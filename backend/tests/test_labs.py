"""Labs: what a lab may contain, what the sandbox refuses, what the checks catch."""

from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path
from typing import Any

import pytest

from hq.labs import (
    SANDBOX_EXEC,
    _find_executable,
    check_phase_text,
    run_exercises,
    validate_lab_files,
    write_lab,
)

SLUG = "elite-performance-phase-01-measurement"

needs_sandbox = pytest.mark.skipif(
    sys.platform != "darwin" or not SANDBOX_EXEC.exists(),
    reason="labs run only under macOS sandbox-exec",
)
needs_go = pytest.mark.skipif(_find_executable("go") is None, reason="go is not installed")
needs_python = pytest.mark.skipif(_find_executable("python3") is None,
                                  reason="python3 is not installed")


def exercise(n: int, **over: Any) -> dict[str, Any]:
    ex: dict[str, Any] = {
        "id": f"E{n}", "title": f"exercise {n}", "kind": "observe", "cwd": "e01",
        "run": "go run .", "expect": ["hello"], "expect_exit": 0, "timeout_s": 60,
        "verify": "auto", "why_manual": "",
    }
    ex.update(over)
    return ex


def lab(exercises: list[dict[str, Any]] | None = None, language: str = "go",
        **files: str) -> dict[str, str]:
    out = {
        "exercises.json": json.dumps({"slug": SLUG, "language": language,
                                      "exercises": exercises or [exercise(1)]}),
        "e01/go.mod": "module lab\n\ngo 1.21\n",
        "e01/main.go": 'package main\n\nimport "fmt"\n\nfunc main() { fmt.Println("hello") }\n',
    }
    out.update({k.replace("__", "/"): v for k, v in files.items()})
    return out


# --- validate_lab_files ---------------------------------------------------------

def test_a_good_lab_is_accepted() -> None:
    assert validate_lab_files(SLUG, lab()) == []


@pytest.mark.parametrize("path", ["../escape.go", "e01/../../escape.go"])
def test_a_path_that_climbs_out_is_refused(path: str) -> None:
    problems = validate_lab_files(SLUG, {**lab(), path: "package main\n"})
    assert any("'..'" in p for p in problems)


def test_an_absolute_path_is_refused() -> None:
    problems = validate_lab_files(SLUG, {**lab(), "/etc/evil.go": "package main\n"})
    assert any("absolute" in p for p in problems)


def test_hidden_and_reserved_files_are_refused() -> None:
    problems = validate_lab_files(SLUG, {**lab(), ".env.txt": "x", "RESULTS.json": "{}"})
    assert any("hidden" in p for p in problems)
    assert any("reserved" in p for p in problems)


@pytest.mark.parametrize("run", ["go run . | tee out.txt", "go run . > out.txt",
                                 "go run .; rm -rf /", "go run $HOME", "python3 `id`"])
def test_shell_metacharacters_are_refused(run: str) -> None:
    problems = validate_lab_files(SLUG, lab([exercise(1, run=run)]))
    assert any("metacharacters" in p for p in problems)


@pytest.mark.parametrize("run", ["bash run.sh", "curl https://example.com", "/usr/local/go/bin/go run ."])
def test_only_go_and_python3_may_be_run(run: str) -> None:
    problems = validate_lab_files(SLUG, lab([exercise(1, run=run)]))
    assert any("must start with `go` or `python3`" in p for p in problems)


def test_a_missing_manifest_is_refused() -> None:
    files = lab()
    del files["exercises.json"]
    assert any("exercises.json is missing" in p for p in validate_lab_files(SLUG, files))


def test_a_go_mod_with_a_dependency_is_refused() -> None:
    files = lab()
    files["e01/go.mod"] = "module lab\n\ngo 1.21\n\nrequire github.com/x/y v1.0.0\n"
    assert any("require" in p for p in validate_lab_files(SLUG, files))


def test_a_manual_exercise_must_say_why() -> None:
    problems = validate_lab_files(SLUG, lab([exercise(1, verify="manual", why_manual="")]))
    assert any("why_manual" in p for p in problems)
    assert validate_lab_files(
        SLUG, lab([exercise(1, verify="manual", why_manual="needs a real load balancer")])
    ) == []


