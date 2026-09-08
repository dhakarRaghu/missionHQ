"""The job-search ledger: record a verified role, and read back what is known.

One table, not two files. The reference project this borrows from keeps a
`seen-jobs.csv` for every role ever verified and a `job-tracker.csv` for the
ones worth acting on, and its own notes explain why: discovery memory has to
survive even for roles rejected today, or next week's search surfaces them
again. That reasoning is right. Two hand-edited CSVs are not, when the
database can dedupe and a dashboard can read it.

``record_job`` upserts on company plus role, deliberately not on the URL: the
same posting moves between an ATS and a careers page, and the reference
project's notes call that out as the thing that creates duplicates.
"""

from __future__ import annotations

import logging

from pydantic_ai import ModelRetry, RunContext

from hq import db
from hq.obs import emit
from hq.safety import ActionClass, Trust
from hq.tools.registry import HQDeps, hq_tool

log = logging.getLogger(__name__)

BUCKETS = ("strong", "decent", "stretch")
STATUSES = ("seen", "shortlisted", "applied", "interviewing", "offer",
            "rejected", "closed")
LIST_LIMIT = 50


@hq_tool(action=ActionClass.VAULT_WRITE, trust=Trust.TOOL, owner_only=False)
async def record_job(
    ctx: RunContext[HQDeps],
    company: str,
    role: str,
    url: str,
    fit_score: int,
    why_fit: str,
    location: str = "",
    experience_band: str = "",
    stack: str = "",
    source: str = "",
    next_step: str = "",
) -> str:
    """Record one verified role in the job ledger, or update it if already known.

    Call this for every role you actually verified, including ones too weak to
    apply to. That is the point: a role written down once is never researched
    twice, and next week's search can skip it.

    `fit_score` is 0-10 from the rubric in your instructions, and `why_fit` is
    the one sentence justifying it. A score without a reason is not useful to
    anyone reading the board later.

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

    bucket = "strong" if fit_score >= 8 else ("decent" if fit_score >= 6 else "stretch")
    rows = await db.fetch(
        """
        INSERT INTO hq.jobs (company, role, url, source, location,
                             experience_band, stack, fit_score, fit_bucket,
                             why_fit, next_step)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ON CONFLICT (lower(company), lower(role)) DO UPDATE SET
            -- A rediscovery updates freshness and keeps the better link, but
            -- never overwrites a status the owner moved along.
            last_seen = now(), updated_at = now(),
            seen_count = hq.jobs.seen_count + 1,
            url = EXCLUDED.url,
            fit_score = EXCLUDED.fit_score,
            fit_bucket = EXCLUDED.fit_bucket,
            why_fit = EXCLUDED.why_fit
        RETURNING id::text, seen_count, status
        """,
        (company, role, url, source[:60], location[:120], experience_band[:60],
         stack[:200], int(fit_score), bucket, why_fit[:500], next_step[:300]),
    )
    row = rows[0]
    await emit("job.recorded", run_id=ctx.deps.run_id, task_id=ctx.deps.task_id,
               agent=ctx.deps.agent,
               payload={"company": company, "role": role, "fit_score": fit_score,
                        "seen_count": row["seen_count"]})
    again = f" (seen {row['seen_count']} times)" if row["seen_count"] > 1 else ""
    return (f"recorded {company} — {role}: {fit_score}/10 {bucket}{again},"
            f" status {row['status']}")


@hq_tool(action=ActionClass.READ, trust=Trust.VAULT)
async def list_jobs(ctx: RunContext[HQDeps], status: str = "", company: str = "") -> list[dict]:
    """Roles already in the ledger, newest first.

    Check this BEFORE researching a company, so you do not spend a run
    rediscovering something already recorded. Pass `company` to see what is
    known about one, or `status` to see a stage of the pipeline.
    """
    where, params = ["true"], []
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
        "SELECT company, role, url, location, fit_score, fit_bucket, status,"
        " why_fit, next_step, referral, seen_count, last_seen"
        f" FROM hq.jobs WHERE {' AND '.join(where)}"
        " ORDER BY fit_score DESC, last_seen DESC LIMIT %s",
        tuple(params),
    )
