"""The job-search ledger: record a verified role, and read back what is known.

One table, not two files. The reference project this borrows from keeps a
`seen-jobs.csv` for every role ever verified and a `job-tracker.csv` for the
ones worth acting on, and its own notes explain why: discovery memory has to
survive even for roles rejected today, or next week's search surfaces them
again. That reasoning is right. Two hand-edited CSVs are not, when the
database can dedupe and a dashboard can read it.

``record_job`` prefers the ATS provider's stable posting id. When a source has
no id, it falls back to company, role and location. The URL is deliberately not
part of the key because the same posting can move between an ATS and a careers
page.
"""

from __future__ import annotations

import logging
import re

from pydantic_ai import ModelRetry, RunContext

from hq import db
from hq.config import settings
from hq.obs import emit
from hq.safety import ActionClass, Trust
from hq.tools.registry import HQDeps, hq_tool

log = logging.getLogger(__name__)

BUCKETS = ("strong", "decent", "stretch")

# The lower bound of every "N years" figure in a free-text experience band.
# Group 1 is the floor: "0-3 years" -> 0, "3+ years" -> 3, "~4 yrs" -> 4.
# Only digits actually attached to a year word count, so "SDE2+ / ~4 yrs"
# reads as 4 and not as 2.
_YEAR_SPAN_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(?:(?:\+|-|–|—|to)\s*(?:\d+(?:\.\d+)?)?)?\s*\+?\s*"
    r"(?:yrs?\.?|years?)\b",
    re.IGNORECASE,
)


def min_years_required(experience_band: str) -> float | None:
    """The floor of the experience a posting asks for, or None when it names no
    number. The floor, not the ceiling: "2-4 years" is open to a candidate with
    two, so what matters is the smallest figure the posting will accept."""
    floors = [float(m.group(1)) for m in _YEAR_SPAN_RE.finditer(experience_band)]
    return min(floors) if floors else None

STATUSES = (
    "seen",
    "shortlisted",
    "applied",
    "interviewing",
    "offer",
    "rejected",
    "closed",
)
LIST_LIMIT = 50


def _normal(value: str) -> str:
    return " ".join(value.casefold().split())


def _dedupe_key(
    company: str, role: str, location: str, provider: str, external_id: str
) -> str:
    """Stable board id when available; conservative content identity otherwise."""
    provider, external_id = _normal(provider), external_id.strip()
    if provider and external_id:
        return f"ats:{provider}:{external_id}"
    return f"fallback:{_normal(company)}|{_normal(role)}|{_normal(location)}"


