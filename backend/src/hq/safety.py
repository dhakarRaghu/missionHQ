"""Action classes, budgets, HALT, pause/resume. Deterministic policy — no model involved."""

from __future__ import annotations

import json
import re
from enum import StrEnum
from typing import Any

from hq import db
from hq.config import settings

# --- deterministic guardrail -------------------------------------------------
# Runs before any approval ticket is opened. Pure policy: no model involved.

GUARD_MAX_ARGS_CHARS = 8000
GUARD_DENIAL_WINDOW = "24 hours"
_SECRET_PATTERNS = (
    re.compile(r"sk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"BEGIN PRIVATE KEY"),
)

# "Today" means the calendar day in CRON_TZ, not the Postgres server timezone.
_TODAY = "date_trunc('day', now() AT TIME ZONE %s)"


class ActionClass(StrEnum):
    NOTIFY = "notify"
    READ = "read"
    VAULT_WRITE = "vault_write"
    EXTERNAL_WRITE = "external_write"  # ticket required
    SPEND = "spend"                    # ticket + cap required


class Trust(StrEnum):
    USER = "user"
    VAULT = "vault"
    TOOL = "tool"
    WEB = "web"


def halted() -> bool:
    return settings().halt_file.exists()


async def agent_paused(agent: str) -> bool:
    row = await db.fetchone("SELECT value FROM hq.control WHERE key = %s", (f"paused:{agent}",))
    return bool(row and row["value"] is True)


async def set_agent_paused(agent: str, paused: bool) -> None:
    await db.execute(
        """
        INSERT INTO hq.control (key, value, updated_at) VALUES (%s, %s, now())
        ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = now()
        """,
        (f"paused:{agent}", db.jsonb(paused)),
    )


# A run's totals from its recorded model calls (hq.model_calls, one row per
# attempt). NULL when the run has none, so callers coalesce to what they had.
CALLS_SUM = "(SELECT sum(mc.{col}) FROM hq.model_calls mc WHERE mc.run_id = r.id)"
# SET clause that costs a run being closed by someone other than its workflow
# (the watchdog, an owner cancel): what it spent before it stopped.
CALLS_COSTED = (
    f"input_tokens = coalesce({CALLS_SUM.format(col='input_tokens')}, r.input_tokens),"
    f" output_tokens = coalesce({CALLS_SUM.format(col='output_tokens')}, r.output_tokens),"
    f" cost_usd = coalesce({CALLS_SUM.format(col='cost_usd')}, r.cost_usd)"
)


async def spend_today_usd(agent: str | None = None) -> float:
    """Today's spend: every recorded model call, including those of runs
    still going, plus the cost of runs that have no call rows (the claude
    CLI, and runs from before calls were recorded)."""
    tz = settings().cron_tz
    who_calls = "" if agent is None else " AND mc.agent = %s"
    who_runs = "" if agent is None else " AND r.agent = %s"
    params: tuple = (tz, tz) + ((agent,) if agent else ()) + (tz, tz) + ((agent,) if agent else ())
    row = await db.fetchone(
        "SELECT coalesce((SELECT sum(mc.cost_usd) FROM hq.model_calls mc"
        f"   WHERE mc.started_at AT TIME ZONE %s >= {_TODAY}{who_calls}), 0)"
        " + coalesce((SELECT sum(r.cost_usd) FROM hq.runs r"
        f"   WHERE r.started_at AT TIME ZONE %s >= {_TODAY}{who_runs}"
        "   AND NOT EXISTS (SELECT 1 FROM hq.model_calls mc WHERE mc.run_id = r.id)), 0)"
        " AS c",
        params,
    )
    return float(row["c"]) if row else 0.0


async def spend_cap_hit(agent: str, agent_daily_cap: float) -> str | None:
    """Returns a human reason when a cap blocks a run, else None."""
    if await spend_today_usd() >= settings().daily_spend_cap_usd:
        return f"system daily spend cap ${settings().daily_spend_cap_usd:.2f} reached"
    if await spend_today_usd(agent) >= agent_daily_cap:
        return f"agent {agent} daily cap ${agent_daily_cap:.2f} reached"
    return None


async def notifications_sent_today() -> int:
    tz = settings().cron_tz
    row = await db.fetchone(
        "SELECT count(*) AS n FROM hq.events"
        f" WHERE kind = 'notify' AND ts AT TIME ZONE %s >= {_TODAY}",
        (tz, tz),
    )
    return int(row["n"]) if row else 0


async def notification_budget_left() -> bool:
    return await notifications_sent_today() < settings().notifications_per_day


# --- deterministic guardrail -------------------------------------------------

def serialize_args(args: dict[str, Any]) -> str:
    """Canonical JSON for one tool call's arguments (stable key order)."""
    return json.dumps(args, sort_keys=True, default=str)


def _contains_secret(text: str) -> bool:
    if any(p.search(text) for p in _SECRET_PATTERNS):
        return True
    s = settings()
    for value in (s.gateway_api_key, s.telegram_bot_token):
        if value and value in text:
            return True
    return False


async def guard_deterministic(tool_name: str, args: dict[str, Any], agent: str) -> str | None:
    """Denial reason for an approval-gated tool call, or None to let it through.

    Denies when: any argument carries a secret-looking token or one of this
    deployment's own credentials; the serialized arguments exceed
    ``GUARD_MAX_ARGS_CHARS``; or the owner already denied the same
    (agent, tool, args) within ``GUARD_DENIAL_WINDOW``. Guardrail denials are
    not counted as owner denials, so a refusal reason never masks another.
    """
    text = serialize_args(args)
    if len(text) > GUARD_MAX_ARGS_CHARS:
        return f"arguments are {len(text)} chars; limit is {GUARD_MAX_ARGS_CHARS}"
    if _contains_secret(text):
        return "arguments contain a secret-looking token"
    row = await db.fetchone(
        f"""
        SELECT t.id::text, t.resolved_at FROM hq.tickets t
        JOIN hq.runs r ON r.id = t.run_id
        WHERE r.agent = %s AND t.tool_name = %s AND t.tool_args = %s::jsonb
          AND t.status = 'denied'
          AND coalesce(t.resolved_via, '') NOT LIKE 'guardrail:%%'
          AND t.resolved_at > now() - interval '{GUARD_DENIAL_WINDOW}'
        ORDER BY t.resolved_at DESC LIMIT 1
        """,
        (agent, tool_name, text),
    )
    if row is not None:
        return (
            f"owner denied the same {tool_name} call within the last {GUARD_DENIAL_WINDOW}"
            f" (ticket {row['id']})"
        )
    return None
