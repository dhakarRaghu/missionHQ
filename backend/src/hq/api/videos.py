"""Making a narrated video of a lesson, when he asks for one.

POST /videos/make           "Generate video": make a lesson's video (course phase or article)
GET  /videos/jobs           every video job and its state
GET  /videos/jobs/{id}      one job: plan, narration, reviews, what is still open
GET  /videos/jobs/{id}/sheet  the contact sheet of the stills (JPEG), after the build

Nothing starts a video by itself: "make" is the only start (hq.video.jobs).
There is no approval step after it: a clean script goes straight to the render.

Finished videos are served by the media router (`api/media.py`).
"""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from hq.api.deps import require_auth
from hq.learning_pipeline import LESSON_DIR
from hq.video import MODES, jobs, paths
from hq.video.script import load_job

router = APIRouter(prefix="/videos", dependencies=[Depends(require_auth)])


class MakeVideo(BaseModel):
    lesson_md: str = Field(description="learning/lessons/<date>-<slug>.md")
    mode: str = "course"
    fresh: bool = Field(default=False, description=(
        "write a new script even when the stopped job's checked script could be built again"))


async def _job_or_404(video_id: str) -> Any:
    if not paths.valid_id(video_id):
        raise HTTPException(400, "bad video id")
    job = load_job(video_id)
    if job is None:
        raise HTTPException(404, f"no video job {video_id!r}")
    return await jobs.settle(job)


@router.post("/make", operation_id="makeVideo")
async def make_video(body: MakeVideo) -> dict[str, Any]:
    if body.mode not in MODES:
        raise HTTPException(400, f"mode is one of {list(MODES)}")
    if not body.lesson_md.startswith(f"{LESSON_DIR}/") or not body.lesson_md.endswith(".md") \
            or ".." in body.lesson_md:
        raise HTTPException(400, "lesson_md must be a learning/lessons/*.md path")
    return await jobs.start(body.lesson_md, body.mode, source="web", fresh=body.fresh)


@router.get("/jobs", operation_id="listVideoJobs")
async def list_jobs() -> list[dict[str, Any]]:
    root = paths.work_root()
    if not root.is_dir():
        return []
    out = []
    for folder in sorted(root.iterdir()):
        job = load_job(folder.name) if paths.valid_id(folder.name) else None
        if job:
            state = await jobs.shown_state(job)
            row = job.model_dump(include={"id", "mode", "title", "lesson_md",
                                          "course", "duration_s", "updated"})
            row["state"] = state
            # The script's spoken length, before a render exists.
            row["minutes"] = (job.review or {}).get("minutes")
            row["can_rebuild"] = jobs.can_rebuild(job)
            out.append(row)
    return sorted(out, key=lambda j: j.get("updated") or "", reverse=True)


@router.get("/jobs/{video_id}", operation_id="getVideoJob")
async def get_job(video_id: str) -> dict[str, Any]:
    job = await _job_or_404(video_id)
    folder = paths.work_dir(video_id)

    def read(name: str) -> Any:
        path = folder / name
        return json.loads(path.read_text()) if path.is_file() else None

    return {"job": {**job.model_dump(), "state": await jobs.shown_state(job)},
            "can_rebuild": jobs.can_rebuild(job),
            "plan": read("plan.json"),
            "narration": read("narration.json"), "review": read("review.json"),
            "has_sheet": (folder / "sheet.jpg").is_file()}


@router.get("/jobs/{video_id}/sheet", operation_id="getVideoSheet")
async def get_sheet(video_id: str) -> FileResponse:
    await _job_or_404(video_id)
    path = paths.work_dir(video_id) / "sheet.jpg"
    if not path.is_file():
        raise HTTPException(404, "no contact sheet yet")
    return FileResponse(path, media_type="image/jpeg")
