"""Value week: measure whether the owner acts on what Mission HQ sends.

The plan's kill metric: run the system for 7 days; if the owner ignores half
of what it sends, stop building and fix output quality. This module records
the two sides of that ratio.

- "sent" = outbox rows delivered since the week started (digest rows excluded,
  the digest is a summary, not a request for a decision).
- "acted" = ``owner.action`` events since the week started. Every owner touch
  point (Telegram message, approve/deny button, web approve/deny, new task,
  web chat message) records one such event via :func:`record_owner_action`.

The week start is an ISO date in CRON_TZ stored under hq.control key
``value_week:start``. It is set once; calling :func:`start_value_week` again
is a no-op that returns the existing date.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, time, timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo

from hq import db
from hq.config import settings
from hq.obs import emit

log = logging.getLogger(__name__)

START_KEY = "value_week:start"
WEEK_DAYS = 7
MIN_SENT_FOR_VERDICT = 5  # below this the sample is too small to judge
RESPONSE_RATE_OK = 0.5
EVENT_KIND = "owner.action"
# Recall metrics: did the agents read before they wrote, and did the owner ask?
RECALL_TOOLS = ("memory_search", "recall_facts", "vault_read")

Via = Literal["telegram", "web"]
Action = Literal[
    "message",
    "command",
    "approve",
    "deny",
    "new_task",
    "chat",
    "vault_edit",
    "cancel_task",
    "update_job",
]


# --- owner actions ------------------------------------------------------------


async def record_owner_action(via: Via, action: Action) -> None:
    """Log one owner action. Never raises: a logging failure must not break
    the action the owner just took."""
    try:
        await emit(EVENT_KIND, payload={"via": via, "action": action})
    except Exception:
        log.warning("owner.action not recorded (%s/%s)", via, action, exc_info=True)


# --- week lifecycle -----------------------------------------------------------


def _tz() -> ZoneInfo:
    return ZoneInfo(settings().cron_tz)


def _local_now(now: datetime | None) -> datetime:
    now = now or datetime.now(UTC)
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    return now.astimezone(_tz())


async def get_start() -> date | None:
    row = await db.fetchone("SELECT value FROM hq.control WHERE key = %s", (START_KEY,))
    if not row or not isinstance(row["value"], str):
        return None
    try:
        return date.fromisoformat(row["value"])
    except ValueError:
        return None


async def start_value_week(now: datetime | None = None) -> date:
    """Set the start date (today in CRON_TZ) unless one is already stored.
    Returns the effective start date."""
    today = _local_now(now).date()
    await db.execute(
        "INSERT INTO hq.control (key, value, updated_at) VALUES (%s, %s, now())"
        " ON CONFLICT (key) DO NOTHING",
        (START_KEY, db.jsonb(today.isoformat())),
    )
    return await get_start() or today


# --- status -------------------------------------------------------------------


async def value_week_status(now: datetime | None = None) -> dict[str, Any]:
    local_now = _local_now(now)
    start = await get_start()
    pending_old = await _tickets_pending_over_24h()
    if start is None:
        return {
            "start": None,
            "active": False,
            "day": 0,
            "days_left": WEEK_DAYS,
            "sent": 0,
            "acted": 0,
            "tickets_pending_over_24h": pending_old,
            "response_rate": 0.0,
            "verdict": _verdict(0, 0),
            "per_day": [],
            "recall_queries": 0,
            "owner_questions": 0,
        }

    start_ts = datetime.combine(start, time.min, tzinfo=_tz())
    elapsed = (local_now.date() - start).days
    day = max(1, min(elapsed + 1, WEEK_DAYS))
    sent = await _count_sent(start_ts)
    acted = await _count_acted(start_ts)
    rate = acted / sent if sent else 0.0
    return {
        "start": start.isoformat(),
        "active": 0 <= elapsed < WEEK_DAYS,
        "day": day,
        "days_left": WEEK_DAYS - day,
        "sent": sent,
        "acted": acted,
        "tickets_pending_over_24h": pending_old,
        "response_rate": round(rate, 3),
        "verdict": _verdict(sent, acted),
        "per_day": await _per_day(start, start_ts, local_now.date()),
        "recall_queries": await _count_recall_queries(start_ts),
        "owner_questions": await _count_owner_questions(start_ts),
    }


def _verdict(sent: int, acted: int) -> str:
    rate = acted / sent if sent else 0.0
    return (
        "on track"
        if rate >= RESPONSE_RATE_OK or sent < MIN_SENT_FOR_VERDICT
        else "at risk"
    )


def format_status(status: dict[str, Any]) -> str:
    """One line for Telegram and the digest header."""
    if not status["start"]:
        return "Value week: not started"
    if not status["active"]:
        return f"Value week: finished (started {status['start']})"
    pct = round(status["response_rate"] * 100)
    return (
        f"Value week: day {status['day']}/{WEEK_DAYS} · sent {status['sent']}"
        f" · acted {status['acted']} ({pct}%)"
    )


def format_report(status: dict[str, Any]) -> str:
    """Multi-line Telegram reply for ``/week``."""
    lines = [format_status(status)]
    if status["start"]:
        lines.append(
            f"started {status['start']} · {status['days_left']} day(s) left"
            f" · verdict: {status['verdict']}"
        )
        if status["tickets_pending_over_24h"]:
            lines.append(
                f"tickets pending over 24h: {status['tickets_pending_over_24h']}"
            )
        for row in status["per_day"]:
            lines.append(f"- {row['date']}: sent {row['sent']}, acted {row['acted']}")
    return "\n".join(lines)


# --- queries ------------------------------------------------------------------


async def _count_sent(since: datetime) -> int:
    row = await db.fetchone(
        "SELECT count(*) AS n FROM hq.outbox WHERE sent_at >= %s"
        " AND (idempotency_key IS NULL OR idempotency_key NOT LIKE 'digest:%%')",
        (since,),
    )
    return int(row["n"]) if row else 0


async def _count_acted(since: datetime) -> int:
    row = await db.fetchone(
        "SELECT count(*) AS n FROM hq.events WHERE kind = %s AND ts >= %s",
        (EVENT_KIND, since),
    )
    return int(row["n"]) if row else 0


async def _count_recall_queries(since: datetime) -> int:
    """Agent calls to a recall tool (memory_search, recall_facts, vault_read)."""
    row = await db.fetchone(
        "SELECT count(*) AS n FROM hq.events WHERE kind = 'tool.called' AND ts >= %s"
        " AND agent IS NOT NULL AND payload->>'tool' = ANY(%s)",
        (since, list(RECALL_TOOLS)),
    )
    return int(row["n"]) if row else 0


async def _count_owner_questions(since: datetime) -> int:
    """Owner chat messages (``owner.action`` with action='chat')."""
    row = await db.fetchone(
        "SELECT count(*) AS n FROM hq.events WHERE kind = %s AND ts >= %s"
        " AND payload->>'action' = 'chat'",
        (EVENT_KIND, since),
    )
    return int(row["n"]) if row else 0


async def _tickets_pending_over_24h() -> int:
    row = await db.fetchone(
        "SELECT count(*) AS n FROM hq.tickets WHERE status = 'pending'"
        " AND created_at < now() - interval '24 hours'"
    )
    return int(row["n"]) if row else 0


async def _per_day(start: date, since: datetime, today: date) -> list[dict[str, Any]]:
    tz = settings().cron_tz
    sent_rows = await db.fetch(
        "SELECT to_char((sent_at AT TIME ZONE %s)::date, 'YYYY-MM-DD') AS d, count(*) AS n"
        " FROM hq.outbox WHERE sent_at >= %s"
        " AND (idempotency_key IS NULL OR idempotency_key NOT LIKE 'digest:%%')"
        " GROUP BY 1",
        (tz, since),
    )
    acted_rows = await db.fetch(
        "SELECT to_char((ts AT TIME ZONE %s)::date, 'YYYY-MM-DD') AS d, count(*) AS n"
        " FROM hq.events WHERE kind = %s AND ts >= %s GROUP BY 1",
        (tz, EVENT_KIND, since),
    )
    sent_by = {r["d"]: int(r["n"]) for r in sent_rows}
    acted_by = {r["d"]: int(r["n"]) for r in acted_rows}
    last = min(today, start + timedelta(days=WEEK_DAYS - 1))
    out = []
    d = start
    while d <= last:
        key = d.isoformat()
        out.append(
            {"date": key, "sent": sent_by.get(key, 0), "acted": acted_by.get(key, 0)}
        )
        d += timedelta(days=1)
    return out
