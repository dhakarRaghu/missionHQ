"""Labs: the exercises a course phase ships, validated and run in a sandbox.

The inference course on his study platform was reviewed on 2026-09-14, and the
review found commands that did not run and benchmark numbers that did not
reproduce. He had already studied from it. A lab that does not run teaches him
that the course cannot be trusted, and he finds out at the worst moment: with
the terminal open, following along.

So a lab is data, files plus a manifest of exercises, and this module is the
part that proves each exercise runs before he sees it. Pure logic and
subprocesses only, no database: the ledger side lives in
`hq.tools.review_tools`.
"""

from __future__ import annotations

import json
import os
import re
import resource
import shlex
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
import uuid
from collections.abc import Callable, Iterator, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from hq.config import settings

LAB_ROOT = settings().learning_dir / "labs"
MANIFEST = "exercises.json"
RESULTS_MD = "RESULTS.md"
# Machine-readable twin of RESULTS.md. record_review reads it to refuse a pass
# over a failed exercise. Replacing the lab dir deletes it, so a result can
# never outlive the lab it was measured on.
RESULTS_JSON = "RESULTS.json"
# Written by run_lab only. A lab that shipped its own RESULTS.json could hand
# the reviewer a pass nobody ran.
RESERVED_NAMES = frozenset({RESULTS_MD, RESULTS_JSON})

ALLOWED_EXTENSIONS = frozenset({
    ".go", ".mod", ".sum", ".py", ".txt", ".md", ".json", ".sql", ".sh",
    ".yaml", ".yml", ".toml",
})
MAX_FILES = 60
MAX_FILE_BYTES = 200 * 1024
MAX_TOTAL_BYTES = 1536 * 1024
KINDS = frozenset({"observe", "build", "break", "debug"})
LANGUAGES = frozenset({"go", "python"})
VERIFY_MODES = frozenset({"auto", "manual"})
EXECUTABLES = frozenset({"go", "python3"})
# No shell runs these commands, so a pipe or a redirect would be passed to the
# program as a literal argument and the exercise would fail in a way that
# looks like the lesson's fault. Refused up front instead.
SHELL_METACHARACTERS = frozenset("|&;<>$`\n\r")
MAX_TIMEOUT_S = 300
DEFAULT_TIMEOUT_S = 60
OUTPUT_TAIL_CHARS = 4000
# How much of an exercise's output the `expect` regexes are matched against.
MATCH_BYTES = 1024 * 1024

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,199}$")
_ID_RE = re.compile(r"^E[1-9]\d*$")
_GO_REQUIRE_RE = re.compile(r"^\s*require\b", re.MULTILINE)

SANDBOX_EXEC = Path("/usr/bin/sandbox-exec")
NICE = Path("/usr/bin/nice")
_KNOWN_EXECUTABLES = {
    "go": ("/usr/local/go/bin/go", "/opt/homebrew/bin/go"),
    "python3": ("/opt/homebrew/bin/python3", "/usr/local/bin/python3", "/usr/bin/python3"),
}


def lab_dir(slug: str) -> Path:
    return LAB_ROOT / slug


# --- validation ---------------------------------------------------------------

def _path_problem(path: object) -> str | None:
    if not isinstance(path, str) or not path:
        return f"{path!r}: a file path must be a non-empty string"
    if path != path.strip() or "\\" in path or "\x00" in path:
        return f"{path!r}: no surrounding whitespace, backslashes or NUL bytes"
    if path.startswith("/"):
        return f"{path!r}: absolute paths are not allowed; use a path relative to the lab"
    parts = path.split("/")
    if ".." in parts:
        return f"{path!r}: '..' is not allowed; the lab cannot reach outside its own folder"
    if any(p in ("", ".") for p in parts):
        return f"{path!r}: empty or '.' path segments are not allowed"
    if any(p.startswith(".") for p in parts):
        return f"{path!r}: hidden files and folders are not allowed"
    if path in RESERVED_NAMES:
        return f"{path!r}: reserved; run_lab writes it"
    suffix = PurePosixPath(path).suffix
    if suffix not in ALLOWED_EXTENSIONS:
        return (f"{path!r}: extension {suffix or '(none)'} is not allowed;"
                f" allowed: {' '.join(sorted(ALLOWED_EXTENSIONS))}")
    return None


def run_problems(run: str) -> list[str]:
    """Why this command cannot be run as an exercise, or []."""
    if not run.strip():
        return ["run is empty; an auto exercise needs a command"]
    bad = sorted({c for c in run if c in SHELL_METACHARACTERS})
    if bad:
        shown = "".join(bad).replace("\n", "\\n").replace("\r", "\\r")
        return [(
            f"run {run!r} contains shell metacharacters {shown!r}. No shell runs it:"
            " write one command, and do any piping or redirection inside the program"
        )]
    try:
        argv = shlex.split(run)
    except ValueError as exc:
        return [f"run {run!r} does not parse: {exc}"]
    if not argv or argv[0] not in EXECUTABLES:
        return [f"run {run!r} must start with `go` or `python3`"]
    return []


def _exercise_problems(ex: dict[str, Any], dirs: set[str] | None) -> list[str]:
    problems: list[str] = []
    if not isinstance(ex.get("title"), str) or not ex["title"].strip():
        problems.append("title is required")
    if ex.get("kind") not in KINDS:
        problems.append(f"kind must be one of {sorted(KINDS)}, got {ex.get('kind')!r}")
    verify = ex.get("verify", "auto")
    if verify not in VERIFY_MODES:
        problems.append(f"verify must be 'auto' or 'manual', got {verify!r}")
    if verify == "manual" and not str(ex.get("why_manual") or "").strip():
        problems.append("verify is 'manual', so why_manual must say why code cannot check it")

    cwd = ex.get("cwd", ".")
    if not isinstance(cwd, str):
        problems.append("cwd must be a string")
    else:
        norm = cwd.strip().rstrip("/") or "."
        if norm.startswith("/") or ".." in norm.split("/"):
            problems.append(f"cwd {cwd!r} must be a relative folder inside the lab")
        elif dirs is not None and norm not in dirs:
            problems.append(f"cwd {cwd!r} is not a folder in the lab's files")

    run = ex.get("run", "")
    if not isinstance(run, str):
        problems.append("run must be a string")
    elif run.strip() or verify == "auto":
        problems.extend(run_problems(run))

    expect = ex.get("expect", [])
    if not isinstance(expect, list) or not all(isinstance(e, str) for e in expect):
        problems.append("expect must be a list of regex strings")
    else:
        for pattern in expect:
            try:
                re.compile(pattern)
            except re.error as exc:
                problems.append(f"expect regex {pattern!r} does not compile: {exc}")

    expect_exit = ex.get("expect_exit", 0)
    if not isinstance(expect_exit, int) or isinstance(expect_exit, bool):
        problems.append("expect_exit must be an integer")
    timeout = ex.get("timeout_s", DEFAULT_TIMEOUT_S)
    if (not isinstance(timeout, int) or isinstance(timeout, bool)
            or not 1 <= timeout <= MAX_TIMEOUT_S):
        problems.append(f"timeout_s must be an integer from 1 to {MAX_TIMEOUT_S}")
    return problems


