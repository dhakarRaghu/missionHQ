"""Task board. The ONLY write path for task state is ``apply()``:
it appends a task_events row and updates the tasks projection in one transaction.
Also owns the tickets state machine and the notification outbox.
"""

from __future__ import annotations

import logging
from typing import Any

from hq import db
from hq.obs import emit

log = logging.getLogger(__name__)

VALID_STATUSES = {"backlog", "running", "blocked", "needs_approval", "done",
                  "failed", "archived"}

# Legal status transitions. A same-status "transition" is always accepted as a
# no-op so a replayed workflow step can re-apply what it already applied.
ALLOWED: dict[str, set[str]] = {
    "backlog": {"running", "blocked", "failed", "archived"},
    "running": {"needs_approval", "blocked", "done", "failed"},
    "needs_approval": {"running", "blocked", "failed"},
    "blocked": {"backlog", "running", "failed", "archived"},
    "done": {"archived"},
    "failed": {"backlog", "archived"},
    # Terminal. It also has to be a key at all: ``apply`` looks up
    # ``ALLOWED[current]``, so an absent entry is a KeyError on any event
    # appended to a task the maintenance tick had already archived.
    "archived": set(),
}
# ``running`` and ``needs_approval`` deliberately have no route to archived.
# Hiding a card whose run is still going would hide something still spending
# money, so the owner cancels it first. The dismiss endpoint refuses the same
# two states, and the two rules must stay in step.

# Events written before ``apply`` started recording ``data.status``. Used only
# by the projection rebuild so old logs still replay to a status.
_LEGACY_EVENT_STATUS: dict[str, str] = {
    "status_changed": "running",
    "blocked": "blocked",
    "reaped": "blocked",
    "approval_requested": "needs_approval",
    "approval_resolved": "running",
    "run_done": "done",
    "run_blocked": "blocked",
    "run_failed": "failed",
}


class IllegalTransition(ValueError):
    """Raised by ``apply`` when the requested status is not reachable from the
    task's current status."""


async def create_task(
    *,
    title: str,
    agent: str,
    source: str,
    brief: str = "",
    parent_id: str | None = None,
    origin_session_id: str | None = None,
    payload: dict[str, Any] | None = None,
    dedup_key: str | None = None,
) -> tuple[str, str, bool]:
    """Insert a task in backlog. Returns (task_id, status, inserted). On a
    dedup_key collision the existing task is returned with inserted=False."""
    async with db.tx() as conn:
        cur = await conn.execute(
            """
            INSERT INTO hq.tasks (
              title, brief, agent, source, parent_id, origin_session_id, payload, dedup_key
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (dedup_key) DO UPDATE SET dedup_key = excluded.dedup_key
            RETURNING id, status, (xmax = 0) AS inserted
            """,
            (
                title, brief, agent, source, parent_id, origin_session_id,
                db.jsonb(payload or {}), dedup_key,
            ),
        )
        row = await cur.fetchone()
        assert row is not None
        task_id = str(row["id"])
        inserted = bool(row["inserted"])
        if inserted:
            await _append_event(conn, task_id, "system", "created", {"source": source})
    if inserted:
        await emit("task.created", task_id=task_id, agent=agent, payload={"title": title})
    return task_id, str(row["status"]), inserted


async def apply(
    task_id: str,
    event_type: str,
    *,
    actor: str = "system",
    data: dict[str, Any] | None = None,
    status: str | None = None,
    expect: str | None = None,
) -> bool:
    """Append an event; optionally move the projection to a new status.

    The transition is validated against ``ALLOWED`` inside the same transaction
    that holds the row lock, so two concurrent appenders cannot both pass. A
    status-changing event also records ``data["status"]`` so the event log
    alone can rebuild the projection (see ``rebuild_projection``).

    With ``expect``, nothing is appended unless the task is in that status
    under the lock, and the answer is False. Two watchdog ticks that both saw
    a run stop then move its task once: an unguarded blocked -> blocked is
    legal, and three ticks requeued one video in the same millisecond.
    """
    if status is not None and status not in VALID_STATUSES:
        raise ValueError(f"invalid status {status!r}")
    event_data = dict(data or {})
    async with db.tx() as conn:
        # Row lock serializes concurrent appenders so seq never collides.
        cur = await conn.execute(
            "SELECT status FROM hq.tasks WHERE id = %s FOR UPDATE", (task_id,)
        )
        row = await cur.fetchone()
        if row is None:
            raise ValueError(f"unknown task {task_id}")
        current = str(row["status"])
        if expect is not None and current != expect:
            return False
        if status is not None:
            if status != current and status not in ALLOWED[current]:
                log.warning(
                    "refused illegal transition %s -> %s for task %s (event %s)",
                    current, status, task_id, event_type,
                )
                raise IllegalTransition(
                    f"task {task_id}: cannot move {current} -> {status} (event {event_type})"
                )
            event_data["status"] = status
        await _append_event(conn, task_id, actor, event_type, event_data)
        if status is not None and status != current:
            await conn.execute(
                "UPDATE hq.tasks SET status = %s, updated_at = now() WHERE id = %s",
                (status, task_id),
            )
    await emit(
        "task.updated", task_id=task_id,
        payload={"event": event_type, **event_data, "status": status},
    )
    return True


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


