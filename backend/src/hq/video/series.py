"""Stage 0: from a finished lesson to a series of parts of about ten minutes.

One video per lesson ran 20 to 49 minutes and was not watched to the end
(2026-10-14). So a lesson is taught in full, but as parts: this stage plans
which concepts go in which part, each part with its own question and the
question it hands over to the next, writes `data/video-work/<series>/series.json`,
and starts one script task per part. The parts are written side by side on
the `video_scripts` lane, and each part's build joins the `videos` lane (one
render at a time) as soon as its script passes, so part 1 can be watched
while the later parts are still being made.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any, cast

from hq import llm
from hq.dbos_app import DBOS
from hq.video import SCRIPT_STAGE, checks, paths, register
from hq.video.models import SeriesPlan
from hq.video.script import (
    _STEP,
    WRITER_MODEL,
    _ask,
    _gather_step,
    material_text,
    video_id_for,
)

log = logging.getLogger(__name__)

SERIES_ATTEMPTS = 4


def part_id(series_id: str, n: int) -> str:
    """The video id of part n: `<series>-p<n>`, within the id limit."""
    return f"{series_id[:76]}-p{n}"


def load_series(series_id: str) -> dict[str, Any] | None:
    path = paths.work_dir(series_id) / "series.json"
    return json.loads(path.read_text()) if path.is_file() else None


def save_series(series_id: str, data: dict[str, Any]) -> None:
    folder = paths.work_dir(series_id)
    folder.mkdir(parents=True, exist_ok=True)
    data = {**data, "updated": datetime.now(UTC).isoformat(timespec="seconds")}
    tmp = folder / "series.json.tmp"
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(folder / "series.json")


@DBOS.step(name="video.series_save")
async def _save_step(series_id: str, data: dict[str, Any]) -> None:
    save_series(series_id, data)


@DBOS.step(name="video.series_load")
async def _load_step(series_id: str) -> dict[str, Any] | None:
    return load_series(series_id)


@DBOS.step(name="video.series_plan", **_STEP)
async def _plan_step(prompt: str) -> dict[str, Any]:
    return cast(SeriesPlan, await _ask(WRITER_MODEL, "series", prompt, SeriesPlan)).model_dump()


@DBOS.step(name="video.series_parts")
async def _drop_old_parts_step(series_id: str, keep: int) -> None:
    """A series planned again with fewer parts: the old later parts leave the page."""
    register.drop_videos(lambda v: v.get("series_id") == series_id
                         and int(v.get("part") or 0) > keep)


def _prompt(mode: str, m: dict[str, Any], problems: list[str],
            previous: dict[str, Any] | None) -> str:
    prompt = (f"Mode: {mode}\nCourse: {m.get('course') or '(an article, no course)'}\n\n"
              + material_text(m))
    if problems:
        prompt += ("\n\n## Your previous series\n\n```json\n"
                   + json.dumps(previous, ensure_ascii=False) + "\n```\n\n## What was sent back\n\n"
                   + "\n".join(f"- {p}" for p in problems)
                   + "\n\nChange only what is named and keep every other field. Return the"
                     " whole series.")
    return prompt


async def plan_series(series_id: str, lesson_md: str, mode: str, task_id: str,
                      slug: str | None = None) -> tuple[SeriesPlan | None, dict[str, Any]]:
    """Plan the series and save it; (None, state) when it still fails its checks."""
    state: dict[str, Any] = {"id": series_id, "mode": mode, "lesson_md": lesson_md,
                             "task_id": task_id, "state": "planning", "title": "",
                             "course": "", "plan": None, "parts": [], "report": []}
    await _save_step(series_id, state)
    m = await _gather_step({"lesson_md": lesson_md, "mode": mode, "slug": slug})
    state["course"] = m["course"]
    problems: list[str] = []
    previous: dict[str, Any] | None = None
    for attempt in range(1, SERIES_ATTEMPTS + 1):
        raw = await _plan_step(_prompt(mode, m, problems, previous))
        plan = SeriesPlan.model_validate(raw)
        problems = checks.series_problems(plan, mode)
        if not problems:
            parts = [part_id(series_id, n) for n in range(1, len(plan.parts) + 1)]
            state.update(state="planned", title=plan.title, plan=plan.model_dump(), parts=parts,
                         report=[f"series accepted on attempt {attempt}"])
            await _save_step(series_id, state)
            await _drop_old_parts_step(series_id, len(parts))
            return plan, state
        previous = raw
    why = f"the series still failed after {SERIES_ATTEMPTS} attempts: {problems[:6]}"
    state.update(state="failed", report=[why])
    await _save_step(series_id, state)
    return None, state


async def run(task: dict[str, Any], deps: Any) -> tuple[str, str]:
    """Plan the series and start its parts. Returns (outcome, report)."""
    from hq import engine

    payload = dict(task.get("payload") or {})
    mode = str(payload.get("mode") or "course")
    lesson_md = str(payload.get("lesson_md") or "")
    series_id = str(payload.get("video_id") or video_id_for(lesson_md))
    task_id = str(task.get("id") or "")
    saved = await _load_step(series_id)
    if saved and saved.get("task_id") == task_id and saved.get("state") == "planned":
        # The same task queued again after the host slept: its plan stands,
        # because parts it already started were written from it.
        plan: SeriesPlan | None = SeriesPlan.model_validate(saved["plan"])
        state = saved
    else:
        with llm.call_context(run_id=deps.run_id, task_id=deps.task_id, agent="tutor"):
            plan, state = await plan_series(series_id, lesson_md, mode, task_id,
                                            payload.get("slug"))
    if plan is None:
        return "failed", "\n".join(state["report"])
    for n, vid in enumerate(state["parts"], 1):
        await engine.dispatch(
            agent="tutor", title=f"Video script: {plan.parts[n - 1].title}", source="agent",
            brief="A narrated video of a finished lesson (hq.video).",
            parent_task_id=deps.task_id,
            payload={"stage": SCRIPT_STAGE, "video_id": vid, "lesson_md": lesson_md,
                     "mode": mode, "series": series_id, "part": n},
            dedup_key=f"video:{vid}:{SCRIPT_STAGE}:{deps.task_id}")
    count = len(state["parts"])
    lines = [f"**Video series: {plan.title}**",
             f"{count} part{'s' if count != 1 else ''}, each written and built on its own:"]
    lines += [f"{n}. {p.title} ({len(p.concepts)} concepts)" for n, p in enumerate(plan.parts, 1)]
    if plan.mismatches:
        lines += ["", "Lesson mismatches found:", *[f"- {x}" for x in plan.mismatches]]
    return "done", "\n".join(lines)