def test_ids_slug_cwd_and_timeout_are_checked() -> None:
    files = lab([exercise(1), exercise(1, cwd="nowhere", timeout_s=900)])
    manifest = json.loads(files["exercises.json"])
    manifest["slug"] = "some-other-phase"
    files["exercises.json"] = json.dumps(manifest)
    problems = " | ".join(validate_lab_files(SLUG, files))

    assert "duplicate exercise ids" in problems
    assert "expected 'elite-performance-phase-01-measurement'" in problems
    assert "not a folder in the lab" in problems
    assert "timeout_s" in problems


def test_writing_a_lab_replaces_the_old_one_whole(tmp_path: Path) -> None:
    write_lab(SLUG, {**lab(), "e01/old.txt": "stale"}, root=tmp_path)
    dest = write_lab(SLUG, lab(), root=tmp_path)

    assert not (dest / "e01/old.txt").exists()
    assert (dest / "exercises.json").is_file()
    assert [p.name for p in tmp_path.iterdir()] == [SLUG]


# --- run_exercises --------------------------------------------------------------

def materialise(tmp_path: Path, files: dict[str, str]) -> Path:
    assert validate_lab_files(SLUG, files) == []
    return write_lab(SLUG, files, root=tmp_path)


def go_lab(source: str, **over: Any) -> dict[str, str]:
    files = lab([exercise(1, **over)])
    files["e01/main.go"] = source
    return files


@needs_sandbox
@needs_go
def test_a_go_hello_lab_passes(tmp_path: Path) -> None:
    [result] = run_exercises(materialise(tmp_path, lab()))

    assert result.status == "pass", result.reason + result.output
    assert "hello" in result.output


@needs_sandbox
@needs_go
def test_a_regex_that_does_not_match_fails_and_is_named(tmp_path: Path) -> None:
    [result] = run_exercises(materialise(tmp_path, lab([exercise(1, expect=["p99=\\d+ms"])])))

    assert result.status == "fail"
    assert "p99=\\d+ms" in result.reason


@needs_sandbox
@needs_go
def test_the_network_is_denied(tmp_path: Path) -> None:
    source = """package main

import (
	"fmt"
	"net"
	"time"
)

func main() {
	for _, addr := range []string{"example.com:80", "1.1.1.1:80"} {
		conn, err := net.DialTimeout("tcp", addr, 5*time.Second)
		if err != nil {
			fmt.Println("dial failed:", addr, err)
			continue
		}
		conn.Close()
		fmt.Println("dial ok:", addr)
	}
}
"""
    [result] = run_exercises(materialise(tmp_path, go_lab(source, expect=["dial ok"])))

    assert result.status == "fail"
    assert "dial ok" not in result.output
    assert "dial failed: example.com:80" in result.output
    assert "dial failed: 1.1.1.1:80" in result.output


@needs_sandbox
@needs_go
def test_a_write_outside_the_temp_copy_is_denied(tmp_path: Path) -> None:
    target = Path(f"/tmp/hq-lab-escape-{uuid.uuid4().hex}")
    source = f"""package main

import (
	"fmt"
	"os"
)

func main() {{
	if err := os.WriteFile("{target}", []byte("escaped"), 0o644); err != nil {{
		fmt.Println("write failed:", err)
		os.Exit(3)
	}}
	fmt.Println("write ok")
}}
"""
    [result] = run_exercises(materialise(tmp_path, go_lab(source, expect=["write ok"])))

    assert result.status == "fail"
    assert "write failed" in result.output
    assert not target.exists()


@needs_sandbox
@needs_python
def test_a_timeout_is_enforced(tmp_path: Path) -> None:
    files = lab([exercise(1, cwd=".", run="python3 sleep.py", expect=[], timeout_s=2)],
                language="python")
    files["sleep.py"] = "import time\nprint('sleeping', flush=True)\ntime.sleep(60)\n"
    started = time.monotonic()
    [result] = run_exercises(materialise(tmp_path, files))

    assert result.status == "fail"
    assert "timed out after 2s" in result.reason
    assert time.monotonic() - started < 20


@needs_sandbox
def test_a_manual_exercise_is_reported_not_run(tmp_path: Path) -> None:
    files = lab([exercise(1, verify="manual", why_manual="needs two machines")])
    [result] = run_exercises(materialise(tmp_path, files))

    assert result.status == "manual"
    assert result.reason == "needs two machines"


def python_lab(tmp_path: Path, *scripts: str, timeout_s: int = 60,
               expect: list[str] | None = None) -> Path:
    """A python lab with one exercise per script, run from the lab root."""
    exercises = [exercise(n, cwd=".", run=f"python3 s{n}.py", expect=expect or [],
                          timeout_s=timeout_s)
                 for n in range(1, len(scripts) + 1)]
    files = lab(exercises, language="python")
    files.update({f"s{n}.py": s for n, s in enumerate(scripts, 1)})
    return materialise(tmp_path, files)


