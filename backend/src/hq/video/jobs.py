"""Starting a video when he asks, and a job's state as it really is.

Nothing starts a video by itself. "Generate video" on a phase or an article
(POST /videos/make) and sage's `start_video` in chat both come through
`start`, so the two can never disagree about what a press does:

- a lesson whose video is being made (its series task or any part) is left
  alone;
- a series already planned for the unchanged lesson goes on part by part: a
  built part is kept, a part whose script passed and whose build stopped is
  built again from that script, and any other part writes its script again;
- anything else plans the series anew (`series.py`), which starts its parts.

A video made before series existed (one job for the whole lesson) is still
built again from its checked script when its build stopped.

The job file is written by the task working on it, so a task that dies
without writing (a program missing on this machine, a deploy, a timeout)
leaves it saying "writing" or "building" forever. `settle` compares the file
with the task board and marks such a job failed, with the task's own error.
"""

from __future__ import annotations

import uuid
from typing import Any

from hq import db
from hq.config import REPO_DIR
from hq.video import BUILD_STAGE, SCRIPT_STAGE, SERIES_STAGE, paths
from hq.video.models import VideoJob

LIVE_TASK = ("backlog", "queued", "running", "needs_approval")
# The states in which the file says a task is working on the job.
ACTIVE = ("writing", "approved", "building")
BRIEF = "A narrated video of a finished lesson (hq.video)."


async def live_task(video_id: str, *, parts: bool = True) -> str | None:
    """The task making this video now, whichever way it was started. For a
    series id, also any task making one of its parts, unless `parts` is off."""
    if not parts:
        row = await db.fetchone(
            "SELECT id::text FROM hq.tasks WHERE payload->>'video_id' = %s"
            " AND status = ANY(%s) ORDER BY created_at DESC LIMIT 1",
            (video_id, list(LIVE_TASK)))
        return str(row["id"]) if row else None
    row = await db.fetchone(
        "SELECT id::text FROM hq.tasks WHERE (payload->>'video_id' = %s"
        " OR payload->>'series' = %s) AND status = ANY(%s) ORDER BY created_at DESC LIMIT 1",
        (video_id, video_id, list(LIVE_TASK)))
    return str(row["id"]) if row else None


def _lesson_unchanged(lesson_md: str, since: float) -> bool:
    lesson = REPO_DIR / lesson_md
    return not lesson.is_file() or lesson.stat().st_mtime <= since


async def settle_series(data: dict[str, Any]) -> dict[str, Any]:
    """A series whose planning task ended without saying so is failed."""
    from hq.video.series import save_series

    if data.get("state") != "planning" or not _is_task_id(str(data.get("task_id") or "")):
        return data
    if await live_task(str(data["id"])):
        return data
    data = {**data, "state": "failed",
            "report": [*data.get("report", []),
                       "Stopped while planning the series: its task is no longer running"]}
    save_series(str(data["id"]), data)
    return data


def _is_task_id(value: str) -> bool:
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


async def settle(job: VideoJob) -> VideoJob:
    """The job as it is: one whose task has ended without saying so is failed,
    or, when only its queued build is gone, a checked script to build."""
    from hq.video.script import save_job

    if job.state not in ACTIVE:
        return job
    task_id = job.build_task_id if job.state == "building" else job.script_task_id
    # A run by hand (scripts/video_run.py) has no task to compare with.
    if not _is_task_id(task_id) or await live_task(job.id):
        return job
    if job.state == "approved":
        # The script passed and queued its build, and that build is gone
        # before it began: the script is still good, so it waits to be built.
        job.report = [*job.report, "The queued build never started; the script is kept."]
        job.state = "script_ready"
        save_job(job)
        return job
    run = await db.fetchone(
        "SELECT outcome, error FROM hq.runs WHERE task_id = %s"
        " ORDER BY started_at DESC LIMIT 1", (task_id,))
    why = "its task is no longer running"
    if run:
        why = f"its task ended {run['outcome']}"
        if run.get("error"):
            why += f": {run['error']}"
    stage = "building" if job.state == "building" else "writing the script"
    job.report = [*job.report, f"Stopped while {stage}: {why}"[:1500]]
    job.state = "failed"
    save_job(job)
    return job


async def shown_state(job: VideoJob) -> str:
    """The state the page shows: the file's, or "queued" while a new task for a
    stopped or finished job waits to start and has not written the file yet."""
    job = await settle(job)
    if job.state not in ACTIVE and await live_task(job.id):
        return "queued"
    return job.state


