"""Daily notification digest: the outlet for everything the per-day cap held back.

``build_digest()`` is read-only and safe anywhere (the ``/digest`` Telegram
command calls it directly). ``send_digest()`` is meant to run inside the
``daily_digest`` DBOS workflow: the reads are plain, the write side (outbox row,
``digest:last_sent`` marker, ``digest`` event) sits in one step so a replayed
workflow never queues a second copy. The outbox idempotency key is the local
date, so at most one digest per day leaves the system even if triggered twice.

The digest is NOT a budgeted notification: it never emits a ``notify`` event.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from hq import db, engagement, runner, safety, value
from hq.config import settings
from hq.dbos_app import DBOS
from hq.obs import emit

log = logging.getLogger(__name__)

LAST_SENT_KEY = "digest:last_sent"
MAX_CHARS = 3900
MAX_ITEMS = 8           # per list; the rest collapses into "…and N more"
ITEM_TEXT_CHARS = 160


# --- building ---------------------------------------------------------------

async def build_digest(since: datetime | None, *, now: datetime | None = None) -> str:
    """Plain-text digest (no markdown), at most MAX_CHARS. Empty string when
    every section is empty."""
    text, _counts = await _build(since, now=now)
    return text


NOTE_CHARS = 2200            # a 300-word note whole, its one action included
NOTE_DEADLINE = (23, 20)     # wait for sage's 22:30 note until here, then go without it


def _daily_note(now: datetime) -> str:
    """Sage's note for the day, as plain text, when it has been written. The
    note is what he reads at night; the digest is how it reaches his phone."""
    from hq import memory

    try:
        text = memory.read(f"daily/{now:%Y-%m-%d}.md")
    except (OSError, ValueError):
        return ""
    _meta, body = memory.parse_frontmatter(text)
    lines = [ln.lstrip("#").strip() if ln.startswith("#") else ln for ln in body.splitlines()]
    plain = "\n".join(lines).replace("**", "").strip()
    return plain if len(plain) <= NOTE_CHARS else plain[: NOTE_CHARS - 1].rstrip() + "…"


async def _build(since: datetime | None, *, now: datetime | None = None
                 ) -> tuple[str, dict[str, int]]:
    tz = ZoneInfo(settings().cron_tz)
    now = (now or datetime.now(UTC)).astimezone(tz)
    if since is None:
        since = await last_sent() or (now - timedelta(hours=24))

    sections: list[str] = []
    counts: dict[str, int] = {}
    note = await asyncio.to_thread(_daily_note, now)
    counts["note"] = int(bool(note))

    held = await _held_messages(since)
    counts["held"] = len(held)
    if held:
        lines = [f"- [{r['agent'] or '?'}] {_clip(r['text'] or '', ITEM_TEXT_CHARS)}" for r in held]
        sections.append(f"Held back by the notification cap ({len(held)}):\n" + _list(lines))

    tickets = await _pending_tickets(now)
    counts["tickets"] = tickets["count"]
    if tickets["count"]:
        sections.append(
            f"Pending approvals ({tickets['count']}): {tickets['tools']}; "
            f"oldest {tickets['oldest_age']}"
        )

    stuck = await _stuck_tasks(since)
    counts["tasks"] = len(stuck)
    if stuck:
        lines = [
            f"- {r['status']} [{r['agent']}] {_clip(r['title'], 80)}"
            + (f": {_clip(r['reason'], ITEM_TEXT_CHARS)}" if r["reason"] else "")
            for r in stuck
        ]
        sections.append(f"Blocked or failed tasks ({len(stuck)}):\n" + _list(lines))

    missed = await _missed_schedules(since)
    counts["missed"] = len(missed)
    if missed:
        lines = [
            f"- {r['agent']} {r['schedule'] or ''} slot {_slot_label(r['slot_at'])}"
            + (f" (task {r['task_status']})" if r["task_status"] else " (no task)")
            for r in missed
        ]
        sections.append(f"Missed schedules ({len(missed)}):\n" + _list(lines))

    runs = await _runs_summary(since)
    counts["runs"] = runs["count"]
    if runs["count"]:
        per_agent = [f"- {a}: {n} runs, ${c:.2f}" for a, n, c in runs["per_agent"]]
        head = f"Runs ({runs['count']}): ${runs['cost']:.2f} total"
        if runs["stalled"]:
            head += f", {runs['stalled']} stalled"
        if runs["no_artifact"]:
            head += f", {runs['no_artifact']} without artifact"
        sections.append(head + "\n" + _list(per_agent))

    spend = await safety.spend_today_usd()
    counts["spend_cents"] = round(spend * 100)
    if spend > 0:
        cap = settings().daily_spend_cap_usd
        sections.append(f"Spend today: ${spend:.2f} of ${cap:.2f} cap")

    if not sections and not note:
        return "", counts
    # The week in numbers rides along when there is a digest anyway; on its
    # own it is not a reason to send one.
    week = await _value_section(now)
    if week:
        sections.append(week)

    header = f"Mission HQ digest — {now:%Y-%m-%d}"
    week_line = await _value_week_line(now)
    if week_line:
        header += "\n" + week_line
    body = header + "\n\n" + "\n\n".join(([note] if note else []) + sections)
    if len(body) > MAX_CHARS:
        body = body[: MAX_CHARS - 1].rstrip() + "…"
    return body, counts


async def _value_week_line(now: datetime) -> str:
    """"Value week: day N/7 · sent X · acted Y (Z%)" while the week runs,
    else empty. A failure here must not cost the owner the digest."""
    try:
        status = await engagement.value_week_status(now=now)
    except Exception:
        log.warning("value week status unavailable for the digest", exc_info=True)
        return ""
    return engagement.format_status(status) if status["active"] else ""


async def _value_section(now: datetime) -> str:
    """The weekly value report, five lines. Empty on failure: the report must
    not cost the owner the digest."""
    try:
        return value.format_report(await value.week_report(now))
    except Exception:
        log.warning("value report unavailable for the digest", exc_info=True)
        return ""


async def last_sent() -> datetime | None:
    row = await db.fetchone("SELECT value FROM hq.control WHERE key = %s", (LAST_SENT_KEY,))
    if not row or not isinstance(row["value"], str):
        return None
    try:
        ts = datetime.fromisoformat(row["value"])
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


async def _held_messages(since: datetime) -> list[dict[str, Any]]:
    return await db.fetch(
        "SELECT agent, payload->>'text' AS text FROM hq.events"
        " WHERE kind = 'notify_digested' AND ts >= %s ORDER BY ts",
        (since,),
    )


async def _pending_tickets(now: datetime) -> dict[str, Any]:
    rows = await db.fetch(
        "SELECT tool_name, count(*) AS n, min(created_at) AS oldest FROM hq.tickets"
        " WHERE status = 'pending' GROUP BY tool_name ORDER BY n DESC, tool_name"
    )
    if not rows:
        return {"count": 0, "tools": "", "oldest_age": ""}
    oldest = min(r["oldest"] for r in rows)
    tools = ", ".join(f"{r['tool_name']} x{r['n']}" for r in rows[:MAX_ITEMS])
    if len(rows) > MAX_ITEMS:
        tools += f", …and {len(rows) - MAX_ITEMS} more"
    return {
        "count": sum(int(r["n"]) for r in rows),
        "tools": tools,
        "oldest_age": _age(now - oldest),
    }


async def _stuck_tasks(since: datetime) -> list[dict[str, Any]]:
    return await db.fetch(
        """
        SELECT t.agent, t.title, t.status,
               coalesce(e.data->>'reason', e.data->>'error') AS reason
        FROM hq.tasks t
        LEFT JOIN LATERAL (
            SELECT data FROM hq.task_events
            WHERE task_id = t.id AND (data ? 'reason' OR data ? 'error')
            ORDER BY seq DESC LIMIT 1
        ) e ON true
        WHERE t.status IN ('blocked', 'failed') AND t.updated_at >= %s
        ORDER BY t.updated_at DESC
        """,
        (since,),
    )


async def _missed_schedules(since: datetime) -> list[dict[str, Any]]:
    """``cron.missed`` events (dead-man check in engine) since ``since``."""
    return await db.fetch(
        "SELECT agent, payload->>'schedule' AS schedule, payload->>'slot_at' AS slot_at,"
        " payload->>'slot' AS slot, payload->>'task_status' AS task_status"
        " FROM hq.events WHERE kind = 'cron.missed' AND ts >= %s ORDER BY ts",
        (since,),
    )


def _slot_label(slot_at: str | None) -> str:
    """'2026-09-02 21:00' from the stored ISO timestamp; raw text as fallback."""
    if not slot_at:
        return "?"
    try:
        return datetime.fromisoformat(slot_at).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return slot_at


async def _runs_summary(since: datetime) -> dict[str, Any]:
    rows = await db.fetch(
        "SELECT agent, count(*) AS n, coalesce(sum(cost_usd), 0) AS cost,"
        " count(*) FILTER (WHERE stall_count > 0) AS stalled,"
        " count(*) FILTER (WHERE outcome = 'no_artifact') AS no_artifact"
        " FROM hq.runs WHERE started_at >= %s GROUP BY agent ORDER BY cost DESC, agent",
        (since,),
    )
    return {
        "count": sum(int(r["n"]) for r in rows),
        "cost": sum(float(r["cost"]) for r in rows),
        "stalled": sum(int(r["stalled"]) for r in rows),
        "no_artifact": sum(int(r["no_artifact"]) for r in rows),
        "per_agent": [(r["agent"], int(r["n"]), float(r["cost"])) for r in rows],
    }


def _list(lines: list[str]) -> str:
    shown = lines[:MAX_ITEMS]
    if len(lines) > MAX_ITEMS:
        shown.append(f"…and {len(lines) - MAX_ITEMS} more")
    return "\n".join(shown)


def _clip(text: str, n: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _age(delta: timedelta) -> str:
    secs = max(int(delta.total_seconds()), 0)
    days, rem = divmod(secs, 86400)
    hours, rem = divmod(rem, 3600)
    mins = rem // 60
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {mins}m"
    return f"{mins}m"


# --- sending ----------------------------------------------------------------

async def send_digest(*, now: datetime | None = None) -> bool:
    """Build, queue to the outbox (one per local day), record the marker, flush.
    Returns False and sends nothing when there is nothing to report or when
    today's digest already left."""
    now = now or datetime.now(UTC)
    local = now.astimezone(ZoneInfo(settings().cron_tz))
    text, counts = await _build(None, now=now)
    if not text:
        return False
    # The note is the reason the digest goes out at all. Sage's 22:30 run
    # takes up to half an hour, so a fixed 22:50 send missed the note about
    # half the time; the watchdog calls again each minute until it is there.
    if not counts.get("note") and (local.hour, local.minute) < NOTE_DEADLINE:
        return False
    local_date = now.astimezone(ZoneInfo(settings().cron_tz)).strftime("%Y-%m-%d")
    queued = await _record_step(text, local_date, counts, now.astimezone(UTC).isoformat())
    if not queued:
        return False
    await runner.flush_outbox_step()
    return True


@DBOS.step()
async def _record_step(text: str, local_date: str, counts: dict[str, int], sent_iso: str) -> bool:
    """One durable unit: outbox row + last-sent marker + event. Returns False
    when the day's digest row already exists (nothing new is queued and the
    marker is left alone, so unsent items roll into the next digest)."""
    key = f"digest:{local_date}"
    row = await db.fetchone(
        "INSERT INTO hq.outbox (chat_ref, intent, idempotency_key) VALUES ('', %s, %s)"
        " ON CONFLICT (idempotency_key) DO NOTHING RETURNING id",
        (db.jsonb({"kind": "text", "text": text}), key),
    )
    if row is None:
        return False
    await db.execute(
        "INSERT INTO hq.control (key, value, updated_at) VALUES (%s, %s, now())"
        " ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = now()",
        (LAST_SENT_KEY, db.jsonb(sent_iso)),
    )
    await emit("digest", payload={**counts, "chars": len(text), "date": local_date})
    return True