@needs_sandbox
@needs_python
def test_a_lab_cannot_exec_other_programs(tmp_path: Path) -> None:
    script = """import subprocess
for argv in (["/bin/echo", "escaped"], ["/usr/bin/osascript", "-e", "return 1"]):
    try:
        subprocess.run(argv, check=False)
        print("ran", argv[0])
    except OSError as exc:
        print("denied", argv[0], exc)
"""
    [result] = run_exercises(python_lab(tmp_path, script))

    assert result.status == "pass", result.reason + result.output
    assert "denied /bin/echo" in result.output
    assert "denied /usr/bin/osascript" in result.output
    assert "ran " not in result.output


@needs_sandbox
@needs_python
def test_a_lab_cannot_read_or_write_outside_its_folder(tmp_path: Path) -> None:
    import tempfile

    temp_root = Path(tempfile.gettempdir()).resolve()
    secret = temp_root / f"hq-lab-secret-{uuid.uuid4().hex}.txt"
    secret.write_text("the owner's secret")
    target = temp_root / f"hq-lab-escape-{uuid.uuid4().hex}.txt"
    tmp_secret = Path(f"/private/tmp/hq-lab-secret-{uuid.uuid4().hex}.txt")
    try:
        tmp_secret.write_text("in /private/tmp")
    except OSError:
        tmp_secret = secret  # this test process may not write /private/tmp itself
    readable = [str(secret), str(tmp_secret)]
    if Path("/opt/homebrew/var").is_dir():
        readable.append("/opt/homebrew/var")
    script = f"""import os
for path in {readable!r}:
    try:
        print("read", path, os.listdir(path) if os.path.isdir(path) else open(path).read())
    except OSError as exc:
        print("denied read", path, exc)
try:
    open({str(target)!r}, "w").write("escaped")
    print("wrote outside")
except OSError as exc:
    print("denied write", exc)
"""
    try:
        [result] = run_exercises(python_lab(tmp_path, script))
    finally:
        secret.unlink(missing_ok=True)
        if tmp_secret != secret:
            tmp_secret.unlink(missing_ok=True)

    assert result.status == "pass", result.reason + result.output
    for path in readable:
        assert f"denied read {path}" in result.output
    assert "secret" not in result.output.replace("hq-lab-secret", "")
    assert "denied write" in result.output
    assert not target.exists()


@needs_sandbox
@needs_python
def test_a_child_that_leaves_the_process_group_is_killed(tmp_path: Path) -> None:
    import os

    script = """import os, time
pid = os.fork()
if pid == 0:
    os.setsid()
    time.sleep(60)
    os._exit(0)
print(f"child={pid}", flush=True)
time.sleep(60)
"""
    [result] = run_exercises(python_lab(tmp_path, script, timeout_s=2))

    assert "timed out after 2s" in result.reason
    [child] = [int(line.split("=")[1]) for line in result.output.splitlines()
               if line.startswith("child=")]
    deadline = time.monotonic() + 5
    alive = True
    while alive and time.monotonic() < deadline:
        try:
            os.kill(child, 0)
            time.sleep(0.1)
        except ProcessLookupError:
            alive = False
    assert not alive, f"child {child} outlived the exercise"


@needs_sandbox
@needs_python
def test_a_file_over_the_size_limit_cannot_be_written(tmp_path: Path) -> None:
    script = """import os
try:
    with open("big.bin", "wb") as fh:
        for _ in range(100):
            fh.write(b"x" * (1024 * 1024))
    print("wrote 100 MB")
except OSError as exc:
    print("write failed", exc, os.path.getsize("big.bin"))
"""
    [result] = run_exercises(python_lab(tmp_path, script, expect=["wrote 100 MB"]))

    assert result.status == "fail"
    assert "write failed" in result.output
    assert "wrote 100 MB" not in result.output


@needs_sandbox
@needs_python
def test_each_exercise_gets_a_fresh_copy(tmp_path: Path) -> None:
    make = "open('flag.txt', 'w').write('left behind')\nprint('made')\n"
    check = ("import os, sys\nprint('present' if os.path.exists('flag.txt') else 'absent')\n"
             "sys.exit(1 if os.path.exists('flag.txt') else 0)\n")
    first, second = run_exercises(python_lab(tmp_path, make, check))

    assert first.status == "pass", first.reason + first.output
    assert second.status == "pass", second.reason + second.output
    assert "absent" in second.output


