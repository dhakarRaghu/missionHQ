"""Where the engine hands a video task: tutor runs both stages, no agent loop."""

from __future__ import annotations

import logging
import os
import subprocess
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from hq.loader import AgentSpec
from hq.video import BUILD_STAGE, SCRIPT_STAGE, SERIES_STAGE, STAGES

log = logging.getLogger(__name__)


def handles(spec: AgentSpec, payload: object) -> bool:
    return (spec.name == "tutor" and isinstance(payload, dict)
            and payload.get("stage") in STAGES)


@contextmanager
def awake() -> Iterator[None]:
    """Keep the Mac from idle-sleeping while a video task runs, on battery too.

    The backend's own caffeinate (`api/app.py`) uses -s, which holds only on
    AC power. On battery the laptop slept through three video tasks from
    2026-10-11 to 10-13: a 36-minute video's build took 10.5 hours, about 3.4
    of them awake, and a script slept, was queued again and wrote itself a
    second time. A video runs only when he starts one, so holding idle sleep
    off (-i) for the task is what he asked for. Closing the lid still sleeps.
    -w ties it to this process, so a crash cannot leave it holding.
    """
    from hq.video.build import CAFFEINATE

    proc = None
    try:
        proc = subprocess.Popen([CAFFEINATE, "-i", "-w", str(os.getpid())],
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        log.warning("could not hold the machine awake for a video: %s", exc)
    try:
        yield
    finally:
        if proc is not None:
            proc.terminate()


async def write(task: dict[str, Any], spec: AgentSpec, deps: Any) -> Any:
    with awake():
        return await _write(task, deps)


async def _write(task: dict[str, Any], deps: Any) -> Any:
    from hq.runner import RunOutcome
    from hq.video import build, script, series

    stage = (task.get("payload") or {}).get("stage")
    try:
        if stage == SERIES_STAGE:
            outcome, report = await series.run(task, deps)
        elif stage == SCRIPT_STAGE:
            outcome, report = await script.run(task, deps)
        elif stage == BUILD_STAGE:
            outcome, report = await build.run(task, deps)
        else:
            outcome, report = "failed", f"unknown video stage {stage!r}"
    except ValueError as exc:
        # A plan or a spec that could not be fixed in its rounds: the job keeps
        # every artifact written so far, and the report says what failed.
        from hq.video.script import load_job, save_job

        vid = str((task.get("payload") or {}).get("video_id") or "")
        job = load_job(vid) if vid else None
        if job:
            job.state, job.report = "failed", [*job.report, str(exc)[:1500]]
            save_job(job)
        outcome, report = "failed", str(exc)[:1500]
    return RunOutcome(output=report, outcome=outcome, input_tokens=0, output_tokens=0,
                      cost_usd=0.0, error=None if outcome == "done" else report[:500])