def manifest_problems(slug: str, manifest: object, dirs: set[str] | None = None) -> list[str]:
    """Why this exercises.json is not a valid manifest for `slug`, or []."""
    if not isinstance(manifest, dict):
        return [f"{MANIFEST} must be a JSON object"]
    problems: list[str] = []
    if manifest.get("slug") != slug:
        problems.append(f"{MANIFEST}: slug is {manifest.get('slug')!r}, expected {slug!r}")
    if manifest.get("language") not in LANGUAGES:
        problems.append(f"{MANIFEST}: language must be 'go' or 'python'")
    exercises = manifest.get("exercises")
    if not isinstance(exercises, list) or not exercises:
        problems.append(f"{MANIFEST}: exercises must be a non-empty list")
        return problems
    ids: list[str] = []
    for n, ex in enumerate(exercises, 1):
        if not isinstance(ex, dict):
            problems.append(f"exercise #{n}: must be an object")
            continue
        ex_id = ex.get("id")
        label = ex_id if isinstance(ex_id, str) and ex_id else f"exercise #{n}"
        if isinstance(ex_id, str):
            ids.append(ex_id)
        if not isinstance(ex_id, str) or not _ID_RE.match(ex_id):
            problems.append(f"{label}: id must look like E1, E2, ...")
        problems.extend(f"{label}: {p}" for p in _exercise_problems(ex, dirs))
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        problems.append(f"{MANIFEST}: duplicate exercise ids {dupes}")
    expected = {f"E{i}" for i in range(1, len(exercises) + 1)}
    if set(ids) != expected:
        problems.append(
            f"{MANIFEST}: ids must be E1..E{len(exercises)}, each once;"
            f" got {sorted(ids, key=lambda i: (len(i), i))}"
        )
    return problems


def validate_lab_files(slug: str, files: dict[str, str]) -> list[str]:
    """Every reason this lab cannot be written, or [] when it can."""
    problems: list[str] = []
    if not SLUG_RE.match(slug or ""):
        problems.append(f"slug {slug!r} must be lowercase letters, digits and hyphens")
    if not isinstance(files, dict) or not files:
        return [*problems, "files is empty: a lab needs at least exercises.json"]
    if len(files) > MAX_FILES:
        problems.append(f"{len(files)} files; a lab may have at most {MAX_FILES}")

    total = 0
    dirs = {"."}
    for path, content in files.items():
        issue = _path_problem(path)
        if issue:
            problems.append(issue)
            continue
        if not isinstance(content, str):
            problems.append(f"{path!r}: content must be text")
            continue
        size = len(content.encode("utf-8"))
        total += size
        if size > MAX_FILE_BYTES:
            problems.append(f"{path!r}: {size} bytes; each file may be at most {MAX_FILE_BYTES}")
        parent = PurePosixPath(path).parent
        while str(parent) != ".":
            dirs.add(str(parent))
            parent = parent.parent
        if PurePosixPath(path).name == "go.mod" and _GO_REQUIRE_RE.search(content):
            problems.append(
                f"{path!r} has a require line. Labs are stdlib only: the sandbox has no"
                " network and GOPROXY is off, so a dependency can never download"
            )
    if total > MAX_TOTAL_BYTES:
        problems.append(f"lab is {total} bytes; at most {MAX_TOTAL_BYTES} in total")

    if MANIFEST not in files:
        problems.append(f"{MANIFEST} is missing; every lab needs its manifest")
        return problems
    try:
        manifest = json.loads(files[MANIFEST])
    except (TypeError, ValueError) as exc:
        problems.append(f"{MANIFEST} is not valid JSON: {exc}")
        return problems
    problems.extend(manifest_problems(slug, manifest, dirs))
    return problems


# --- files on disk ------------------------------------------------------------

def read_lab_files(directory: Path) -> dict[str, str]:
    """The lab's own files as {relative path: text}. Hidden files (a Finder
    .DS_Store) and run_lab's results are not part of the lab."""
    out: dict[str, str] = {}
    for p in sorted(directory.rglob("*")):
        rel = p.relative_to(directory)
        if not p.is_file() or any(part.startswith(".") for part in rel.parts):
            continue
        if len(rel.parts) == 1 and rel.name in RESERVED_NAMES:
            continue
        try:
            out[rel.as_posix()] = p.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError(f"{rel.as_posix()} is not UTF-8 text") from exc
    return out


