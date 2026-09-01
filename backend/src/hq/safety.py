"""Action classes, budgets, HALT, pause/resume. Deterministic policy — no model involved."""

from __future__ import annotations

from enum import StrEnum

from hq import db
from hq.config import settings


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


async def spend_today_usd(agent: str | None = None) -> float:
    if agent is None:
        row = await db.fetchone(
            "SELECT coalesce(sum(cost_usd), 0) AS c FROM hq.runs"
            " WHERE started_at >= date_trunc('day', now())"
        )
    else:
        row = await db.fetchone(
            "SELECT coalesce(sum(cost_usd), 0) AS c FROM hq.runs"
            " WHERE started_at >= date_trunc('day', now()) AND agent = %s",
            (agent,),
        )
    return float(row["c"])


async def spend_cap_hit(agent: str, agent_daily_cap: float) -> str | None:
    """Returns a human reason when a cap blocks a run, else None."""
    if await spend_today_usd() >= settings().daily_spend_cap_usd:
        return f"system daily spend cap ${settings().daily_spend_cap_usd:.2f} reached"
    if await spend_today_usd(agent) >= agent_daily_cap:
        return f"agent {agent} daily cap ${agent_daily_cap:.2f} reached"
    return None


async def notifications_sent_today() -> int:
    row = await db.fetchone(
        "SELECT count(*) AS n FROM hq.events"
        " WHERE kind = 'notify' AND ts >= date_trunc('day', now())"
    )
    return int(row["n"])


async def notification_budget_left() -> bool:
    return await notifications_sent_today() < settings().notifications_per_day