def test_a_lab_containing_a_symlink_is_refused(tmp_path: Path) -> None:
    import os

    dest = materialise(tmp_path, lab())
    os.symlink("/etc/hosts", dest / "e01" / "hosts.txt")

    with pytest.raises(ValueError, match=r"e01/hosts.txt is a symlink"):
        run_exercises(dest)


def test_a_lab_is_never_written_through_a_symlink(tmp_path: Path) -> None:
    import os

    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    root = tmp_path / "labs"
    root.mkdir()
    os.symlink(elsewhere, root / SLUG)
    with pytest.raises(ValueError, match="symlink"):
        write_lab(SLUG, lab(), root=root)
    assert list(elsewhere.iterdir()) == []

    linked_root = tmp_path / "linked-labs"
    os.symlink(elsewhere, linked_root)
    with pytest.raises(ValueError, match="symlink"):
        write_lab(SLUG, lab(), root=linked_root)
    assert list(elsewhere.iterdir()) == []


def test_read_lab_returns_files_and_manifest_and_does_not_follow_symlinks(
    tmp_path: Path,
) -> None:
    import os

    from hq.labs import (
        READ_LAB_FILE_BYTES,
        ExerciseResult,
        read_lab_snapshot,
        write_results,
    )

    secret = tmp_path / "secret.txt"
    secret.write_text("the owner's secret")
    secret_dir = tmp_path / "secret-dir"
    secret_dir.mkdir()
    (secret_dir / "key.txt").write_text("another secret")
    dest = materialise(tmp_path / "labs", {**lab(), "e01/big.txt": "y" * (100 * 1024)})
    os.symlink(secret, dest / "e01" / "notes.txt")
    os.symlink(secret_dir, dest / "linked")
    write_results(dest, [ExerciseResult(id="E1", title="t", kind="observe", status="pass")])

    snap = read_lab_snapshot(dest)
    by_path = {f["path"]: f for f in snap["files"]}

    assert set(by_path) == {"exercises.json", "e01/go.mod", "e01/main.go", "e01/big.txt"}
    assert snap["manifest"]["exercises"][0]["id"] == "E1"
    assert snap["results"]["passed"] == 1
    big = by_path["e01/big.txt"]
    assert big["bytes"] == 100 * 1024
    assert "truncated" in big["content"]
    assert len(big["content"]) < READ_LAB_FILE_BYTES + 200
    assert any("e01/notes.txt" in s and "symlink" in s for s in snap["skipped"])
    assert any("linked" in s for s in snap["skipped"])
    assert "secret" not in json.dumps(snap["files"])

    assert read_lab_snapshot(tmp_path / "labs" / "nothing-here")["manifest"] is None


def test_read_lab_is_granted_to_tutor() -> None:
    from hq.tools import review_tools

    assert callable(review_tools.read_lab)
    agents = Path(__file__).resolve().parents[2] / "agents"
    assert "  - read_lab\n" in (agents / "tutor" / "job.md").read_text()


def test_an_all_manual_lab_blocks_when_the_spec_has_a_lab() -> None:
    md = lesson("1.1 Distributions", "1.2 Service time")
    manual = {"exercises": [{"id": f"E{i}", "kind": "observe", "verify": "manual",
                             "why_manual": "needs two machines"} for i in range(1, 8)]}

    blocked = by_check(check_phase_text(md, "", NOTE, [], [], manual, True), "exercises")
    no_lab = by_check(check_phase_text(md, "", NOTE, [], [], manual, False), "exercises")

    assert any(f["severity"] == "block" and "verify: auto" in f["problem"] for f in blocked)
    assert not any(f["severity"] == "block" for f in no_lab)


def test_the_score_is_out_of_130() -> None:
    from hq.tools import review_tools

    assert review_tools.MAX_SCORE == 130
    skill = (Path(__file__).resolve().parents[2] / "agents" / "tutor" / "skills"
             / "review-phase" / "SKILL.md").read_text()
    assert "100 of 130" in skill
    assert "1000" not in skill


# --- check_phase_text -----------------------------------------------------------

NOTE = "Sources read:\n- https://brendangregg.com/usemethod.html\n"


def lesson(*headings: str, body: str = "Text.") -> str:
    parts = [f"## {h}\n\n{body}\n" for h in headings]
    return "\n".join([*parts, "## What I could not verify\n\nNothing.\n"])


