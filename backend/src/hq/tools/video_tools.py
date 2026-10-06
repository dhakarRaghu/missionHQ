"""Tools for narrated lesson videos (hq.video).

Videos start by themselves when a lesson is written. Sage can start one for
an older lesson when the owner asks in chat. The pipeline then runs on its
own: a script that passes every check is voiced and rendered.
"""

from __future__ import annotations

from pydantic_ai import ModelRetry, RunContext

from hq import db
from hq.learning_pipeline import LESSON_DIR
from hq.safety import ActionClass
from hq.tools.registry import HQDeps, hq_tool
from hq.video import MODES, SCRIPT_STAGE


@hq_tool(action=ActionClass.READ)
async def start_video(ctx: RunContext[HQDeps], lesson: str, mode: str = "") -> str:
    """Start writing a narrated video of one finished lesson.

    `lesson` is the lesson's title or its learning/lessons/*.md path. `mode`
    is "course" for a course phase or "article" for a Learn article; leave it
    empty to take it from the lesson. It runs to a finished video with no
    approval step, unless a check stops it.
    """
    from hq import engine  # late imports: hq.video.script imports the tools package
    from hq.video.script import load_job, video_id_for

    if lesson.startswith(f"{LESSON_DIR}/") and lesson.endswith(".md"):
        row = await db.fetchone("SELECT md_path, kind FROM hq.lessons WHERE md_path = %s",
                                (lesson,))
    else:
        row = await db.fetchone(
            "SELECT md_path, kind FROM hq.lessons WHERE title ILIKE %s"
            " ORDER BY lesson_date DESC LIMIT 1", (f"%{lesson.strip()}%",))
    if not row or not row.get("md_path"):
        raise ModelRetry(f"no lesson matches {lesson!r}; use list_lessons to find its title")
    md = str(row["md_path"])
    mode = mode or ("course" if row.get("kind") == "course" else "article")
    if mode not in MODES:
        raise ModelRetry(f"mode is one of {list(MODES)}")
    video_id = video_id_for(md)
    job = load_job(video_id)
    if job and job.state in ("writing", "approved", "building"):
        return f"The video {video_id} is already {job.state}."
    task_id = await engine.dispatch(
        agent="tutor", title=f"Video script: {video_id}", source="agent",
        brief="A narrated video of a finished lesson (hq.video).",
        parent_task_id=ctx.deps.task_id,
        payload={"stage": SCRIPT_STAGE, "video_id": video_id, "lesson_md": md, "mode": mode},
        dedup_key=f"video:{video_id}:{SCRIPT_STAGE}:{ctx.deps.run_id or ''}")
    return (f"Started the {mode} video of {md} (task {task_id}). It runs to a finished video"
            " by itself; Courses → Videos shows how far it got.")


@hq_tool(action=ActionClass.READ)
async def start_next_video(ctx: RunContext[HQDeps]) -> str:
    """Start the video of the oldest lesson that has none (the nightly starter).

    A lesson written by the learning chain starts its video there. This one
    catches the rest: lessons written before videos existed, phases published
    from Claude /study, and videos that stopped. One a night, because a render
    keeps the CPU busy for an hour.
    """
    from hq import engine
    from hq.video import register
    from hq.video.script import load_job, video_id_for

    have = {str(v.get("source_lesson") or "") for v in register.manifest()["videos"]}
    covered = {s for v in register.manifest()["videos"] if v.get("kind") == "course"
               for s in (v.get("phase_slugs") or [v.get("phase_slug")]) if s}
    rows = await db.fetch(
        "SELECT md_path, kind, phase_slug FROM hq.lessons"
        " WHERE kind IN ('course', 'topic') AND md_path <> '' ORDER BY lesson_date", ())
    for row in rows:
        md = str(row["md_path"])
        if md in have or (row["kind"] == "course" and row.get("phase_slug") in covered):
            continue
        job = load_job(video_id_for(md))
        if job is not None:
            continue   # made, running, or stopped: a stopped one is retried by hand
        mode = "course" if row["kind"] == "course" else "article"
        video_id = video_id_for(md)
        task_id = await engine.dispatch(
            agent="tutor", title=f"Video: {video_id}", source="system",
            brief="A narrated video of a finished lesson (hq.video).",
            payload={"stage": SCRIPT_STAGE, "video_id": video_id, "lesson_md": md,
                     "mode": mode},
            dedup_key=f"video-backfill:{video_id}")
        return f"started the {mode} video of {md} (task {task_id})"
    return "every lesson has a video or a job"
