"""Run the video pipeline for one lesson by hand, outside the live engine.

The live backend owns the database's DBOS queues and schedules, so a second
backend must never be started to test a video. This script calls the same
stages directly: every model call, check and file is the pipeline's own,
and the job folder is the one the live system would use. Progress events
are not recorded, so a test leaves no rows in the event feed.

    uv run python scripts/video_run.py series <lesson_md> <course|article>  # plan the parts
    uv run python scripts/video_run.py script <lesson_md> [part ...]        # write parts' scripts
    uv run python scripts/video_run.py repair <video_id>   # editor + facts + scenes again
    uv run python scripts/video_run.py scenes <video_id>   # scenes again only
    uv run python scripts/video_run.py build <video_id> [1|2] [--keep-page]

`series` plans the lesson's parts and starts nothing; `script` writes the
named parts (all of them when none are named) one after another, and stops
before the build (VIDEO_AUTO_BUILD=0); run `build` on a part's video id
(`<lesson>-p<n>`) after reading its review.json. `--keep-page` builds and
checks the video in its job folder but does not publish it, so the Courses
page keeps what it shows.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from typing import Any

os.environ.setdefault("VIDEO_AUTO_BUILD", "0")

from hq import db, runner
from hq.dbos_app import DBOS
from hq.video import build, checks, script, series
from hq.video.models import Line, VideoPlan


async def _no_event(*_a: Any, **_k: Any) -> int:
    return 0


class Deps:
    run_id = None
    task_id = None


def _writer(vid: str, m: dict[str, Any]) -> script.ScriptWriter:
    job = script.load_job(vid)
    assert job is not None, f"no job {vid}"
    w = script.ScriptWriter(job, m)
    folder = script.paths.work_dir(vid)
    w.plan = VideoPlan.model_validate(json.loads((folder / "plan.json").read_text()))
    nar = json.loads((folder / "narration.json").read_text())
    w.beats = {b: [Line(**ln) for ln in v["lines"]] for b, v in nar["beats"].items()}
    return w


async def run_series(lesson_md: str, mode: str) -> None:
    sid = script.video_id_for(lesson_md)
    plan, state = await series.plan_series(sid, lesson_md, mode, "by-hand")
    print(state["state"], *state["report"], sep="\n")
    if plan:
        for n, part in enumerate(plan.parts, 1):
            print(f"{state['parts'][n - 1]}: {part.title} {part.concepts}")


async def run_script(lesson_md: str, parts: list[int]) -> None:
    sid = script.video_id_for(lesson_md)
    data = series.load_series(sid)
    assert data and data.get("state") == "planned", f"plan the series first: series {lesson_md}"
    for n in parts or range(1, len(data["parts"]) + 1):
        payload = {"stage": "video_script", "video_id": data["parts"][n - 1],
                   "lesson_md": lesson_md, "mode": data["mode"], "series": sid, "part": n,
                   "build": False}
        outcome, report = await script.run({"id": "by-hand", "payload": payload}, Deps())
        print(outcome)
        print(report)


async def _material(vid: str) -> dict[str, Any]:
    job = script.load_job(vid)
    assert job is not None, f"no job {vid}"
    return await script.gather({"lesson_md": job.lesson_md, "mode": job.mode,
                                "series": job.series_id, "part": job.part})


async def repair(vid: str) -> None:
    job = script.load_job(vid)
    assert job is not None
    m = await _material(vid)
    w = _writer(vid, m)
    before = {b: [ln.text for ln in v] for b, v in w.beats.items()}
    await w.review_whole()
    editor = await w.edit()
    changed = [b for b in w.beats if [ln.text for ln in w.beats[b]] != before[b]]
    facts = await w.check_facts(only=changed)
    await w.review_whole()
    await script._save_step(vid, "narration.json", w.narration())
    assert w.plan is not None
    remaining = checks.narration_problems(w.beats, mode=job.mode,
                                          n_concepts=len(w.plan.concepts))
    folder = script.paths.work_dir(vid)
    review = json.loads((folder / "review.json").read_text())
    review.update({"editor": editor, "remaining": remaining,
                   "facts": [f for f in review["facts"] if f["beat"] not in changed] + facts,
                   "minutes": round(checks.minutes(w.beats), 1)})
    await script._save_step(vid, "review.json", review)
    spec = await w.write_scenes()
    print("changed beats:", changed)
    print("still open:", remaining)
    print("facts flagged:", [f for f in facts if f["verdict"] in ("contradicted", "unsupported")])
    print("scenes:", len(spec["beats"]), "beats")
    print("\n".join(w.report))


async def scenes(vid: str) -> None:
    """Write the scene spec again from the saved plan and narration."""
    w = _writer(vid, await _material(vid))
    spec = await w.write_scenes()
    print("scenes:", len(spec["beats"]), "beats")
    print("\n".join(w.report))


async def _not_published(vid: str) -> dict[str, Any]:
    """Stands in for the publish step: the video stays in its job folder."""
    timing = json.loads((script.paths.work_dir(vid) / f"{vid}.timing.json").read_text())
    folder = script.paths.work_dir(vid)
    chapters = folder / "chapters.json"
    print(f"not published: {folder / build.mp4_name(vid, 1)}")
    return {"duration_s": round(timing["totalFrames"] / timing["fps"], 1),
            "chapters": json.loads(chapters.read_text()) if chapters.is_file() else []}


async def run_build(vid: str, scale: int, keep_page: bool = False) -> None:
    runner.emit_step = _no_event  # type: ignore[assignment]
    DBOS.sleep_async = staticmethod(asyncio.sleep)  # type: ignore[method-assign,assignment]
    if keep_page:
        build._publish_step = _not_published  # type: ignore[assignment]
    job = script.load_job(vid)
    assert job is not None, f"no job {vid}"
    job.state = "approved"
    script.save_job(job)
    outcome, report = await build.run(
        {"id": "by-hand", "payload": {"video_id": vid, "scale": scale}}, Deps())
    print(outcome)
    print(report)


async def main() -> None:
    cmd, *args = sys.argv[1:]
    await db.open_pool()
    t0 = time.time()
    if cmd == "series":
        await run_series(args[0], args[1] if len(args) > 1 else "course")
    elif cmd == "script":
        await run_script(args[0], [int(a) for a in args[1:]])
    elif cmd == "repair":
        await repair(args[0])
    elif cmd == "scenes":
        await scenes(args[0])
    elif cmd == "build":
        rest = [a for a in args[1:] if a != "--keep-page"]
        await run_build(args[0], int(rest[0]) if rest else 1, "--keep-page" in args)
    else:
        raise SystemExit(__doc__)
    print(f"elapsed {time.time() - t0:.0f}s")


if __name__ == "__main__":
    asyncio.run(main())