def load_manifest(directory: Path) -> dict[str, Any]:
    path = directory / MANIFEST
    if not path.is_file():
        raise ValueError(f"no {MANIFEST} in {directory}")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except ValueError as exc:
        raise ValueError(f"{MANIFEST} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        # ValueError, like the bad-JSON case above: callers treat both as
        # "this manifest is unusable", and one exception type keeps that simple.
        raise ValueError(f"{MANIFEST} must be a JSON object")  # noqa: TRY004
    return data


def read_manifest(directory: Path) -> dict[str, Any] | None:
    try:
        return load_manifest(directory)
    except (ValueError, OSError):
        return None


def _walk_lab(directory: Path) -> Iterator[tuple[str, os.stat_result, int, str]]:
    """Every non-hidden entry under `directory` that is not a real folder, as
    (relative path, lstat, parent dir fd, name). Symlinks are yielded, never
    followed: os.fwalk holds each folder open by fd, so a folder swapped for a
    symlink mid-walk is not descended into. Read an entry before advancing;
    the fd closes with the next step."""
    top = str(directory)
    for dirpath, dirnames, filenames, dirfd in os.fwalk(top, follow_symlinks=False):
        rel_dir = PurePosixPath(os.path.relpath(dirpath, top))
        keep: list[str] = []
        for name in sorted([*dirnames, *filenames]):
            if name.startswith("."):
                continue
            try:
                st = os.stat(name, dir_fd=dirfd, follow_symlinks=False)
            except FileNotFoundError:
                continue
            if stat.S_ISDIR(st.st_mode):
                keep.append(name)
                continue
            rel = name if str(rel_dir) == "." else f"{rel_dir}/{name}"
            yield rel, st, dirfd, name
        dirnames[:] = keep


def _read_nofollow(dirfd: int, name: str, limit: int) -> bytes:
    """Up to limit + 1 bytes of a regular file, refusing a symlink at open."""
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=dirfd)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise OSError(f"{name} is not a regular file")
        chunks: list[bytes] = []
        remaining = limit + 1
        while remaining > 0:
            chunk = os.read(fd, min(remaining, 1 << 16))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)
    finally:
        os.close(fd)


def snapshot_lab(src: Path, dest: Path) -> list[str]:
    """Copy the lab at `src` into `dest` once, and say why it cannot be run.

    Validation, the manifest and every exercise then read this copy, never
    the repo folder again: three reads of a folder someone can edit are three
    chances to validate one lab and run another. A symlink is refused, not
    copied, and not followed: `e01/notes.txt -> ~/.ssh/id_ed25519` would print
    the key into RESULTS.md. A hard link is refused for the same reason.
    Hidden files and run_lab's own results are not part of the lab.
    """
    problems: list[str] = []
    try:
        top = os.lstat(src)
    except FileNotFoundError:
        return [f"no lab folder at {src}"]
    if not stat.S_ISDIR(top.st_mode):
        return [f"{src.name} is not a folder; a symlinked lab is never followed"]
    count = total = 0
    for rel, st, dirfd, name in _walk_lab(src):
        if stat.S_ISLNK(st.st_mode):
            problems.append(f"{rel} is a symlink; a lab may contain only regular files")
            continue
        if "/" not in rel and name in RESERVED_NAMES:
            continue
        if not stat.S_ISREG(st.st_mode):
            problems.append(f"{rel} is not a regular file")
            continue
        if st.st_nlink > 1:
            problems.append(f"{rel} has {st.st_nlink} hard links; a lab file must have one")
            continue
        count += 1
        if count > MAX_FILES:
            problems.append(f"more than {MAX_FILES} files; a lab may have at most {MAX_FILES}")
            break
        data = _read_nofollow(dirfd, name, MAX_FILE_BYTES)
        if len(data) > MAX_FILE_BYTES:
            problems.append(f"{rel!r}: over {MAX_FILE_BYTES} bytes")
            continue
        total += len(data)
        if total > MAX_TOTAL_BYTES:
            problems.append(f"lab is over {MAX_TOTAL_BYTES} bytes in total")
            break
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    dest.mkdir(parents=True, exist_ok=True)
    return problems


READ_LAB_FILE_BYTES = 60 * 1024
READ_LAB_TOTAL_BYTES = 400 * 1024
# Enough for any file a valid lab can hold and for RESULTS.json; a bigger file
# is shown truncated and not parsed.
_READ_LAB_LIMIT = 2 * 1024 * 1024


def _as_text(data: bytes, cut: bool) -> str | None:
    if b"\x00" in data:
        return None
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as exc:
        # A read cut at the limit can end inside one multi-byte character.
        if cut and exc.start >= len(data) - 3:
            return data[:exc.start].decode("utf-8", errors="replace")
        return None


def _json_object(data: bytes) -> dict[str, Any] | None:
    try:
        parsed = json.loads(data.decode("utf-8"))
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def read_lab_snapshot(directory: Path) -> dict[str, Any]:
    """What `read_lab` shows: the lab's text files, its parsed manifest and
    its last results. Reads only; never follows a symlink, never leaves the
    folder. Each file is cut at READ_LAB_FILE_BYTES and all of them together
    at READ_LAB_TOTAL_BYTES, with a marker where text was cut."""
    directory = Path(directory)
    files: list[dict[str, Any]] = []
    skipped: list[str] = []
    out: dict[str, Any] = {"slug": directory.name, "files": files, "manifest": None,
                           "results": None, "skipped": skipped}
    try:
        top = os.lstat(directory)
    except FileNotFoundError:
        return {**out, "note": "no lab written for this phase"}
    if not stat.S_ISDIR(top.st_mode):
        raise ValueError(f"{directory.name} is not a folder; a symlinked lab is never followed")
    budget = READ_LAB_TOTAL_BYTES
    for rel, st, dirfd, name in _walk_lab(directory):
        if stat.S_ISLNK(st.st_mode):
            skipped.append(f"{rel}: symlink, not followed")
            continue
        if not stat.S_ISREG(st.st_mode):
            skipped.append(f"{rel}: not a regular file")
            continue
        try:
            data = _read_nofollow(dirfd, name, _READ_LAB_LIMIT)
        except OSError as exc:
            skipped.append(f"{rel}: unreadable ({exc})")
            continue
        cut = len(data) > _READ_LAB_LIMIT
        data = data[:_READ_LAB_LIMIT]
        top_level = "/" not in rel
        if top_level and name == RESULTS_JSON:
            out["results"] = None if cut else _json_object(data)
            continue
        if top_level and name == RESULTS_MD:
            continue  # the same facts as RESULTS.json, which `results` carries
        text = _as_text(data, cut)
        if text is None:
            skipped.append(f"{rel}: not text")
            continue
        if top_level and name == MANIFEST and not cut:
            out["manifest"] = _json_object(data)
        encoded = text.encode("utf-8")
        shown = min(READ_LAB_FILE_BYTES, budget, len(encoded))
        if shown == 0 and encoded:
            content = (f"[omitted: the {READ_LAB_TOTAL_BYTES // 1024} KB read budget"
                       " is spent]")
        else:
            content = encoded[:shown].decode("utf-8", errors="ignore")
            if cut or shown < len(encoded):
                content += f"\n[... truncated: {shown} of {st.st_size} bytes shown]"
        budget -= shown
        files.append({"path": rel, "bytes": st.st_size, "content": content})
    return out


