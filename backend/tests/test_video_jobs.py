"""A video starts only when he asks, and a job never claims work no task is doing (2026-10-11)."""

from __future__ import annotations

import asyncio
import inspect
import json
import os
from pathlib import Path
from typing import Any

import pytest

from hq import engine
from hq.video import BUILD_STAGE, SCRIPT_STAGE, build, jobs
from hq.video.models import VideoJob
from hq.video.script import load_job, save_job

TASK = "0d6f6a52-6f8e-4d3c-9a57-1f1f2c3b4a5d"
LESSON = "learning/lessons/2026-10-10-some-lesson.md"


@pytest.fixture
def work(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("VIDEO_WORK_DIR", str(tmp_path))
    return tmp_path


def _board(monkeypatch: pytest.MonkeyPatch, *, live: str | None, run: dict | None) -> list:
    """A stand-in task board: one live task or none, and the last run of a task."""
    dispatched: list[dict[str, Any]] = []

    async def fetchone(sql: str, params: tuple = ()) -> dict | None:
        if "FROM hq.tasks" in sql:
            return {"id": live} if live else None
        if "FROM hq.runs" in sql:
            return run
        raise AssertionError(sql)

    async def dispatch(**kwargs: Any) -> str:
        dispatched.append(kwargs)
        return "new-task"

    monkeypatch.setattr(jobs.db, "fetchone", fetchone)
    monkeypatch.setattr(engine, "dispatch", dispatch)
    return dispatched


def _job(state: str, **extra: Any) -> VideoJob:
    job = VideoJob(id="some-lesson", mode="course", lesson_md=LESSON, state=state,
                   script_task_id=TASK, **extra)
    save_job(job)
    return job


def test_a_job_whose_task_died_reads_as_failed_with_its_error(work, monkeypatch) -> None:
    # Six jobs said "writing" for days: check-spec could not find node, the
    # task failed, and nothing wrote the job file again.
    _board(monkeypatch, live=None,
           run={"outcome": "failed", "error": "[Errno 2] No such file or directory: 'node'"})
    job = asyncio.run(jobs.settle(_job("writing")))
    assert job.state == "failed"
    assert "No such file or directory" in job.report[-1]
    assert load_job("some-lesson").state == "failed"  # written back, said once


def test_a_lost_build_keeps_its_checked_script(work, monkeypatch) -> None:
    _board(monkeypatch, live=None, run=None)
    _checked_script(work / "some-lesson")
    job = asyncio.run(jobs.settle(_job("approved")))
    assert job.state == "script_ready" and jobs.can_rebuild(job)


def test_a_job_with_a_live_task_is_left_alone(work, monkeypatch) -> None:
    _board(monkeypatch, live="running-task", run=None)
    assert asyncio.run(jobs.settle(_job("writing"))).state == "writing"


def test_a_build_by_hand_is_not_settled(work, monkeypatch) -> None:
    _board(monkeypatch, live=None, run=None)
    job = _job("building", build_task_id="by-hand")
    assert asyncio.run(jobs.settle(job)).state == "building"


def _checked_script(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "narration.json").write_text("{}")
    (folder / "spec.json").write_text("{}")


def test_a_failed_build_is_built_again_from_its_checked_script(work, monkeypatch) -> None:
    sent = _board(monkeypatch, live=None, run=None)
    _job("failed", build_task_id=TASK)
    _checked_script(work / "some-lesson")
    out = asyncio.run(jobs.start(LESSON, "course", source="web"))
    assert out["started"] and out["stage"] == "build"
    assert sent[0]["payload"]["stage"] == BUILD_STAGE


def test_fresh_or_a_stopped_script_writes_the_script_again(work, monkeypatch) -> None:
    sent = _board(monkeypatch, live=None, run=None)
    _job("failed", build_task_id=TASK)
    _checked_script(work / "some-lesson")
    asyncio.run(jobs.start(LESSON, "course", source="web", fresh=True))
    # A script that stopped at its own checks never had a build.
    _job("failed")
    asyncio.run(jobs.start(LESSON, "course", source="web"))
    assert [s["payload"]["stage"] for s in sent] == [SCRIPT_STAGE, SCRIPT_STAGE]
    assert sent[0]["payload"]["lesson_md"] == LESSON


def test_a_video_being_made_is_not_started_twice(work, monkeypatch) -> None:
    sent = _board(monkeypatch, live="running-task", run=None)
    out = asyncio.run(jobs.start(LESSON, "course", source="web"))
    assert not out["started"] and out["task_id"] == "running-task" and not sent


def test_nothing_starts_a_video_by_itself() -> None:
    assert not [d for d in engine.SYSTEM_DISPATCHES if "video" in d[0]]
    chain = inspect.getsource(engine._advance_learning)
    assert "SCRIPT_STAGE" not in chain and "video_id" not in chain


def test_an_old_voice_is_made_again(work) -> None:
    # Timing version 1 summed per-line MP3 lengths and ran up to a second ahead.
    folder = work / "some-lesson"
    folder.mkdir()
    (folder / "narration.json").write_text("{}")
    (folder / "narrate.done").write_text("0\n")
    timing = folder / "some-lesson.timing.json"
    timing.write_text(json.dumps({"version": 1}))
    later = os.stat(folder / "narration.json").st_mtime + 5
    os.utime(timing, (later, later))
    assert not build._voice_is_current("some-lesson")
    timing.write_text(json.dumps({"version": 2}))
    os.utime(timing, (later, later))
    assert build._voice_is_current("some-lesson")