def can_rebuild(job: VideoJob) -> bool:
    """A job whose script is checked and not being built: "script_ready" (a
    script-only run), or a failed build. Its scenes are on disk, and the
    lesson has not changed since the script was written."""
    checked = job.state == "script_ready" or (job.state == "failed" and bool(job.build_task_id))
    if not checked:
        return False
    folder = paths.work_dir(job.id)
    narration, spec = folder / "narration.json", folder / "spec.json"
    if not (narration.is_file() and spec.is_file()):
        return False
    lesson = REPO_DIR / job.lesson_md
    return not lesson.is_file() or lesson.stat().st_mtime <= narration.stat().st_mtime


async def _dispatch(stage: str, title: str, payload: dict[str, Any], *, source: str,
                    parent_task_id: str | None, key: str) -> str:
    from hq import engine

    return await engine.dispatch(
        agent="tutor", title=title, brief=BRIEF, source=source,
        parent_task_id=parent_task_id, payload={"stage": stage, **payload},
        dedup_key=f"video:{payload['video_id']}:{stage}:{key}")


async def start(lesson_md: str, mode: str, *, source: str, fresh: bool = False,
                parent_task_id: str | None = None, attempt: str = "") -> dict[str, Any]:
    """Make the video of one lesson. `fresh` plans and writes everything anew
    even when stopped parts could be built again. `attempt` makes the task's
    dedup key stable for one request (a chat run's id); a press of the button
    is its own."""
    from hq.video.script import load_job, video_id_for
    from hq.video.series import load_series

    series_id = video_id_for(lesson_md)
    key = attempt or uuid.uuid4().hex[:8]
    # The series task itself (or a video made before series); a part still
    # being made is checked on its own below, so a stopped part beside it can
    # still be started again.
    if live := await live_task(series_id, parts=False):
        return {"started": False, "video_id": series_id, "task_id": live, "stage": "",
                "reason": "this video is already being made"}
    series = load_series(series_id)
    folder = paths.work_dir(series_id)
    if (series and series.get("state") == "planned" and not fresh
            and _lesson_unchanged(lesson_md, (folder / "series.json").stat().st_mtime)):
        started: list[tuple[str, str, str]] = []
        busy: list[tuple[str, str]] = []
        for n, vid in enumerate(series["parts"], 1):
            if part_live := await live_task(vid):
                busy.append((vid, part_live))  # its script or its build is queued or running
                continue
            job = load_job(vid)
            if job:
                job = await settle(job)
            if job and job.state == "built":
                continue
            if job and can_rebuild(job):
                tid = await _dispatch(BUILD_STAGE, f"Video build: {job.title or vid}",
                                      {"video_id": vid, "scale": 1, "series": series_id},
                                      source=source,
                                      parent_task_id=parent_task_id, key=key)
                started.append((vid, tid, "build"))
            else:
                tid = await _dispatch(SCRIPT_STAGE, f"Video script: {vid}",
                                      {"video_id": vid, "lesson_md": lesson_md, "mode": mode,
                                       "series": series_id, "part": n}, source=source,
                                      parent_task_id=parent_task_id, key=key)
                started.append((vid, tid, "script"))
        if started:
            vid, tid, stage = started[0]
            return {"started": True, "video_id": vid, "task_id": tid, "stage": stage,
                    "parts": [v for v, _, _ in started]}
        if busy:
            # Nothing stopped, but parts are still being made: planning anew
            # now would write a second series over them.
            return {"started": False, "video_id": busy[0][0], "task_id": busy[0][1],
                    "stage": "", "reason": "this video is already being made"}
        # Every part is built: a press asks for the video again, so plan anew.
    elif not series and not fresh:
        job = load_job(series_id)
        if job:
            job = await settle(job)
        if job is not None and can_rebuild(job):
            tid = await _dispatch(BUILD_STAGE, f"Video build: {job.title or series_id}",
                                  {"video_id": series_id, "scale": 1}, source=source,
                                  parent_task_id=parent_task_id, key=key)
            return {"started": True, "video_id": series_id, "task_id": tid, "stage": "build"}
    tid = await _dispatch(SERIES_STAGE, f"Video series: {series_id}",
                          {"video_id": series_id, "lesson_md": lesson_md, "mode": mode},
                          source=source, parent_task_id=parent_task_id, key=key)
    return {"started": True, "video_id": series_id, "task_id": tid, "stage": "series"}
