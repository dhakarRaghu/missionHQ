"""Run the video pipeline for one lesson by hand, outside the live engine.

The live backend owns the database's DBOS queues and schedules, so a second
backend must never be started to test a video. This script calls the same
stages directly: every model call, check and file is the pipeline's own,
and the job folder is the one the live system would use. Progress events
are not recorded, so a test leaves no rows in the event feed.

    uv run python scripts/video_run.py script <lesson_md> <course|article>
    uv run python scripts/video_run.py repair <lesson_md>   # editor + facts + scenes again
    uv run python scripts/video_run.py scenes <lesson_md>   # scenes again only
    uv run python scripts/video_run.py build <video_id> [1|2]

`script` stops before the build (VIDEO_AUTO_BUILD=0); run `build` after
reading the job's review.json.
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
from hq.video import build, checks, script
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


async def run_script(lesson_md: str, mode: str) -> None:
    vid = script.video_id_for(lesson_md)
    payload = {"stage": "video_script", "video_id": vid, "lesson_md": lesson_md,
               "mode": mode, "build": False}
    outcome, report = await script.run({"id": "by-hand", "payload": payload}, Deps())
    print(outcome)
    print(report)


async def repair(lesson_md: str) -> None:
    vid = script.video_id_for(lesson_md)
    job = script.load_job(vid)
    assert job is not None
    m = await script.gather({"lesson_md": lesson_md, "mode": job.mode})
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


async def scenes(lesson_md: str) -> None:
    """Write the scene spec again from the saved plan and narration."""
    vid = script.video_id_for(lesson_md)
    job = script.load_job(vid)
    assert job is not None
    w = _writer(vid, await script.gather({"lesson_md": lesson_md, "mode": job.mode}))
    spec = await w.write_scenes()
    print("scenes:", len(spec["beats"]), "beats")
    print("\n".join(w.report))


async def run_build(vid: str, scale: int) -> None:
    runner.emit_step = _no_event  # type: ignore[assignment]
    DBOS.sleep_async = staticmethod(asyncio.sleep)  # type: ignore[method-assign,assignment]
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
    if cmd == "script":
        await run_script(args[0], args[1] if len(args) > 1 else "course")
    elif cmd == "repair":
        await repair(args[0])
    elif cmd == "scenes":
        await scenes(args[0])
    elif cmd == "build":
        await run_build(args[0], int(args[1]) if len(args) > 1 else 1)
    else:
        raise SystemExit(__doc__)
    print(f"elapsed {time.time() - t0:.0f}s")


if __name__ == "__main__":
    asyncio.run(main())