def _refuse_symlink(path: Path) -> None:
    if path.is_symlink():
        raise ValueError(f"{path} is a symlink; a lab is never written through one")


def write_lab(slug: str, files: dict[str, str], root: Path | None = None) -> Path:
    """Replace the lab folder with `files`, never leaving a half-written lab.

    The files go into a hidden sibling first and are swapped in by rename. A
    reviewer running the lab while tutor rewrites it sees the old lab or the
    new one, not a mix, and a failed write leaves the old lab where it was.
    No path component may be a symlink: not the labs folder, not the lab,
    not a folder inside it.
    """
    base = root or LAB_ROOT
    base.mkdir(parents=True, exist_ok=True)
    dest = base / slug
    _refuse_symlink(base)
    _refuse_symlink(dest)
    staging = Path(tempfile.mkdtemp(prefix=f".{slug}.new-", dir=base))
    old: Path | None = None
    try:
        for rel, content in files.items():
            parent = staging
            for part in PurePosixPath(rel).parts[:-1]:
                parent = parent / part
                _refuse_symlink(parent)
                parent.mkdir(exist_ok=True)
            fd = os.open(staging / rel, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW,
                         0o644)
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(content)
        if dest.exists():
            old = Path(tempfile.mkdtemp(prefix=f".{slug}.old-", dir=base))
            old.rmdir()
            dest.rename(old)
        try:
            staging.rename(dest)
        except OSError:
            if old is not None:
                old.rename(dest)
                old = None
            raise
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise
    if old is not None:
        shutil.rmtree(old, ignore_errors=True)
    return dest


# --- running ------------------------------------------------------------------

@dataclass
class ExerciseResult:
    id: str
    title: str
    kind: str
    status: str  # pass | fail | manual
    reason: str = ""
    output: str = ""
    seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sandbox_available() -> bool:
    return sys.platform == "darwin" and SANDBOX_EXEC.exists()


PS = Path("/bin/ps")
# Every exercise's processes carry this in their environment, so the ones
# that leave the process group (os.setsid, a double fork) can still be found.
RUN_MARKER = "HQ_LAB_RUN"
CPU_GRACE_S = 5
MAX_WRITE_FILE_BYTES = 64 * 1024 * 1024
# RLIMIT_NPROC on macOS counts every process the uid owns, so the limit is the
# user's current count plus this headroom, not a small absolute number.
NPROC_HEADROOM = 128
MAX_ADDRESS_SPACE = 16 * 1024 * 1024 * 1024
MAX_LAB_DISK_BYTES = 256 * 1024 * 1024
MAX_LAB_DISK_FILES = 20_000
DISK_POLL_S = 1.0

# Read denies. Later allows re-open the exercise's own folders.
_DENY_READ = ("/Users", "/opt/homebrew/var", "/private/tmp", "/private/var/folders",
              "/Volumes")
# `open URL` and NSWorkspace hand the url to LaunchServices, which starts an
# unsandboxed app that has the network. No lookup, no handoff.
_LAUNCH_SERVICES = ("com.apple.coreservices.launchservicesd", "com.apple.lsd.mapdb",
                    "com.apple.lsd.modifydb")


def _quoted(path: str) -> str:
    if not path.startswith("/") or '"' in path or "\\" in path:
        raise ValueError(f"path {path!r} cannot be quoted into a sandbox profile")
    return f'"{path}"'


def _subpaths(paths: Sequence[str]) -> str:
    return " ".join(f"(subpath {_quoted(p)})" for p in paths)


def sandbox_profile(ex_root: Path, cache: Path, toolchains: Sequence[str]) -> str:
    """The macOS sandbox one exercise runs under.

    `ex_root` is this exercise's own folder (its copy of the lab, HOME, TMPDIR,
    GOTMPDIR, GOPATH); `cache` is the Go build cache the run's exercises share;
    `toolchains` are the Go and python3 installations from `toolchain_paths`.

    Verified on this machine on 2026-09-14 (macOS 15.7.8, Go 1.24.1 at
    /usr/local/go, Homebrew python 3.14), with a cold build cache:
      - `go run .` and `go test -v .` build and run stdlib programs with
        CGO_ENABLED=0 and exec allowed only in GOROOT, GOTMPDIR and GOCACHE
        (Go 1.24 caches `go run` binaries in GOCACHE and runs them from
        there). Go needed no other executable; python3 needed none beyond its
        own base_prefix (the framework re-execs Resources/Python.app inside it).
        Neither toolchain needed a read path under the denied folders.
      - exec of /bin/echo, /usr/bin/osascript, /usr/bin/open and a `#!/bin/sh`
        script fails with "operation not permitted". A platform binary copied
        into the lab (echo, osascript, open, launchctl) is killed with SIGKILL
        when run.
      - reads of /opt/homebrew/var, /private/tmp (and /tmp), /Users and a
        sibling folder under /private/var/folders fail; so do writes to /tmp
        and to /private/var/folders outside the exercise.
      - network: `net.Dial` to a host name fails at DNS and a connect to
        1.1.1.1:80 fails with "operation not permitted", from Go and Python.
    Lab output is copied into RESULTS.md and the reviewer's context, so
    anything a lab can read, it can publish; anything it can exec outside its
    toolchain, it can use to reach the network through another app.
    """
    root = str(ex_root.resolve())
    shared = str(cache.resolve())
    gotmp = str((ex_root / "gotmp").resolve())
    launch = " ".join(f'(global-name "{name}")' for name in _LAUNCH_SERVICES)
    return "\n".join([
        "(version 1)",
        "(allow default)",
        "(deny network*)",
        "(deny process-exec*)",
        f"(allow process-exec* {_subpaths([*toolchains, gotmp, shared])})",
        "(deny appleevent-send)",
        f"(deny mach-lookup {launch})",
        f"(deny file-read* {_subpaths(_DENY_READ)})",
        f"(allow file-read* {_subpaths([root, shared, *toolchains])})",
        "(deny file-write*)",
        (f'(allow file-write* {_subpaths([root, shared])} (literal "/dev/null")'
         ' (literal "/dev/tty"))'),
    ])


