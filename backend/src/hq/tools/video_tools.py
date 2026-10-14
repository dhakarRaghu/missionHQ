"""Tools for narrated lesson videos (hq.video).

A video is made only when the owner asks: "Generate video" on the page, or
in chat, where sage calls `start_video`. The pipeline then runs on its own: a
script that passes every check is voiced and rendered.
"""

from __future__ import annotations

from pydantic_ai import ModelRetry, RunContext

from hq import db
from hq.learning_pipeline import LESSON_DIR
from hq.safety import ActionClass
from hq.tools.registry import HQDeps, hq_tool
from hq.video import MODES


@hq_tool(action=ActionClass.READ)
async def start_video(ctx: RunContext[HQDeps], lesson: str, mode: str = "") -> str:
    """Start writing a narrated video of one finished lesson.

    `lesson` is the lesson's title or its learning/lessons/*.md path. `mode`
    is "course" for a course phase or "article" for a Learn article; leave it
    empty to take it from the lesson. It runs to a finished video with no
    approval step, unless a check stops it. A video whose build stopped is
    built again from its checked script.
    """
    from hq.video import jobs  # late import: hq.video.script imports the tools package

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
    result = await jobs.start(md, mode, source="agent", parent_task_id=ctx.deps.task_id,
                              attempt=ctx.deps.run_id or "")
    if not result["started"]:
        return f"The video {result['video_id']} is already being made (task {result['task_id']})."
    what = ("Building it again from its checked script" if result["stage"] == "build"
            else "Writing its script")
    return (f"{what}: the {mode} video of {md} (task {result['task_id']}). It runs to a"
            " finished video by itself; Courses → Videos shows how far it got.")
