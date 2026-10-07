"""Where the engine hands a video task: tutor runs both stages, no agent loop."""

from __future__ import annotations

from typing import Any

from hq.loader import AgentSpec
from hq.video import BUILD_STAGE, SCRIPT_STAGE, STAGES


def handles(spec: AgentSpec, payload: object) -> bool:
    return (spec.name == "tutor" and isinstance(payload, dict)
            and payload.get("stage") in STAGES)


async def write(task: dict[str, Any], spec: AgentSpec, deps: Any) -> Any:
    from hq.runner import RunOutcome
    from hq.video import build, script

    stage = (task.get("payload") or {}).get("stage")
    try:
        if stage == SCRIPT_STAGE:
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