def _find_executable(name: str) -> str | None:
    for candidate in _KNOWN_EXECUTABLES.get(name, ()):
        if os.access(candidate, os.X_OK):
            return candidate
    return shutil.which(name)


def _probe_output(argv: list[str], home: Path) -> str:
    try:
        done = subprocess.run(
            argv, capture_output=True, text=True, timeout=30, check=True,
            stdin=subprocess.DEVNULL,
            env={"PATH": "/usr/bin:/bin", "HOME": str(home), "GOTOOLCHAIN": "local"},
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout.strip()


def toolchain_paths(scratch: Path) -> list[str]:
    """The installations a lab may execute from, asked of the toolchains
    themselves on every run so an upgrade does not leave a stale path: the
    go binary and `go env GOROOT`, the python3 binary and its
    `sys.base_prefix`, each as given and resolved (the sandbox matches the
    resolved path; /opt/homebrew/bin/python3 is a symlink into the Cellar)."""
    paths: set[str] = set()
    go = _find_executable("go")
    if go:
        paths.add(go)
        paths.add(_probe_output([go, "env", "GOROOT"], scratch)
                  or str(Path(os.path.realpath(go)).parent.parent))
    py = _find_executable("python3")
    if py:
        paths.add(py)
        base = _probe_output([py, "-I", "-c", "import sys; print(sys.base_prefix)"], scratch)
        if base:
            paths.add(base)
    paths |= {os.path.realpath(p) for p in paths if p}
    return sorted(p for p in paths
                  if p.startswith("/") and p != "/" and '"' not in p and "\\" not in p)


def _clean_env(ex_root: Path, cache: Path, marker: str) -> dict[str, str]:
    """Nothing from the backend's own environment reaches a lab: not the
    database URL, not the gateway key. Only what go and python3 need."""
    path_dirs: list[str] = []
    for name in sorted(EXECUTABLES):
        exe = _find_executable(name)
        if exe and str(Path(exe).parent) not in path_dirs:
            path_dirs.append(str(Path(exe).parent))
    path_dirs += ["/usr/bin", "/bin"]
    home = ex_root / "home"
    return {
        "PATH": ":".join(path_dirs),
        "HOME": str(home),
        "TMPDIR": str(home / "tmp"),
        "GOCACHE": str(cache / "gocache"),
        "GOTMPDIR": str(ex_root / "gotmp"),
        "GOPATH": str(ex_root / "gopath"),
        "GOPROXY": "off",
        "GOFLAGS": "-mod=mod",
        "GOTOOLCHAIN": "local",
        # cgo would exec clang, which the sandbox does not allow.
        "CGO_ENABLED": "0",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONIOENCODING": "utf-8",
        "LANG": "en_US.UTF-8",
        RUN_MARKER: marker,
    }


def _user_process_count() -> int:
    done = subprocess.run([str(PS), "-axo", "uid="], capture_output=True, text=True,
                          timeout=10, check=True)
    uid = os.getuid()
    return sum(1 for field in done.stdout.split() if field.isdigit() and int(field) == uid)


def _resource_limits(timeout: int) -> Callable[[], None]:
    """A preexec_fn setting the exercise's rlimits, inherited by every process
    it starts. The values are computed here, before the fork, so the child
    only calls setrlimit: preexec_fn runs between fork and exec in a threaded
    process, and anything that takes a lock there can deadlock."""
    cpu = timeout + CPU_GRACE_S
    _, nproc_hard = resource.getrlimit(resource.RLIMIT_NPROC)
    nproc = _user_process_count() + NPROC_HEADROOM
    if nproc_hard != resource.RLIM_INFINITY:
        nproc = min(nproc, nproc_hard)

    def apply() -> None:
        resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
        resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_WRITE_FILE_BYTES, MAX_WRITE_FILE_BYTES))
        resource.setrlimit(resource.RLIMIT_NPROC, (nproc, nproc))
        try:
            # macOS does not honour this as a memory cap: it refuses any
            # RLIMIT_AS below the process's current virtual size (verified
            # 2026-09-14: 1 GB, 8 GB and 64 GB are refused, 1 TB is accepted),
            # and the forked backend is already past 16 GB of address space.
            # Kept for a kernel that enforces it.
            resource.setrlimit(resource.RLIMIT_AS, (MAX_ADDRESS_SPACE, MAX_ADDRESS_SPACE))
        except (ValueError, OSError):
            pass

    return apply


def _kill_group(pid: int) -> None:
    try:
        os.killpg(pid, signal.SIGKILL)
    except OSError:
        pass  # the group already exited


def _marked_pids(marker: str) -> list[int]:
    """Pids whose environment carries this exercise's marker.

    `ps -E` prints the environment after the command for the user's own
    processes (verified 2026-09-14 for sandboxed python, including a child
    that called setsid). It hides it for Apple platform binaries, which the
    sandbox does not let a lab exec. A process that re-execs itself with an
    empty environment drops the marker; RLIMIT_CPU is the backstop for that.
    """
    try:
        done = subprocess.run([str(PS), "-axEww", "-o", "pid=,command="],
                              capture_output=True, text=True, errors="replace", timeout=10,
                              check=False)
    except (OSError, subprocess.SubprocessError):
        return []
    needle = f"{RUN_MARKER}={marker}"
    me = os.getpid()
    pids: list[int] = []
    for line in done.stdout.splitlines():
        head, _, rest = line.strip().partition(" ")
        if head.isdigit() and int(head) != me and needle in rest.split():
            pids.append(int(head))
    return pids


