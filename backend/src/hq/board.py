"""Task board. The ONLY write path for task state is ``apply()``:
it appends a task_events row and updates the tasks projection in one transaction.
Also owns the tickets state machine and the notification outbox.
"""

from __future__ import annotations

from typing import Any

from hq import db
from hq.obs import emit

VALID_STATUSES = {"backlog", "running", "blocked", "needs_approval", "done", "failed"}


async def create_task(
    *,
    title: str,
    agent: str,
    source: str,
    brief: str = "",
    parent_id: str | None = None,
    payload: dict[str, Any] | None = None,
    dedup_key: str | None = None,
) -> str | None:
    """Insert a task in backlog. Returns task id, or None if dedup_key collided."""
    async with db.tx() as conn:
        cur = await conn.execute(
            """
            INSERT INTO hq.tasks (title, brief, agent, source, parent_id, payload, dedup_key)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (dedup_key) DO NOTHING
            RETURNING id
            """,
            (title, brief, agent, source, parent_id, db.jsonb(payload or {}), dedup_key),
        )
        row = await cur.fetchone()
        if row is None:
            return None
        task_id = str(row["id"])
        await _append_event(conn, task_id, "system", "created", {"source": source})
    await emit("task.created", task_id=task_id, agent=agent, payload={"title": title})
    return task_id


async def apply(
    task_id: str,
    event_type: str,
    *,
    actor: str = "system",
    data: dict[str, Any] | None = None,
    status: str | None = None,
) -> None:
    """Append an event; optionally move the projection to a new status."""
    if status is not None and status not in VALID_STATUSES:
        raise ValueError(f"invalid status {status!r}")
    async with db.tx() as conn:
        await _append_event(conn, task_id, actor, event_type, data or {})
        if status is not None:
            await conn.execute(
                "UPDATE hq.tasks SET status = %s, updated_at = now() WHERE id = %s",
                (status, task_id),
            )
    await emit(
        "task.updated", task_id=task_id,
        payload={"event": event_type, "status": status, **(data or {})},
    )


async def _append_event(conn, task_id: str, actor: str, event_type: str, data: dict) -> None:
    await conn.execute(
        """
        INSERT INTO hq.task_events (task_id, seq, actor, event_type, data)
        VALUES (%s,
                (SELECT coalesce(max(seq), 0) + 1 FROM hq.task_events WHERE task_id = %s),
                %s, %s, %s)
        """,
        (task_id, task_id, actor, event_type, db.jsonb(data)),
    )


# --- tickets -----------------------------------------------------------------

async def create_ticket(
    *,
    task_id: str | None,
    run_id: str | None,
    wf_id: str,
    tool_name: str,
    tool_args: dict[str, Any],
    tool_call_id: str,
    action_class: str,
) -> str:
    row = await db.fetchone(
        """
        INSERT INTO hq.tickets (task_id, run_id, wf_id, tool_name, tool_args, tool_call_id, action_class)
        VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id
        """,
        (task_id, run_id, wf_id, tool_name, db.jsonb(tool_args), tool_call_id, action_class),
    )
    ticket_id = str(row["id"])
    await emit(
        "ticket.created", task_id=task_id,
        payload={"ticket_id": ticket_id, "tool": tool_name, "args": tool_args},
    )
    return ticket_id


async def resolve_ticket(ticket_id: str, verdict: str, via: str) -> dict | None:
    """Idempotent pending -> approved|denied. Returns the ticket row if this call
    performed the transition, None if it was already resolved (no-op)."""
    assert verdict in {"approved", "denied", "expired"}
    row = await db.fetchone(
        """
        UPDATE hq.tickets SET status = %s, resolved_at = now(), resolved_via = %s
        WHERE id = %s AND status = 'pending'
        RETURNING id, wf_id, tool_call_id, tool_name, task_id
        """,
        (verdict, via, ticket_id),
    )
    if row is not None:
        await emit(
            "ticket.resolved", task_id=str(row["task_id"]) if row["task_id"] else None,
            payload={"ticket_id": ticket_id, "verdict": verdict, "via": via},
        )
    return row


# --- outbox ------------------------------------------------------------------

async def queue_outbound(
    intent: dict[str, Any], *, chat_ref: str = "", idempotency_key: str | None = None
) -> None:
    """Durable notification: a crash between board.apply and the send loses nothing."""
    await db.execute(
        """
        INSERT INTO hq.outbox (chat_ref, intent, idempotency_key)
        VALUES (%s, %s, %s) ON CONFLICT (idempotency_key) DO NOTHING
        """,
        (chat_ref, db.jsonb(intent), idempotency_key),
    )
