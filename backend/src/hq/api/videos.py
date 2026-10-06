"""Making a narrated video of a lesson, and the owner's two decisions on it.

POST /videos/make           start the script for a lesson (course phase or article)
GET  /videos/jobs           every video job and its state
GET  /videos/jobs/{id}      one job: plan, narration, reviews, what is still open
GET  /videos/jobs/{id}/sheet  the contact sheet of the stills (JPEG), after the build

There is no approval step: a written lesson starts its video on its own
(engine._start_lesson_video), and a clean script goes straight to the render.
"make" is for a lesson written before videos existed, or to try again.

Finished videos are served by the media router (`api/media.py`).
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from hq import db
from hq.api.deps import require_auth
from hq.learning_pipeline import LESSON_DIR
from hq.video import MODES, SCRIPT_STAGE, paths
from hq.video.script import load_job, video_id_for

router = APIRouter(prefix="/videos", dependencies=[Depends(require_auth)])


class MakeVideo(BaseModel):
    lesson_md: str = Field(description="learning/lessons/<date>-<slug>.md")
    mode: str = "course"


def _job_or_404(video_id: str) -> Any:
    if not paths.valid_id(video_id):
        raise HTTPException(400, "bad video id")
    job = load_job(video_id)
    if job is None:
        raise HTTPException(404, f"no video job {video_id!r}")
    return job


async def _live_task(video_id: str) -> str | None:
    row = await db.fetchone(
        "SELECT id::text FROM hq.tasks WHERE dedup_key LIKE %s"
        " AND status IN ('backlog', 'queued', 'running', 'needs_approval') LIMIT 1",
        (f"video:{video_id}:%",))
    return str(row["id"]) if row else None


async def _dispatch(video_id: str, stage: str, title: str, payload: dict[str, Any]) -> str:
    import uuid

    from hq import engine

    return await engine.dispatch(
        agent="tutor", title=title, source="web",
        brief="A narrated video of a finished lesson (hq.video).",
        payload={"stage": stage, "video_id": video_id, **payload},
        dedup_key=f"video:{video_id}:{stage}:{uuid.uuid4().hex[:8]}")


@router.post("/make", operation_id="makeVideo")
async def make_video(body: MakeVideo) -> dict[str, Any]:
    if body.mode not in MODES:
        raise HTTPException(400, f"mode is one of {list(MODES)}")
    if not body.lesson_md.startswith(f"{LESSON_DIR}/") or not body.lesson_md.endswith(".md") \
            or ".." in body.lesson_md:
        raise HTTPException(400, "lesson_md must be a learning/lessons/*.md path")
    video_id = video_id_for(body.lesson_md)
    if live := await _live_task(video_id):
        return {"started": False, "video_id": video_id, "task_id": live,
                "reason": "a task for this video is already running"}
    task_id = await _dispatch(video_id, SCRIPT_STAGE, f"Video script: {video_id}",
                              {"lesson_md": body.lesson_md, "mode": body.mode})
    return {"started": True, "video_id": video_id, "task_id": task_id}


@router.get("/jobs", operation_id="listVideoJobs")
async def list_jobs() -> list[dict[str, Any]]:
    root = paths.work_root()
    if not root.is_dir():
        return []
    out = []
    for folder in sorted(root.iterdir()):
        job = load_job(folder.name) if paths.valid_id(folder.name) else None
        if job:
            row = job.model_dump(include={"id", "mode", "title", "state", "lesson_md",
                                          "course", "duration_s", "updated"})
            # The script's spoken length, before a render exists.
            row["minutes"] = (job.review or {}).get("minutes")
            out.append(row)
    return sorted(out, key=lambda j: j.get("updated") or "", reverse=True)


@router.get("/jobs/{video_id}", operation_id="getVideoJob")
async def get_job(video_id: str) -> dict[str, Any]:
    job = _job_or_404(video_id)
    folder = paths.work_dir(video_id)

    def read(name: str) -> Any:
        path = folder / name
        return json.loads(path.read_text()) if path.is_file() else None

    return {"job": job.model_dump(), "plan": read("plan.json"),
            "narration": read("narration.json"), "review": read("review.json"),
            "has_sheet": (folder / "sheet.jpg").is_file()}


@router.get("/jobs/{video_id}/sheet", operation_id="getVideoSheet")
async def get_sheet(video_id: str) -> FileResponse:
    _job_or_404(video_id)
    path = paths.work_dir(video_id) / "sheet.jpg"
    if not path.is_file():
        raise HTTPException(404, "no contact sheet yet")
    return FileResponse(path, media_type="image/jpeg")
