"""Board and notification tools available to agents."""

from __future__ import annotations

import hashlib

from pydantic_ai import RunContext

from hq import board, db, safety
from hq.job_pipeline import discovery_brief, discovery_payload, families_for
from hq.obs import emit
from hq.safety import ActionClass
from hq.tools.registry import HQDeps, hq_tool


def _now_local():
    from datetime import datetime
    from zoneinfo import ZoneInfo

    from hq.config import settings

    return datetime.now(ZoneInfo(settings().cron_tz))


@hq_tool(action=ActionClass.READ)
async def read_board(ctx: RunContext[HQDeps]) -> list[dict]:
    """Read open tasks on the board (id, title, agent, status)."""
    return await db.fetch(
        "SELECT id::text, title, agent, status, created_at FROM hq.tasks"
        " WHERE status NOT IN ('done', 'failed') ORDER BY created_at DESC LIMIT 50"
    )


ACTIVITY_LIMIT = 50
ACTIVITY_OUTPUT_CHARS = 200
ACTIVITY_MAX_HOURS = 24 * 30

# Tasks touched in the window (every status), each with its latest run and
# the output line the run left on the task (run_done / run_blocked /
# run_failed events carry data.output).
_ACTIVITY_SQL = """
SELECT t.id::text, t.title, t.agent, t.status, t.updated_at,
       r.outcome AS run_outcome, r.cost_usd AS run_cost_usd, r.error AS run_error,
       r.ended_at AS run_ended_at,
       (SELECT e.data->>'output' FROM hq.task_events e
         WHERE e.task_id = t.id AND e.event_type LIKE 'run\\_%%'
           AND e.data ? 'output'
         ORDER BY e.seq DESC LIMIT 1) AS run_output
FROM hq.tasks t
LEFT JOIN LATERAL (
    SELECT outcome, cost_usd, error, ended_at FROM hq.runs
    WHERE task_id = t.id ORDER BY started_at DESC LIMIT 1
) r ON true
WHERE t.updated_at >= now() - make_interval(hours => %s)
ORDER BY t.updated_at DESC
LIMIT %s
"""


@hq_tool(action=ActionClass.READ)
async def read_activity(ctx: RunContext[HQDeps], since_hours: int = 24) -> list[dict]:
    """What happened recently: tasks updated in the last since_hours (all
    statuses, finished work included), each with agent, status, title, the
    last run's outcome and cost, and the first 200 chars of its output.
    Use this for "what happened today / this week"; read_board only shows
    open tasks."""
    hours = min(max(1, int(since_hours)), ACTIVITY_MAX_HOURS)
    rows = await db.fetch(_ACTIVITY_SQL, (hours, ACTIVITY_LIMIT))
    out: list[dict] = []
    for r in rows:
        output = r["run_output"] or ""
        out.append({
            "id": r["id"],
            "title": r["title"],
            "agent": r["agent"],
            "status": r["status"],
            "updated_at": r["updated_at"].isoformat() if r["updated_at"] else None,
            "run_outcome": r["run_outcome"],
            "cost_usd": float(r["run_cost_usd"]) if r["run_cost_usd"] is not None else None,
            "error": (r["run_error"] or "")[:ACTIVITY_OUTPUT_CHARS] or None,
            "output": output[:ACTIVITY_OUTPUT_CHARS],
        })
    return out


@hq_tool(action=ActionClass.READ)
async def create_subtask(ctx: RunContext[HQDeps], title: str, brief: str, agent: str) -> str:
    """Delegate work: create a task for another agent, linked to the current task."""
    from hq import engine  # late import to avoid cycles

    if agent not in engine.registered_agents():
        return f"error: unknown agent {agent!r}; known: {sorted(engine.registered_agents())}"
    task_id = await engine.dispatch(
        agent=agent, title=title, brief=brief, source="agent",
        parent_task_id=ctx.deps.task_id,
        origin_session_id=ctx.deps.session_id,
        payload={"provenance": "agent", "run_id": ctx.deps.run_id},
    )
    return f"created task {task_id} for {agent}"


@hq_tool(action=ActionClass.READ)
async def start_job_search(
    ctx: RunContext[HQDeps],
    query: str,
    locations: str = "India|Bengaluru|Remote",
    max_roles: int = 20,
) -> str:
    """Start browser discovery followed automatically by Hunter verification.

    Use this for broad job searches where the owner did not specify a company
    or applicant-tracking platform. The workflow never applies or contacts.
    """
    from hq import engine  # late import to avoid cycles

    payload = discovery_payload(
        query=query,
        locations=locations,
        max_roles=max_roles,
        families=families_for(_now_local().date()),
    )
    query_label = str(payload["query"])
    task_id = await engine.dispatch(
        agent="operator",
        title=f"Discover jobs: {query_label[:80]}",
        brief=discovery_brief(payload),
        source="agent",
        parent_task_id=ctx.deps.task_id,
        origin_session_id=ctx.deps.session_id,
        payload={**payload, "run_id": ctx.deps.run_id},
        # A nightly start has no task or run of its own; the date keeps one
        # discovery per night instead of one ever ("None:None").
        dedup_key=(f"job-search-discovery:{ctx.deps.task_id}:{ctx.deps.run_id}"
                   if ctx.deps.task_id or ctx.deps.run_id
                   else f"job-search-discovery:system:{_now_local():%Y-%m-%d}"),
    )
    return (
        f"started browser job discovery task {task_id} for operator; "
        "Hunter verification will be queued automatically when discovery finishes"
    )


@hq_tool(action=ActionClass.NOTIFY)
async def notify_owner(ctx: RunContext[HQDeps], text: str) -> str:
    """Send a short message to the owner. Budgeted: over the daily cap it lands in the digest."""
    if await safety.notification_budget_left():
        digest = hashlib.sha1(text.encode()).hexdigest()[:12]
        await board.queue_outbound(
            {"kind": "text", "text": text},
            idempotency_key=f"notify:{ctx.deps.run_id}:{digest}",
        )
        await emit("notify", run_id=ctx.deps.run_id, agent=ctx.deps.agent, payload={"text": text[:200]})
        return "sent"
    await emit("notify_digested", run_id=ctx.deps.run_id, agent=ctx.deps.agent, payload={"text": text[:200]})
    return "daily notification budget reached; message stored for the digest"


# world_facing: this is the one tool whose effect leaves Mission HQ and lands
# in front of other people. No agent may hold it. Kept registered so the rule
# has something to refuse, and so the catalog can say plainly that publishing
# is the owner's alone.
@hq_tool(action=ActionClass.EXTERNAL_WRITE, world_facing=True)
async def announce(ctx: RunContext[HQDeps], text: str) -> str:
    """Send a message outward on the owner's behalf. Always requires the owner's
    approval first. Until a real outward channel exists (phase 3), the approved
    message is delivered to the owner's Telegram as the stand-in."""
    digest = hashlib.sha1(text.encode()).hexdigest()[:12]
    await board.queue_outbound(
        {"kind": "text", "text": f"[announce by {ctx.deps.agent}] {text}"},
        idempotency_key=f"announce:{ctx.deps.run_id}:{digest}",
    )
    await emit("announce", run_id=ctx.deps.run_id, agent=ctx.deps.agent,
               payload={"text": text[:200]})
    return "announced (delivered after approval)"