def _kill_exercise(marker: str, pgid: int) -> None:
    """SIGKILL the exercise's process group and every process carrying its
    marker, until none is left. A child that called os.setsid is not in the
    group; it is found by the marker."""
    _kill_group(pgid)
    for _ in range(20):
        pids = _marked_pids(marker)
        if not pids:
            return
        for pid in pids:
            try:
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        time.sleep(0.05)


def _disk_usage(root: Path) -> tuple[int, int]:
    """(bytes on disk, entries) under root, without following symlinks."""
    used = count = 0
    stack = [str(root)]
    while stack:
        try:
            entries = os.scandir(stack.pop())
        except OSError:
            continue
        with entries:
            for entry in entries:
                try:
                    st = entry.stat(follow_symlinks=False)
                except OSError:
                    continue
                count += 1
                used += st.st_blocks * 512
                if stat.S_ISDIR(st.st_mode):
                    stack.append(entry.path)
    return used, count


def _disk_problem(root: Path) -> str:
    used, count = _disk_usage(root)
    if used > MAX_LAB_DISK_BYTES:
        return (f"the lab's temp folder reached {used // (1024 * 1024)} MB;"
                f" the limit is {MAX_LAB_DISK_BYTES // (1024 * 1024)} MB")
    if count > MAX_LAB_DISK_FILES:
        return f"the lab's temp folder holds {count} entries; the limit is {MAX_LAB_DISK_FILES}"
    return ""


def _wait(proc: subprocess.Popen[bytes], timeout: int, watch: Path) -> tuple[int | None, str]:
    """(exit code, why it was stopped). Checks disk use while it waits, so a
    lab filling the disk is stopped within a second, not at its timeout."""
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return None, f"timed out after {timeout}s"
        try:
            return proc.wait(timeout=min(DISK_POLL_S, remaining)), ""
        except subprocess.TimeoutExpired:
            pass
        problem = _disk_problem(watch)
        if problem:
            return None, problem


def _read_output(log: Path) -> str:
    size = log.stat().st_size
    with log.open("rb") as fh:
        if size > MATCH_BYTES:
            fh.seek(size - MATCH_BYTES)
        return fh.read().decode("utf-8", errors="replace")


def _force_remove(func: Callable[..., Any], path: str, _exc: BaseException) -> None:
    """Go marks some cache files read-only; make them writable and retry."""
    try:
        os.chmod(path, stat.S_IRWXU)
        func(path)
    except OSError:
        pass


def _run_one(ex: dict[str, Any], run_root: Path, snapshot: Path, cache: Path,
             toolchains: Sequence[str]) -> ExerciseResult:
    result = ExerciseResult(id=str(ex["id"]), title=str(ex.get("title", "")),
                            kind=str(ex.get("kind", "")), status="fail")
    if ex.get("verify", "auto") == "manual":
        result.status = "manual"
        result.reason = str(ex.get("why_manual") or "")
        return result

    argv = shlex.split(str(ex["run"]))
    exe = _find_executable(argv[0])
    if exe is None:
        result.reason = f"{argv[0]} is not installed on this machine"
        return result

    # A fresh copy per exercise: one exercise's leftovers cannot make the next
    # one pass. Only the Go build cache is shared, so builds stay fast.
    ex_root = run_root / f"run-{result.id}"
    work = ex_root / "lab"
    try:
        shutil.copytree(snapshot, work)
        for sub in ("home/tmp", "gotmp", "gopath"):
            (ex_root / sub).mkdir(parents=True, exist_ok=True)
        return _execute(ex, result, run_root, ex_root, cache, exe, argv, toolchains)
    finally:
        shutil.rmtree(ex_root, onexc=_force_remove)


def _execute(ex: dict[str, Any], result: ExerciseResult, run_root: Path, ex_root: Path,
             cache: Path, exe: str, argv: list[str], toolchains: Sequence[str]) -> ExerciseResult:
    work = ex_root / "lab"
    cwd = (work / (str(ex.get("cwd") or ".").strip().rstrip("/") or ".")).resolve()
    if not cwd.is_relative_to(work) or not cwd.is_dir():
        result.reason = f"cwd {ex.get('cwd')!r} is not a folder in the lab"
        return result
    timeout = int(ex.get("timeout_s", DEFAULT_TIMEOUT_S))
    expect_exit = int(ex.get("expect_exit", 0))
    marker = uuid.uuid4().hex
    profile = sandbox_profile(ex_root, cache, toolchains)
    env = _clean_env(ex_root, cache, marker)

    log = run_root / "logs" / f"{result.id}.log"
    stopped = ""
    code: int | None = None
    started = time.monotonic()
    try:
        limits = _resource_limits(timeout)
        with log.open("wb") as out:
            # start_new_session puts `go run` and the binary it builds in one
            # process group; the marker sweep catches whatever leaves it.
            proc = subprocess.Popen(
                [str(NICE), "-n", "10", str(SANDBOX_EXEC), "-p", profile, exe, *argv[1:]],
                cwd=cwd, env=env, stdin=subprocess.DEVNULL, stdout=out,
                # preexec_fn is the only way to set rlimits on this child
                # without another unsandboxed launcher process; `limits` only
                # calls setrlimit with precomputed ints (see _resource_limits).
                stderr=subprocess.STDOUT, start_new_session=True,
                preexec_fn=limits,  # noqa: PLW1509
            )
            try:
                code, stopped = _wait(proc, timeout, run_root)
            finally:
                _kill_exercise(marker, proc.pid)
                proc.wait()
    except (OSError, subprocess.SubprocessError) as exc:
        result.reason = f"the exercise could not be started: {exc}"
        return result
    result.seconds = round(time.monotonic() - started, 2)
    text = _read_output(log)
    result.output = text[-OUTPUT_TAIL_CHARS:]
    log.unlink(missing_ok=True)

    reasons: list[str] = []
    if stopped:
        reasons.append(stopped)
    else:
        if code != expect_exit:
            reasons.append(f"exit code {code}, expected {expect_exit}")
        for pattern in ex.get("expect", []):
            if not re.search(pattern, text, re.MULTILINE):
                reasons.append(f"no output matched /{pattern}/")
        disk = _disk_problem(run_root)
        if disk:
            reasons.append(disk)
    result.status = "fail" if reasons else "pass"
    result.reason = "; ".join(reasons)
    return result


