"""A video task queued again after the host slept picks up where it stopped (2026-10-14).

The laptop slept through three video tasks from 2026-10-11 to 10-13. The
watchdog queued each again as a new workflow, which has no record of the old
steps: the phase-05a script wrote its plan and 62 beats a second time, and a
build started its long steps again while the old render was still running.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from pathlib import Path
from typing import Any

import pytest

from hq.video import build, pipeline
from hq.video.models import VideoJob
from hq.video.script import save_job, saved_script

VID = "some-lesson"
TASK = "0d6f6a52-6f8e-4d3c-9a57-1f1f2c3b4a5d"


@pytest.fixture
def work(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("VIDEO_WORK_DIR", str(tmp_path))
    folder = tmp_path / VID
    folder.mkdir()
    (folder / "spec.json").write_text('{"beats": []}')
    (folder / f"{VID}.timing.json").write_text('{"version": 2}')
    return folder


def _record(folder: Path, phase: str, fp: str, pid: int = 0, done: str | None = None) -> None:
    (folder / f"{phase}.run.json").write_text(json.dumps({"fp": fp, "pid": pid}))
    if done is not None:
        (folder / f"{phase}.done").write_text(done + "\n")


def test_a_step_that_finished_on_the_same_inputs_is_skipped(work) -> None:
    state, fp = build.process_state(VID, "render", "render it")
    assert state == "start"
    _record(work, "render", fp, done="0")
    assert build.process_state(VID, "render", "render it") == ("done", fp)
    # A redrawn scene changes the spec, so the render runs again.
    (work / "spec.json").write_text('{"beats": [1]}')
    assert build.process_state(VID, "render", "render it")[0] == "start"


def test_a_step_that_failed_runs_again(work) -> None:
    _, fp = build.process_state(VID, "stills", "stills")
    _record(work, "stills", fp, done="1")
    assert build.process_state(VID, "stills", "stills")[0] == "start"


def test_a_step_still_running_is_polled_not_started_twice(work) -> None:
    _, fp = build.process_state(VID, "render", "render it")
    proc = subprocess.Popen(["bash", "-c", f"sleep 30; echo {VID}"])
    for _ in range(100):  # until the fork has become bash, which ps then shows
        if build._alive(proc.pid, VID):
            break
        time.sleep(0.02)
    try:
        _record(work, "render", fp, pid=proc.pid)
        assert build.process_state(VID, "render", "render it")[0] == "running"
    finally:
        proc.kill()
        proc.wait()
    assert build.process_state(VID, "render", "render it")[0] == "start"


def test_another_process_with_the_same_pid_is_not_taken_for_ours(work) -> None:
    _, fp = build.process_state(VID, "render", "render it")
    _record(work, "render", fp, pid=os.getpid())  # alive, but not this video's
    assert build.process_state(VID, "render", "render it")[0] == "start"


def test_a_long_step_holds_the_mac_awake_and_records_itself(work, monkeypatch) -> None:
    seen: list[list[str]] = []

    class Proc:
        pid = 4242

    def popen(argv: list[str], **_: Any) -> Proc:
        seen.append(argv)
        return Proc()

    monkeypatch.setattr(build.subprocess, "Popen", popen)
    monkeypatch.setattr(build.paths, "project_dir", lambda: work)
    monkeypatch.setattr(build, "_env", dict)
    build._spawn(VID, "render", "render it", "abc")
    if Path(build.CAFFEINATE).is_file():
        assert seen[0][:2] == [build.CAFFEINATE, "-i"]
    assert seen[0][-3:-1] == ["bash", "-c"]
    assert json.loads((work / "render.run.json").read_text()) == {"fp": "abc", "pid": 4242}


def test_a_frame_review_that_passed_on_this_spec_is_not_repeated(work) -> None:
    assert not build.frames_passed(VID)
    (work / "frames.ok").write_text(build._spec_hash(VID) + "\n")
    assert build.frames_passed(VID)
    (work / "spec.json").write_text('{"beats": ["redrawn"]}')
    assert not build.frames_passed(VID)


def _writing(work: Path, **extra: Any) -> None:
    save_job(VideoJob(id=VID, mode="course", lesson_md="learning/lessons/x.md",
                      script_task_id=TASK, **extra))
    (work / "plan.json").write_text(json.dumps({"title": "t"}))
    (work / "narration.json").write_text(json.dumps(
        {"beats": {"cold": {"lines": [{"key": "c0", "text": "A line."}]}}}))


def test_the_same_task_resumes_its_script(work) -> None:
    _writing(work, state="writing", stages=["plan", "beats"])
    saved = saved_script(VID, TASK)
    assert saved is not None
    assert saved["job"]["stages"] == ["plan", "beats"]
    assert saved["plan"] == {"title": "t"}
    assert saved["beats"]["cold"]["lines"][0]["key"] == "c0"


def test_another_task_or_a_finished_script_starts_anew(work) -> None:
    _writing(work, state="writing", stages=["plan"])
    assert saved_script(VID, "another-task") is None
    _writing(work, state="failed", stages=["plan", "beats"])
    assert saved_script(VID, TASK) is None
    _writing(work, state="writing", stages=[])  # stopped before its plan was saved
    assert saved_script(VID, TASK) is None


def test_a_video_task_holds_idle_sleep_off_and_lets_go(monkeypatch) -> None:
    calls: list[list[str]] = []
    ended: list[bool] = []

    class Proc:
        def terminate(self) -> None:
            ended.append(True)

    def popen(argv: list[str], **_: Any) -> Proc:
        calls.append(argv)
        return Proc()

    monkeypatch.setattr(pipeline.subprocess, "Popen", popen)
    with pipeline.awake():
        assert calls[0][:2] == [build.CAFFEINATE, "-i"]
        assert calls[0][2:] == ["-w", str(os.getpid())]
        assert not ended
    assert ended == [True]


def test_a_failed_build_forgets_its_render_so_build_again_renders(work) -> None:
    # verify always exits 0, so a rebuild found render and verify "done" on the
    # same inputs and read the same failing report for ever.
    for phase in ("narrate", "render", "verify"):
        _, fp = build.process_state(VID, phase, phase)
        _record(work, phase, fp, done="0")
    (work / "frames.ok").write_text(build._spec_hash(VID) + "\n")
    build.forget(VID)
    assert build.process_state(VID, "render", "render")[0] == "start"
    assert build.process_state(VID, "verify", "verify")[0] == "start"
    assert not build.frames_passed(VID)
    assert build.process_state(VID, "narrate", "narrate")[0] == "done"  # the voice is kept


def test_a_template_fixed_since_draws_again(work, tmp_path, monkeypatch) -> None:
    project = tmp_path / "project"
    (project / "src").mkdir(parents=True)
    template = project / "src" / "concept.tsx"
    template.write_text("v1")
    monkeypatch.setattr(build.paths, "project_dir", lambda: project)
    _, fp = build.process_state(VID, "render", "render")
    _record(work, "render", fp, done="0")
    assert build.process_state(VID, "render", "render")[0] == "done"
    later = template.stat().st_mtime + 5
    os.utime(template, (later, later))
    assert build.process_state(VID, "render", "render")[0] == "start"
