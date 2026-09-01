"""Board and notification tools available to agents."""

from __future__ import annotations

from pydantic_ai import RunContext

from hq import board, db, safety
from hq.obs import emit
from hq.safety import ActionClass
from hq.tools.registry import HQDeps, hq_tool


@hq_tool(action=ActionClass.READ)
async def read_board(ctx: RunContext[HQDeps]) -> list[dict]:
    """Read open tasks on the board (id, title, agent, status)."""
    return await db.fetch(
        "SELECT id::text, title, agent, status, created_at FROM hq.tasks"
        " WHERE status NOT IN ('done', 'failed') ORDER BY created_at DESC LIMIT 50"
    )


@hq_tool(action=ActionClass.READ)
async def create_subtask(ctx: RunContext[HQDeps], title: str, brief: str, agent: str) -> str:
    """Delegate work: create a task for another agent, linked to the current task."""
    task_id = await board.create_task(
        title=title, brief=brief, agent=agent,
        source="agent", parent_id=ctx.deps.task_id,
    )
    return f"created task {task_id} for {agent}"


@hq_tool(action=ActionClass.NOTIFY)
async def notify_owner(ctx: RunContext[HQDeps], text: str) -> str:
    """Send a short message to the owner. Budgeted: over the daily cap it lands in the digest."""
    if await safety.notification_budget_left():
        await board.queue_outbound(
            {"kind": "text", "text": text},
            idempotency_key=f"notify:{ctx.deps.run_id}:{hash(text) & 0xFFFFFFFF}",
        )
        await emit("notify", run_id=ctx.deps.run_id, agent=ctx.deps.agent, payload={"text": text[:200]})
        return "sent"
    await emit("notify_digested", run_id=ctx.deps.run_id, agent=ctx.deps.agent, payload={"text": text[:200]})
    return "daily notification budget reached; message stored for the digest"