def run_exercises(directory: Path) -> list[ExerciseResult]:
    """Run every `verify: auto` exercise of the lab in `directory`, sandboxed.

    The repo folder is read once, into a snapshot that refuses symlinks, and
    everything after reads the snapshot: validation (a hand edit since
    `write_lab_files` is not allowed to skip the rules), the manifest, and the
    fresh copy each exercise runs in. The snapshot sits outside every
    exercise's sandbox, so one exercise cannot rewrite the lab the next one
    runs, and lab code never writes to the repo.
    """
    directory = Path(directory)
    tmp = Path(tempfile.mkdtemp(prefix="hq-lab-")).resolve()
    try:
        snapshot = tmp / "snapshot"
        try:
            problems = snapshot_lab(directory, snapshot)
        except OSError as exc:
            raise ValueError(f"the lab could not be read: {exc}") from exc
        if problems:
            raise ValueError("the lab was not run: " + "; ".join(problems))
        problems = validate_lab_files(directory.name, read_lab_files(snapshot))
        if problems:
            raise ValueError("the lab does not validate: " + "; ".join(problems))
        if not sandbox_available():
            raise RuntimeError(
                "sandbox-exec is not available on this machine; lab code is never run"
                " outside a sandbox"
            )
        manifest = load_manifest(snapshot)
        cache = tmp / "cache"
        (cache / "gocache").mkdir(parents=True)
        (tmp / "logs").mkdir()
        toolchains = toolchain_paths(tmp)
        return [_run_one(ex, tmp, snapshot, cache, toolchains)
                for ex in manifest["exercises"]]
    finally:
        shutil.rmtree(tmp, onexc=_force_remove)


def summarize(results: list[ExerciseResult]) -> dict[str, int]:
    return {
        "passed": sum(r.status == "pass" for r in results),
        "failed": sum(r.status == "fail" for r in results),
        "manual": sum(r.status == "manual" for r in results),
    }


def _atomic_write(path: Path, text: str) -> None:
    staging = path.with_name(f".{path.name}.tmp")
    staging.write_text(text, encoding="utf-8")
    staging.replace(path)


def write_results(directory: Path, results: list[ExerciseResult]) -> Path:
    """RESULTS.md for him and the reviewer, RESULTS.json for record_review."""
    ran_at = datetime.now(UTC).astimezone(ZoneInfo(settings().cron_tz))
    counts = summarize(results)
    lines = [
        f"# Lab results: {directory.name}",
        "",
        f"ran: {ran_at.isoformat(timespec='seconds')}",
        f"passed {counts['passed']} · failed {counts['failed']} · manual {counts['manual']}",
    ]
    for r in results:
        lines += ["", f"## {r.id}: {r.title} ({r.kind}): {r.status}"]
        if r.reason:
            lines += ["", r.reason]
        if r.output:
            fence = "````" if "```" in r.output else "```"
            lines += ["", f"{fence}text", r.output.rstrip("\n"), fence]
    _atomic_write(directory / RESULTS_JSON, json.dumps(
        {"ran_at": ran_at.isoformat(), **counts,
         "results": [r.to_dict() for r in results]}, indent=2))
    md = directory / RESULTS_MD
    _atomic_write(md, "\n".join(lines) + "\n")
    return md


def read_results(directory: Path) -> dict[str, Any] | None:
    path = directory / RESULTS_JSON
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


# --- deterministic lesson checks ----------------------------------------------

IDIOMS = ("chew through", "spin up", "spinning up", "under the hood", "boils down to",
          "bit me", "a fast thing")
MIN_EXERCISES = 7
MIN_BREAK_EXERCISES = 2
MAX_JUST = 3
MAX_PROSE_RUN = 5
_URL_RE = re.compile(r"https?://[^\s<>\"'`\[\]()]+")
_URL_TRAILING = ".,/;:!?*"
# A lab's own service is not a source. `curl http://localhost:8080/` in a
# worked example has nothing to cite.
_LOCAL_HOSTS = frozenset({"localhost", "127.0.0.1", "0.0.0.0", "::1",
                          "example.com", "example.org", "example.net"})
_NOT_VERIFIED_RE = re.compile(r"^#{1,6}\s.*could not verify", re.IGNORECASE | re.MULTILINE)
_LIST_RE = re.compile(r"^([-*+]|\d+[.)])\s")


def _finding(check: str, severity: str, where: str, problem: str, fix: str) -> dict[str, str]:
    return {"check": check, "severity": severity, "where": where,
            "problem": problem, "fix": fix}


def _normalise_url(url: str) -> str:
    return url.rstrip(_URL_TRAILING)


def _urls(text: str) -> list[str]:
    seen: list[str] = []
    for match in _URL_RE.findall(text):
        url = _normalise_url(match)
        if url and url not in seen:
            seen.append(url)
    return seen


def _is_local(url: str) -> bool:
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return False
    return host in _LOCAL_HOSTS


def _prose_runs(markdown: str) -> list[tuple[str, int]]:
    """Runs of more than MAX_PROSE_RUN prose paragraphs with no code block or
    diagram between them, as (heading the run starts under, length).

    Headings, lists, tables and quotes neither count nor break a run: a wall
    of prose with sub-headings in it is still a wall."""
    runs: list[tuple[str, int]] = []
    heading = "(top of the lesson)"
    run, run_where = 0, heading
    in_fence, fence, in_block = False, "", False

    def close_run() -> None:
        nonlocal run
        if run > MAX_PROSE_RUN:
            runs.append((run_where, run))
        run = 0

    for line in [*markdown.splitlines(), ""]:
        s = line.strip()
        if in_fence:
            if s.startswith(fence):
                in_fence = False
            continue
        if s.startswith(("```", "~~~")):
            close_run()
            in_fence, fence, in_block = True, s[:3], False
            continue
        if not s:
            in_block = False
            continue
        if in_block:
            continue
        in_block = True
        if s.startswith("#"):
            heading = s.lstrip("#").strip()
        elif s.startswith(("<svg", "<figure", "<img", "![")):
            close_run()
        elif s.startswith(("|", ">", "<")) or _LIST_RE.match(s):
            continue
        else:
            if run == 0:
                run_where = heading
            run += 1
    close_run()
    return runs