def checks(md: str, note: str = NOTE, numbers: list[str] | None = None,
           manifest: dict[str, Any] | None = None) -> list[dict[str, str]]:
    manifest = manifest if manifest is not None else {
        "exercises": [{"id": f"E{i}", "kind": "break" if i < 3 else "observe"}
                      for i in range(1, 8)]
    }
    md = md + "\n" + " ".join(f"E{i}" for i in range(1, 8))
    return check_phase_text(md, "", note, ["Distributions", "Service time"],
                            numbers if numbers is not None else ["1.1", "1.2"], manifest)


def by_check(findings: list[dict[str, str]], name: str) -> list[dict[str, str]]:
    return [f for f in findings if f["check"] == name]


def test_a_missing_spec_section_blocks() -> None:
    findings = by_check(checks(lesson("1.1 Distributions")), "spec coverage")

    assert len(findings) == 1
    assert findings[0]["severity"] == "block"
    assert "1.2" in findings[0]["problem"]
    assert by_check(checks(lesson("1.1 Distributions", "1.2 Service time")),
                    "spec coverage") == []


def test_section_numbers_do_not_match_their_neighbours() -> None:
    findings = by_check(checks(lesson("11.1 Something", "1.10 Other")), "spec coverage")
    assert len(findings) == 2


def test_an_unsourced_url_blocks() -> None:
    md = lesson("1.1 Distributions", "1.2 Service time",
                body="See [this](https://made-up.example.dev/p99).")
    findings = by_check(checks(md), "url provenance")

    assert [f["severity"] for f in findings] == ["block"]
    assert "https://made-up.example.dev/p99" in findings[0]["problem"]


def test_a_url_from_the_study_note_is_fine() -> None:
    md = lesson("1.1 Distributions", "1.2 Service time",
                body="Read (https://brendangregg.com/usemethod.html). And curl http://localhost:8080/.")
    assert by_check(checks(md), "url provenance") == []


def test_no_study_note_blocks_once() -> None:
    findings = by_check(checks(lesson("1.1 A", "1.2 B"), note=""), "url provenance")
    assert len(findings) == 1 and findings[0]["severity"] == "block"


def test_a_missing_could_not_verify_section_blocks() -> None:
    md = "## 1.1 Distributions\n\nText.\n\n## 1.2 Service time\n\nText.\n"
    findings = by_check(checks(md), "not-verified section")

    assert [f["severity"] for f in findings] == ["block"]


def test_an_idiom_warns() -> None:
    md = lesson("1.1 Distributions", "1.2 Service time",
                body="Under the hood the queue grows.")
    findings = by_check(checks(md), "idioms")

    assert [f["severity"] for f in findings] == ["warn"]
    assert "under the hood" in findings[0]["problem"]


def test_a_missing_manifest_blocks_and_a_thin_one_warns() -> None:
    md = lesson("1.1 Distributions", "1.2 Service time")
    missing = by_check(check_phase_text(md, "", NOTE, [], [], None), "exercises")
    thin = by_check(check_phase_text(md, "", NOTE, [], [], {"exercises": [
        {"id": "E1", "kind": "observe"}]}), "exercises")

    assert [f["severity"] for f in missing] == ["block"]
    assert thin and all(f["severity"] == "warn" for f in thin)


def test_a_wall_of_prose_warns_and_a_code_block_breaks_it() -> None:
    def prose(n: int) -> str:
        return "\n\n".join(f"Paragraph {i} of prose." for i in range(n))

    code = "\n\n```go\nfmt.Println(1)\n```\n\n"
    wall = check_phase_text(f"## 1.3 Wall{code}{prose(7)}{code}", "", NOTE, [], [], None)
    broken = check_phase_text(f"## 1.3 Wall{code}{prose(4)}{code}{prose(4)}{code}",
                              "", NOTE, [], [], None)

    [finding] = by_check(wall, "diagram density")
    assert finding["severity"] == "warn"
    assert "7 prose paragraphs" in finding["problem"]
    assert "1.3 Wall" in finding["where"]
    assert by_check(broken, "diagram density") == []


def test_a_pass_is_refused_while_a_blocking_check_stands() -> None:
    """A blocking finding is a fact the reviewer's opinion cannot outvote."""
    import inspect

    from hq.tools import review_tools

    src = inspect.getsource(review_tools.record_review)
    assert "_phase_findings" in src
    assert "blocking finding" in src
    assert "return await _phase_findings" in inspect.getsource(review_tools.check_phase)