@hq_tool(action=ActionClass.VAULT_WRITE, trust=Trust.TOOL, owner_only=False)
async def record_job(
    ctx: RunContext[HQDeps],
    company: str,
    role: str,
    url: str,
    fit_score: int,
    why_fit: str,
    location: str = "",
    remote_policy: str = "",
    experience_band: str = "",
    compensation: str = "",
    stack: str = "",
    source: str = "",
    provider: str = "",
    external_id: str = "",
    next_step: str = "",
    referral: str = "",
) -> str:
    """Record one verified role in the job ledger, or update it if already known.

    Call this for every role you actually verified, including ones too weak to
    apply to. That is the point: a role written down once is never researched
    twice, and next week's search can skip it.

    `fit_score` is 0-10 from the rubric in your instructions, and `why_fit` is
    the one sentence justifying it. A score without a reason is not useful to
    anyone reading the board later.

    Always fill `experience_band` with what the posting actually asks for, and
    `compensation` with the package when the posting or a salary page names
    one. A role whose floor is at or above the owner's seniority ceiling is
    still recorded, so it is never researched twice, but it is filed closed
    rather than put in front of him.

    Verify the listing is real and open before recording it. A search result
    title is not verification.
    """
    company, role, url = company.strip(), role.strip(), url.strip()
    if not company or not role:
        raise ModelRetry("company and role are both required")
    if not url.startswith(("http://", "https://")):
        raise ModelRetry("url must be the full listing address, starting with https://")
    if not 0 <= int(fit_score) <= 10:
        raise ModelRetry("fit_score must be between 0 and 10")
    if not why_fit.strip():
        raise ModelRetry("why_fit is required: one sentence saying why this score")

    score = int(fit_score)
    bucket = "strong" if score >= 8 else ("decent" if score >= 6 else "stretch")
    key = _dedupe_key(company, role, location, provider, external_id)

    # Seniority is a hard fact about the owner, not a preference to weigh, so
    # it is applied here rather than trusted to the prompt. The row is still
    # written: skipping it entirely would only mean rediscovering the same
    # posting next week and spending another run rejecting it.
    bar = settings().job_max_min_years
    floor = min_years_required(experience_band)
    over_bar = floor is not None and floor >= bar
    status = "closed" if over_bar else "seen"
    note = (
        f"Closed on record: the posting asks for {floor:g}+ years and the owner"
        f" is early-career (bar is {bar:g})."
        if over_bar
        else ""
    )
    rows = await db.fetch(
        """
        INSERT INTO hq.jobs (company, role, url, source, provider, external_id,
                             dedupe_key, location, remote_policy, experience_band,
                             compensation, stack, fit_score, fit_bucket, why_fit,
                             next_step, referral, status, notes)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s)
        ON CONFLICT (dedupe_key) DO UPDATE SET
            -- A rediscovery refreshes facts but never overwrites a status the
            -- owner moved along.
            last_seen = now(), updated_at = now(),
            seen_count = hq.jobs.seen_count + 1,
            url = EXCLUDED.url,
            source = COALESCE(NULLIF(EXCLUDED.source, ''), hq.jobs.source),
            provider = COALESCE(NULLIF(EXCLUDED.provider, ''), hq.jobs.provider),
            external_id = COALESCE(NULLIF(EXCLUDED.external_id, ''), hq.jobs.external_id),
            location = COALESCE(NULLIF(EXCLUDED.location, ''), hq.jobs.location),
            remote_policy = COALESCE(NULLIF(EXCLUDED.remote_policy, ''), hq.jobs.remote_policy),
            experience_band = COALESCE(NULLIF(EXCLUDED.experience_band, ''), hq.jobs.experience_band),
            compensation = COALESCE(NULLIF(EXCLUDED.compensation, ''), hq.jobs.compensation),
            stack = COALESCE(NULLIF(EXCLUDED.stack, ''), hq.jobs.stack),
            fit_score = EXCLUDED.fit_score,
            fit_bucket = EXCLUDED.fit_bucket,
            why_fit = EXCLUDED.why_fit,
            next_step = COALESCE(NULLIF(EXCLUDED.next_step, ''), hq.jobs.next_step),
            referral = COALESCE(NULLIF(EXCLUDED.referral, ''), hq.jobs.referral)
        RETURNING id::text, seen_count, status
        """,
        (
            company,
            role,
            url,
            source.strip()[:60],
            provider.strip().lower()[:40],
            external_id.strip()[:160],
            key,
            location.strip()[:120],
            remote_policy.strip()[:80],
            experience_band.strip()[:60],
            compensation.strip()[:120],
            stack.strip()[:200],
            score,
            bucket,
            why_fit.strip()[:500],
            next_step.strip()[:300],
            referral.strip()[:500],
            status,
            note,
        ),
    )
    row = rows[0]
    await emit(
        "job.recorded",
        run_id=ctx.deps.run_id,
        task_id=ctx.deps.task_id,
        agent=ctx.deps.agent,
        payload={
            "company": company,
            "role": role,
            "fit_score": fit_score,
            "seen_count": row["seen_count"],
        },
    )
    again = f" (seen {row['seen_count']} times)" if row["seen_count"] > 1 else ""
    if over_bar and row["status"] == "closed":
        return (
            f"recorded {company} — {role} as CLOSED{again}: the posting asks for"
            f" {floor:g}+ years, over the owner's {bar:g}-year ceiling. It is in"
            " the ledger so it is not researched again. Do not look for a"
            " referral and do not report it as a candidate role."
        )
    return (
        f"recorded {company} — {role}: {fit_score}/10 {bucket}{again},"
        f" status {row['status']}"
    )


@hq_tool(action=ActionClass.READ, trust=Trust.VAULT)
async def list_jobs(
    ctx: RunContext[HQDeps], status: str = "", company: str = ""
) -> list[dict]:
    """Roles already in the ledger, newest first.

    Check this BEFORE researching a company, so you do not spend a run
    rediscovering something already recorded. Pass `company` to see what is
    known about one, or `status` to see a stage of the pipeline.
    """
    where: list[str] = ["true"]
    params: list[object] = []
    if status:
        if status not in STATUSES:
            raise ModelRetry(f"status must be one of {list(STATUSES)}")
        where.append("status = %s")
        params.append(status)
    if company.strip():
        where.append("company ILIKE %s")
        params.append(f"%{company.strip()}%")
    params.append(LIST_LIMIT)
    return await db.fetch(
        "SELECT company, role, url, source, provider, external_id, location,"
        " remote_policy, experience_band, compensation, stack, fit_score,"
        " fit_bucket, status, why_fit, next_step, referral, seen_count, last_seen"
        f" FROM hq.jobs WHERE {' AND '.join(where)}"
        " ORDER BY fit_score DESC, last_seen DESC LIMIT %s",
        tuple(params),
    )