def check_phase_text(
    lesson_md: str,
    lesson_html: str,
    note_text: str,
    spec_sections: list[str],
    spec_numbers: list[str],
    manifest: dict[str, Any] | None,
    lab_expected: bool = True,
) -> list[dict[str, str]]:
    """The checks a reviewer should never have to do by eye.

    Each finding is {check, severity, where, problem, fix}. `block` means the
    phase cannot pass while it stands; `warn` is for the reviewer to weigh.
    """
    # Late import: learning_tools imports the tool registry and DBOS, which
    # this module has no other reason to load.
    from hq.tools.learning_tools import page_shortfall

    findings: list[dict[str, str]] = []

    # Spec coverage. The course-phase skill makes the spec a contract, and a
    # dropped section is the one loss nobody notices from inside the lesson.
    for i, number in enumerate(spec_numbers):
        pattern = re.compile(rf"^#{{2,4}}\s.*(?<![\d.]){re.escape(number)}(?!\d)", re.MULTILINE)
        if not pattern.search(lesson_md):
            title = spec_sections[i] if i < len(spec_sections) else ""
            findings.append(_finding(
                "spec coverage", "block", f"spec section {number}",
                f"no heading carries section {number}" + (f" ({title})" if title else ""),
                f"add a `## {number} {title}`-style heading and teach that section under it",
            ))

    # URL provenance. Every link he is allowed to follow was read by hunter
    # and lives in the study note; a url that is not there was remembered, and
    # remembered links are the stale links the inference review found.
    if not note_text.strip():
        findings.append(_finding(
            "url provenance", "block", "study note",
            "no study note found for this phase, so no claim or link can be checked",
            "hunter must study the phase and file its note before the lesson is reviewed",
        ))
    else:
        note_urls = set(_urls(note_text))
        unsourced = [u for u in _urls(lesson_md)
                     if not _is_local(u) and u not in note_urls and u not in note_text]
        for url in unsourced[:20]:
            findings.append(_finding(
                "url provenance", "block", "lesson.md", f"{url} is not in the study note",
                "cite only urls from the study note, or remove the link",
            ))
        if len(unsourced) > 20:
            findings.append(_finding(
                "url provenance", "block", "lesson.md",
                f"{len(unsourced) - 20} more unsourced urls not listed",
                "cite only urls from the study note",
            ))

    shortfall = page_shortfall(lesson_md, lesson_html)
    if shortfall:
        findings.append(_finding("page completeness", "block", "lesson.html", shortfall,
                                 "rewrite the page so it carries every section"))

    if not _NOT_VERIFIED_RE.search(lesson_md):
        findings.append(_finding(
            "not-verified section", "block", "lesson.md",
            "no section headed 'could not verify'",
            "add a section headed 'What I could not verify' listing claims the study"
            " note could not confirm, or saying there were none",
        ))

    # Exercises.
    if manifest is None:
        findings.append(_finding(
            "exercises", "block" if lab_expected else "warn", MANIFEST,
            "no lab manifest for this phase",
            "write the lab with write_lab_files" if lab_expected
            else "the spec has no lab; confirm the phase really needs none",
        ))
    else:
        exercises = [e for e in manifest.get("exercises") or [] if isinstance(e, dict)]
        auto = [e for e in exercises if e.get("verify", "auto") == "auto"]
        if lab_expected and not auto:
            # record_review refuses a pass over a failed exercise. A lab of
            # only manual exercises has none that can fail, so without this it
            # would pass having proved nothing runs.
            findings.append(_finding(
                "exercises", "block", MANIFEST,
                f"none of the {len(exercises)} exercises is verify: auto, so run_lab"
                " checks nothing",
                "make every exercise that runs with the standard library and no network"
                " verify: auto",
            ))
        if len(exercises) < MIN_EXERCISES:
            findings.append(_finding(
                "exercises", "warn", MANIFEST,
                f"{len(exercises)} exercises; a phase should have at least {MIN_EXERCISES}",
                "add exercises until the lab covers every section that has a mechanism",
            ))
        breaks = sum(e.get("kind") == "break" for e in exercises)
        if breaks < MIN_BREAK_EXERCISES:
            findings.append(_finding(
                "exercises", "warn", MANIFEST,
                f"{breaks} exercises of kind 'break'; at least {MIN_BREAK_EXERCISES}",
                "add exercises that break the mechanism on purpose and show the failure",
            ))
        lesson_text = f"{lesson_md}\n{lesson_html}"
        for e in exercises:
            ex_id = str(e.get("id") or "")
            if ex_id and not re.search(rf"\b{re.escape(ex_id)}\b", lesson_text):
                findings.append(_finding(
                    "exercises", "warn", ex_id,
                    f"exercise {ex_id} is never mentioned in the lesson",
                    f"point to {ex_id} from the section it exercises",
                ))

    lowered = lesson_md.lower()
    for word in ("simply", "easily"):
        count = len(re.findall(rf"\b{word}\b", lowered))
        if count:
            findings.append(_finding(
                "banned words", "warn", "lesson.md", f"'{word}' appears {count} time(s)",
                f"delete '{word}'; if the step is not simple, the word is false",
            ))
    just = len(re.findall(r"\bjust\b", lowered))
    if just > MAX_JUST:
        findings.append(_finding(
            "banned words", "warn", "lesson.md", f"'just' appears {just} times",
            "cut 'just' where it minimises a step",
        ))

    for idiom in IDIOMS:
        count = lowered.count(idiom)
        if count:
            findings.append(_finding(
                "idioms", "warn", "lesson.md", f"idiom '{idiom}' appears {count} time(s)",
                "say the literal thing instead",
            ))

    for where, length in _prose_runs(lesson_md):
        findings.append(_finding(
            "diagram density", "warn", f"lesson.md, under '{where}'",
            f"{length} prose paragraphs in a row with no code block or diagram",
            "break the run with a code block, a traced example or a diagram",
        ))
    return findings
