"""Starting a video when he asks, and a job's state as it really is.

Nothing starts a video by itself. "Generate video" on a phase or an article
(POST /videos/make) and sage's `start_video` in chat both come through
`start`, so the two can never disagree about what a press does:

- a video already being made is left alone;
- a job whose script passed every check and review, and whose build then
  stopped (a failed render check, a frame review, a crash), is built again
  from that script, which saves the hours of writing and reviewing;
- anything else writes the script from the lesson, then builds it.

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
from hq.video import BUILD_STAGE, SCRIPT_STAGE, paths
from hq.video.models import VideoJob

LIVE_TASK = ("backlog", "queued", "running", "needs_approval")
# The states in which the file says a task is working on the job.
ACTIVE = ("writing", "approved", "building")
BRIEF = "A narrated video of a finished lesson (hq.video)."


async def live_task(video_id: str) -> str | None:
    """The task making this video now, whichever way it was started."""
    row = await db.fetchone(
        "SELECT id::text FROM hq.tasks WHERE payload->>'video_id' = %s"
        " AND status = ANY(%s) ORDER BY created_at DESC LIMIT 1",
        (video_id, list(LIVE_TASK)))
    return str(row["id"]) if row else None


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


async def start(lesson_md: str, mode: str, *, source: str, fresh: bool = False,
                parent_task_id: str | None = None, attempt: str = "") -> dict[str, Any]:
    """Make the video of one lesson. `fresh` writes a new script even when the
    last one could be built again. `attempt` makes the task's dedup key stable
    for one request (a chat run's id); a press of the button is its own."""
    from hq import engine
    from hq.video.script import load_job, video_id_for

    video_id = video_id_for(lesson_md)
    if live := await live_task(video_id):
        return {"started": False, "video_id": video_id, "task_id": live, "stage": "",
                "reason": "this video is already being made"}
    job = load_job(video_id)
    if job:
        job = await settle(job)
    build = job is not None and not fresh and can_rebuild(job)
    if build:
        assert job is not None
        stage, title = BUILD_STAGE, f"Video build: {job.title or video_id}"
        payload: dict[str, Any] = {"stage": stage, "video_id": video_id, "scale": 1}
    else:
        stage, title = SCRIPT_STAGE, f"Video script: {video_id}"
        payload = {"stage": stage, "video_id": video_id, "lesson_md": lesson_md, "mode": mode}
    task_id = await engine.dispatch(
        agent="tutor", title=title, brief=BRIEF, source=source,
        parent_task_id=parent_task_id, payload=payload,
        dedup_key=f"video:{video_id}:{stage}:{attempt or uuid.uuid4().hex[:8]}")
    return {"started": True, "video_id": video_id, "task_id": task_id,
            "stage": "build" if build else "script"}