# --- projection check --------------------------------------------------------

def _replay_status(events: list[dict[str, Any]]) -> str:
    """Fold an ordered event list into a status. ``created`` starts at backlog;
    every event carrying ``data.status`` applies it; events from before that
    field existed fall back to ``_LEGACY_EVENT_STATUS`` by event type."""
    status = "backlog"
    for ev in events:
        data = ev["data"] or {}
        recorded = data.get("status")
        if isinstance(recorded, str) and recorded in VALID_STATUSES:
            status = recorded
        elif ev["event_type"] in _LEGACY_EVENT_STATUS:
            status = _LEGACY_EVENT_STATUS[ev["event_type"]]
    return status


async def rebuild_projection(task_id: str) -> str:
    """Status derived purely from hq.task_events for one task. Does not write."""
    events = await db.fetch(
        "SELECT event_type, data FROM hq.task_events WHERE task_id = %s ORDER BY seq",
        (task_id,),
    )
    return _replay_status(events)


async def verify_projections() -> list[dict[str, str]]:
    """Compare the derived status with the stored one for every task. Returns
    ``[{task_id, stored, derived}]`` for each mismatch; empty means consistent."""
    tasks = await db.fetch("SELECT id::text, status FROM hq.tasks ORDER BY created_at")
    events = await db.fetch(
        "SELECT task_id::text, event_type, data FROM hq.task_events ORDER BY task_id, seq"
    )
    by_task: dict[str, list[dict[str, Any]]] = {}
    for ev in events:
        by_task.setdefault(ev["task_id"], []).append(ev)
    mismatches: list[dict[str, str]] = []
    for t in tasks:
        derived = _replay_status(by_task.get(t["id"], []))
        if derived != t["status"]:
            mismatches.append({"task_id": t["id"], "stored": t["status"], "derived": derived})
    return mismatches


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
    status: str = "pending",
    resolved_via: str | None = None,
) -> str:
    """Deterministic: keyed by (wf_id, tool_call_id), so a replayed workflow
    gets the ticket it already opened instead of a second one.

    ``status`` other than ``pending`` inserts the ticket already resolved (used
    by the guardrails: the owner is never asked, but the refusal is on record)."""
    assert status in {"pending", "approved", "denied", "expired"}
    row = await db.fetchone(
        """
        INSERT INTO hq.tickets (task_id, run_id, wf_id, tool_name, tool_args, tool_call_id,
                                action_class, status, resolved_at, resolved_via)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s,
                CASE WHEN %s = 'pending' THEN NULL ELSE now() END, %s)
        ON CONFLICT (wf_id, tool_call_id) DO NOTHING RETURNING id
        """,
        (task_id, run_id, wf_id, tool_name, db.jsonb(tool_args), tool_call_id, action_class,
         status, status, resolved_via),
    )
    if row is None:
        row = await db.fetchone(
            "SELECT id FROM hq.tickets WHERE wf_id = %s AND tool_call_id = %s",
            (wf_id, tool_call_id),
        )
        assert row is not None
        return str(row["id"])
    ticket_id = str(row["id"])
    await emit(
        "ticket.created", task_id=task_id,
        payload={"ticket_id": ticket_id, "tool": tool_name, "args": tool_args,
                 "status": status, "resolved_via": resolved_via},
    )
    return ticket_id


async def ticket_statuses(ticket_ids: list[str]) -> dict[str, str]:
    """{ticket_id: status} for the given ids. The table is the source of truth."""
    if not ticket_ids:
        return {}
    rows = await db.fetch(
        "SELECT id::text, status FROM hq.tickets WHERE id = ANY(%s::uuid[])", (ticket_ids,)
    )
    return {r["id"]: r["status"] for r in rows}


async def resolve_ticket(ticket_id: str, verdict: str, via: str) -> dict | None:
    """Idempotent pending -> approved|denied|expired. Returns the ticket row if
    this call performed the transition, None if it was already resolved (no-op)."""
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
