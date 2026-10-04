"""The follow-up clock on what he applied to, run once a day.

An applied role with no reply is due a follow-up 7 days later; after the
second touch and another 7 days it is ghosted. What is due reaches him
through sage's daily note (continuity) and the Jobs page (/api/pipeline/due).
Nothing here contacts anyone: he sends every follow-up himself.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

from hq import db, job_retention, outreach
from hq.config import settings
from hq.obs import emit


def today() -> date:
    return datetime.now(ZoneInfo(settings().cron_tz)).date()


async def pipeline_due(on: date | None = None) -> dict[str, list[dict[str, Any]]]:
    """Follow-ups due on or before `on`."""
    on = on or today()
    follow = await db.fetch(
        "SELECT id::text, company, role, url, applied_at, followup_due, touches FROM hq.jobs"
        " WHERE status = 'applied' AND followup_due IS NOT NULL AND followup_due <= %s"
        " AND touches < %s ORDER BY followup_due", (on, outreach.MAX_TOUCHES))
    return {"follow_ups": [dict(r) for r in follow]}


async def apply_clocks(on: date | None = None) -> dict[str, int]:
    """Applied roles past their last touch, with no reply, become ghosted."""
    on = on or today()
    ghosted = await db.fetch(
        "UPDATE hq.jobs SET status = 'ghosted', followup_due = NULL, updated_at = now()"
        " WHERE status = 'applied' AND followup_due IS NOT NULL AND followup_due <= %s"
        " AND touches >= %s RETURNING id::text", (on, outreach.MAX_TOUCHES))
    if ghosted:
        await emit("pipeline.clocks", payload={"ghosted": len(ghosted)})
    return {"ghosted": len(ghosted)}


async def funnel(days: int = job_retention.KEEP_DAYS) -> list[dict[str, Any]]:
    """How each channel did over the last `days`: found, strong, and how far
    its roles went. Counts, not rates: the numbers are small. The window is
    the ledger's: found and closed roles leave it after KEEP_DAYS, so a longer
    window would count their later stages but not the roles themselves."""
    return [dict(r) for r in await db.fetch(
        "SELECT coalesce(nullif(channel, ''), 'other') AS channel, count(*) AS found,"
        " count(*) FILTER (WHERE fit_bucket = 'strong') AS strong,"
        " count(*) FILTER (WHERE applied_at IS NOT NULL) AS applied,"
        " count(*) FILTER (WHERE status IN ('interviewing','offer')) AS interviewing,"
        " count(*) FILTER (WHERE status = 'offer') AS offers"
        " FROM hq.jobs WHERE first_seen >= now() - make_interval(days => %s)"
        " GROUP BY 1 ORDER BY found DESC", (days,))]
