"""Read/mutate REST endpoints. Every endpoint carries an explicit operation_id
(the generated TypeScript client keys off them). Mutations reuse the exact
paths Telegram uses, so both interfaces resolve the same durable state."""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from hq import board, db, engagement, safety
from hq.api.deps import require_auth
from hq.config import settings
from hq.dbos_app import DBOS
from hq.obs import emit

log = logging.getLogger(__name__)
router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/health", operation_id="getHealth")
async def health() -> dict:
    row = await db.fetchone("SELECT 1 AS ok")
    return {"ok": bool(row), "halted": safety.halted()}


# Task rows carry the id of their latest run so the board can link to it.
TASK_SELECT = (
    "SELECT t.id::text, t.title, t.brief, t.agent, t.status, t.source, t.parent_id::text,"
    " t.created_at, t.updated_at, r.id::text AS run_id FROM hq.tasks t"
    " LEFT JOIN LATERAL (SELECT id FROM hq.runs WHERE task_id = t.id"
    " ORDER BY started_at DESC LIMIT 1) r ON true"
)


@router.get("/tasks", operation_id="listTasks")
async def list_tasks(status: str | None = None, limit: int = 100) -> list[dict]:
    if status:
        return await db.fetch(
            f"{TASK_SELECT} WHERE t.status = %s ORDER BY t.updated_at DESC LIMIT %s",
            (status, limit),
        )
    # Archived tasks are left out unless asked for by name: they are finished
    # work the owner has stopped looking at, and the board is for what is live.
    return await db.fetch(
        f"{TASK_SELECT} WHERE t.status <> 'archived' ORDER BY t.updated_at DESC LIMIT %s",
        (limit,),
    )


class CreateTaskBody(BaseModel):
    agent: str
    title: str
    brief: str = ""


@router.post("/tasks", operation_id="createTask", status_code=201)
async def create_task(body: CreateTaskBody) -> dict:
    """Queue work for an agent. Goes through engine.dispatch like cron and chat
    do, so there is still exactly one enqueue path."""
    from hq import engine

    if body.agent not in engine.registered_agents():
        raise HTTPException(404, f"unknown agent {body.agent}")
    task_id = await engine.dispatch(
        agent=body.agent, title=body.title, brief=body.brief, source="web"
    )
    await engagement.record_owner_action("web", "new_task")
    return {"task_id": task_id}


@router.post("/tasks/{task_id}/cancel", operation_id="cancelTask")
async def cancel_task(task_id: str) -> dict:
    """Stop a run that is still going.

    A run can take minutes, and until now the only way to end one was to wait
    or restart the backend. Cancelling the DBOS workflow stops it at its next
    step boundary; completed steps stay committed, which is the point of them
    being steps. The board is marked from here rather than from inside the
    workflow, because a cancelled workflow does not get to run its own
    bookkeeping.
    """
    rows = await db.fetch(
        "SELECT r.wf_id, t.status FROM hq.tasks t"
        " LEFT JOIN LATERAL (SELECT wf_id FROM hq.runs WHERE task_id = t.id"
        "   ORDER BY started_at DESC LIMIT 1) r ON true"
        " WHERE t.id = %s",
        (task_id,),
    )
    if not rows:
        raise HTTPException(404, "no such task")
    if rows[0]["status"] not in {"running", "needs_approval", "backlog"}:
        return {"cancelled": False, "reason": f"task is {rows[0]['status']}"}

    wf_id = rows[0]["wf_id"]
    if wf_id:
        try:
            await DBOS.cancel_workflow_async(wf_id)
        except Exception as exc:  # noqa: BLE001 — mark the board even if it already ended
            log.warning("cancel of workflow %s failed: %s", wf_id, exc)

    # The workflow cannot close its own run row once cancelled, and a row left
    # with outcome NULL would count against the success rate in `hq.cli health`.
    # A deliberate stop is not a failure, so record it as its own outcome.
    await db.execute(
        "UPDATE hq.runs SET outcome = 'cancelled', ended_at = now()"
        " WHERE task_id = %s AND ended_at IS NULL",
        (task_id,),
    )
    await board.apply(
        task_id,
        "cancelled",
        actor="owner",
        status="failed",
        data={"reason": "cancelled by the owner"},
    )
    await engagement.record_owner_action("web", "cancel_task")
    return {"cancelled": True}


@router.post("/tasks/{task_id}/retry", operation_id="retryTask")
async def retry_task(task_id: str) -> dict:
    """Run a stopped task again, from the board.

    Blocked and failed are where tasks go to be forgotten: a transient gateway
    failure or an approval that timed out leaves work the owner still wants,
    and until now the only way back was to retype it as a new task, which lost
    the brief and the history. This re-runs the same row, so its event log
    keeps every attempt in one place.
    """
    from hq import engine

    row = await db.fetchone("SELECT status FROM hq.tasks WHERE id = %s", (task_id,))
    if row is None:
        raise HTTPException(404, "no such task")
    if row["status"] not in {"blocked", "failed"}:
        return {"retried": False, "reason": f"task is {row['status']}"}
    await board.apply(task_id, "retried", actor="owner", status="backlog",
                      data={"reason": "retried by the owner"})
    await engine.requeue(task_id)
    await engagement.record_owner_action("web", "retry_task")
    return {"retried": True}


@router.post("/tasks/{task_id}/dismiss", operation_id="dismissTask")
async def dismiss_task(task_id: str) -> dict:
    """Take a finished or stopped task off the board.

    Archived, not deleted. The row, its runs and its events all stay, so the
    Runs page and the health score still see what happened; the board simply
    stops showing work the owner has finished with. A task still running has
    to be cancelled first — dismissing one would hide a run that is still
    spending money.
    """
    row = await db.fetchone("SELECT status FROM hq.tasks WHERE id = %s", (task_id,))
    if row is None:
        raise HTTPException(404, "no such task")
    if row["status"] in {"running", "needs_approval"}:
        return {"dismissed": False,
                "reason": f"task is {row['status']}; cancel it first"}
    await board.apply(task_id, "dismissed", actor="owner", status="archived",
                      data={"reason": "dismissed by the owner"})
    await engagement.record_owner_action("web", "dismiss_task")
    return {"dismissed": True}


@router.get("/tasks/{task_id}/events", operation_id="listTaskEvents")
async def list_task_events(task_id: str) -> list[dict]:
    return await db.fetch(
        "SELECT seq, ts, actor, event_type, data FROM hq.task_events"
        " WHERE task_id = %s ORDER BY seq",
        (task_id,),
    )


JOB_SELECT = (
    "SELECT id::text, company, role, url, source, provider, external_id,"
    " location, remote_policy,"
    " experience_band, compensation, stack, fit_score, fit_bucket, status,"
    " why_fit, next_step, notes, referral, seen_count, first_seen, last_seen"
    " FROM hq.jobs"
)


@router.get("/jobs", operation_id="listJobs")
async def list_jobs(status: str | None = None, limit: int = 200) -> list[dict]:
    """The job ledger. Everything hunter verified, strongest fit first."""
    if status:
        if status not in JOB_STATUSES:
            raise HTTPException(400, f"status must be one of {list(JOB_STATUSES)}")
        return await db.fetch(
            f"{JOB_SELECT} WHERE status = %s ORDER BY fit_score DESC, last_seen DESC"
            " LIMIT %s",
            (status, limit),
        )
    return await db.fetch(
        f"{JOB_SELECT} ORDER BY fit_score DESC, last_seen DESC LIMIT %s", (limit,)
    )


class JobPatch(BaseModel):
    """What the owner may change from the dashboard. Everything else is
    hunter's finding and stays as recorded."""

    status: str | None = None
    next_step: str | None = None
    notes: str | None = None
    referral: str | None = None


JOB_STATUSES = (
    "seen",
    "shortlisted",
    "applied",
    "interviewing",
    "offer",
    "rejected",
    "closed",
)


@router.patch("/jobs/{job_id}", operation_id="updateJob")
async def update_job(job_id: str, body: JobPatch) -> dict:
    """Move a role along the pipeline, or add a note to it."""
    sets, params = [], []
    if body.status is not None:
        if body.status not in JOB_STATUSES:
            raise HTTPException(400, f"status must be one of {list(JOB_STATUSES)}")
        sets.append("status = %s")
        params.append(body.status)
    for field in ("next_step", "notes", "referral"):
        value = getattr(body, field)
        if value is not None:
            sets.append(f"{field} = %s")
            params.append(value[:2000])
    if not sets:
        raise HTTPException(400, "nothing to update")
    sets.append("updated_at = now()")
    params.append(job_id)
    rows = await db.fetch(
        f"UPDATE hq.jobs SET {', '.join(sets)} WHERE id = %s RETURNING id::text",
        tuple(params),
    )
    if not rows:
        raise HTTPException(404, "no such job")
    await engagement.record_owner_action("web", "update_job")
    await emit("job.updated", payload={"job_id": job_id, "fields": sets[:-1]})
    referral_task = None
    if body.status == "shortlisted":
        referral_task = await _hunt_referral(job_id)
    return {"ok": True, "referral_task_id": referral_task}


async def _hunt_referral(job_id: str) -> str | None:
    """Shortlisting is the owner saying this one is worth a real approach, so
    that is the moment to go and find the person to ask.

    Operator does it, not hunter: the people are on LinkedIn, which
    ``browser_read`` refuses in code, and only the signed-in browser can see a
    first-degree connection. The brief names one company and one role, which is
    what keeps the browse guard's "bounded" test satisfiable — an open-ended
    walk of a company's employees is exactly what it is there to refuse.

    Best effort. A dispatch that fails must not fail the owner's status change,
    which has already been committed.
    """
    from hq import engine

    job = await db.fetchone(
        "SELECT company, role, url, referral FROM hq.jobs WHERE id = %s", (job_id,)
    )
    if job is None or "operator" not in engine.registered_agents():
        return None
    known = (job["referral"] or "").strip()
    brief = (
        f"Find the one person to ask for a referral into {job['company']} for"
        f" their {job['role']} role ({job['url']}).\n\n"
        "Start on the company's LinkedIn people page, in ONE tab:\n"
        "  https://www.linkedin.com/company/<slug>/people/?facetNetwork=F\n"
        "Try the obvious slug first. That page lists his own connections at"
        " the company with their headlines, which is usually the entire"
        " answer. Do not search Google for this, and do not open individual"
        " profiles — the headline is enough to name the right person, and"
        " walking profiles is what gets an account restricted.\n\n"
        "Report, in this order of preference:\n"
        "1. An existing first-degree connection at the company. If there is"
        " one, that is the answer; say how the owner knows them.\n"
        "2. Otherwise the named engineering leader or recruiter who visibly"
        " owns this role or its team, from the same page.\n"
        "3. If neither is verifiable, give the target persona and the exact"
        " page to check by hand. Never invent a person or a relationship.\n\n"
        "Also report the shared ground the owner could open with: a post, a"
        " repo, a talk, a shared school or employer. A referral ask with no"
        " shared ground is a cold ask with extra steps.\n\n"
        "Read only. Do not connect, follow, message, or apply. One tab, and"
        " close it when you are done."
    )
    if known:
        brief += f"\n\nWhat hunter already recorded, to confirm or correct:\n{known}"
    try:
        return await engine.dispatch(
            agent="operator",
            title=f"Referral path: {job['company']} — {job['role']}"[:120],
            brief=brief,
            source="web",
            dedup_key=f"referral:{job_id}",
        )
    except Exception as exc:  # noqa: BLE001 — the status change already stands
        log.warning("could not queue referral hunt for job %s: %s", job_id, exc)
        await emit("job.referral_hunt_failed",
                   payload={"job_id": job_id, "error": str(exc)[:200]})
        return None


@router.get("/runs", operation_id="listRuns")
async def list_runs(limit: int = 50) -> list[dict]:
    return await db.fetch(
        "SELECT id::text, task_id::text, agent, model, job_hash, started_at, ended_at,"
        " outcome, input_tokens, output_tokens, cost_usd, error"
        " FROM hq.runs ORDER BY started_at DESC LIMIT %s",
        (limit,),
    )


RUN_COLUMNS = (
    "r.id::text, r.task_id::text, r.wf_id, r.agent, r.model, r.job_hash, r.started_at,"
    " r.ended_at, r.outcome, r.input_tokens, r.output_tokens, r.cost_usd, r.stall_count, r.error"
)
# hq.messages has no run reference. A chat run's history row is written right
# after ended_at; this is how long after ended_at we still accept it.
TRANSCRIPT_GRACE = timedelta(seconds=60)


@router.get("/runs/{run_id}", operation_id="getRunDetail")
async def get_run_detail(run_id: str) -> dict:
    """One run with its event timeline, its approval tickets and, for chat
    runs, the user/assistant turns of that conversation round."""
    run = (
        await db.fetchone(
            f"SELECT {RUN_COLUMNS}, t.title AS task_title, t.brief AS task_brief"
            " FROM hq.runs r LEFT JOIN hq.tasks t ON t.id = r.task_id WHERE r.id = %s::uuid",
            (run_id,),
        )
        if _is_uuid(run_id)
        else None
    )
    if run is None:
        raise HTTPException(404, f"unknown run {run_id}")
    events = await db.fetch(
        "SELECT id, ts, task_id::text, agent, kind, payload FROM hq.events"
        " WHERE run_id = %s ORDER BY id",
        (run_id,),
    )
    tickets = await db.fetch(
        "SELECT id::text, task_id::text, tool_name, tool_args, action_class, status,"
        " created_at, resolved_at, resolved_via FROM hq.tickets WHERE run_id = %s"
        " ORDER BY created_at",
        (run_id,),
    )
    transcript, reason = await _chat_transcript(run)
    return {
        "run": run,
        "events": events,
        "tickets": tickets,
        "transcript": transcript,
        "transcript_reason": reason,
    }


def _is_uuid(value: str) -> bool:
    import uuid

    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


async def _chat_transcript(run: dict[str, Any]) -> tuple[list[dict] | None, str | None]:
    """Turns of the chat round this run answered, or (None, why-not).

    Chat runs have no task and store their history in hq.messages, which does
    not reference the run. The match is: same agent, history row written
    between started_at and ended_at + grace, and exactly one such row. Any
    ambiguity omits the transcript rather than showing another session's chat."""
    from hq.api.chat import _transcript

    if run["task_id"] is not None:
        return None, "task run"
    if run["ended_at"] is None:
        return None, "run still going"
    rows = await db.fetch(
        "SELECT history FROM hq.messages WHERE agent = %s AND ts >= %s AND ts <= %s"
        " ORDER BY id LIMIT 2",
        (run["agent"], run["started_at"], run["ended_at"] + TRANSCRIPT_GRACE),
    )
    if not rows:
        return None, "no stored history in the run's time window"
    if len(rows) > 1:
        return None, "more than one history row in the run's time window"
    turns = _transcript(rows[0]["history"])
    # The stored history is the whole conversation; keep the last round only.
    last_user = max(
        (i for i, t in enumerate(turns) if t["role"] == "user"), default=None
    )
    return (turns[last_user:] if last_user is not None else turns), None


TICKET_STATUSES = ("pending", "approved", "denied", "expired")


@router.get("/tickets", operation_id="listTickets")
async def list_tickets(status: str = "pending", limit: int = 100) -> list[dict]:
    """Tickets in one or more states (``status=approved,denied`` for the
    resolved view), newest first, with the agent of the run that asked."""
    wanted = [s.strip() for s in status.split(",") if s.strip()]
    unknown = [s for s in wanted if s not in TICKET_STATUSES]
    if not wanted or unknown:
        raise HTTPException(422, f"status must be one of {', '.join(TICKET_STATUSES)}")
    return await db.fetch(
        "SELECT k.id::text, k.task_id::text, k.run_id::text, r.agent, k.tool_name,"
        " k.tool_args, k.action_class, k.status, k.created_at, k.resolved_at, k.resolved_via"
        " FROM hq.tickets k LEFT JOIN hq.runs r ON r.id = k.run_id"
        " WHERE k.status = ANY(%s) ORDER BY k.created_at DESC LIMIT %s",
        (wanted, max(1, min(limit, 500))),
    )


class ResolveTicketBody(BaseModel):
    verdict: str  # approved | denied


@router.post("/tickets/{ticket_id}/resolve", operation_id="resolveTicket")
async def resolve_ticket(ticket_id: str, body: ResolveTicketBody) -> dict:
    if body.verdict not in {"approved", "denied"}:
        raise HTTPException(422, "verdict must be approved or denied")
    await engagement.record_owner_action(
        "web", "approve" if body.verdict == "approved" else "deny"
    )
    row = await board.resolve_ticket(ticket_id, body.verdict, via="web")
    if row is None:
        return {"resolved": False, "reason": "already resolved"}
    await DBOS.send_async(row["wf_id"], f"{ticket_id}:{body.verdict}", topic="approval")
    return {"resolved": True, "verdict": body.verdict}


@router.get("/engagement", operation_id="getEngagement")
async def get_engagement() -> dict:
    """Value-week status: what was sent, what the owner acted on, the verdict."""
    return await engagement.value_week_status()


@router.post("/engagement/start", operation_id="startValueWeek")
async def start_value_week() -> dict:
    """Start the 7-day value week (no-op when already started). Returns the
    same shape as GET /engagement."""
    await engagement.start_value_week()
    return await engagement.value_week_status()


@router.get("/agents", operation_id="listAgents")
async def list_agents() -> list[dict]:
    from hq import engine

    out = []
    for name, (spec, _agent) in sorted(engine.registered_agents().items()):
        out.append(
            {
                "name": name,
                "description": spec.description,
                "model": spec.model,
                "tools": spec.tools,
                "cron": [c.model_dump() for c in spec.cron],
                "paused": await safety.agent_paused(name),
                "spend_today_usd": await safety.spend_today_usd(name),
                "daily_cap_usd": spec.caps.daily_usd,
                "caps": spec.caps.model_dump(),
                "vault_write_scopes": spec.vault_write_scopes(),
            }
        )
    return out


@router.get("/agents/drafts", operation_id="listAgentDrafts")
async def list_agent_drafts() -> list[dict]:
    """Agent folders whose job.md says ``status: draft`` (written by the
    factory agent after the owner approved the draft ticket)."""
    import asyncio

    from hq.tools import factory_tools

    return await asyncio.to_thread(factory_tools.list_drafts)


@router.post("/agents/{name}/activate", operation_id="activateAgent")
async def activate_agent(name: str) -> dict:
    """Owner-only: flip a draft to active after re-validation, then restart.

    Agents load only at startup (DBOSDurability agents are built before
    DBOS.launch()), so the process exits 2 s after this reply and launchd
    (KeepAlive) starts it again with the new agent loaded."""
    import asyncio

    from hq.tools import factory_tools

    try:
        message = await asyncio.to_thread(factory_tools.activate_agent, name)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from None
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    factory_tools.schedule_restart()
    return {"activated": name, "restarting": True, "message": message}


class PauseBody(BaseModel):
    paused: bool


@router.post("/agents/{name}/pause", operation_id="setAgentPaused")
async def set_agent_paused(name: str, body: PauseBody) -> dict:
    from hq import engine

    if name not in engine.registered_agents():
        raise HTTPException(404, f"unknown agent {name}")
    await safety.set_agent_paused(name, body.paused)
    return {"agent": name, "paused": body.paused}


@router.get("/evals", operation_id="listEvalRuns")
async def list_eval_runs(agent: str | None = None, limit: int = 20) -> list[dict]:
    """Recent eval runs (newest first), optionally for one agent."""
    from hq import evals

    return await evals.history(agent, limit=limit)


@router.get("/evals/latest", operation_id="latestEvalScores")
async def latest_eval_scores() -> list[dict]:
    """One row per agent: its most recent eval score, case count and time."""
    from hq import evals

    return await evals.latest_scores()


@router.get("/costs/daily", operation_id="getDailyCosts")
async def daily_costs(days: int = 14) -> list[dict]:
    """Spend and run count per (day, agent) for the last ``days`` days.
    Days are calendar days in CRON_TZ, the owner's scheduling timezone."""
    days = max(1, min(days, 90))
    tz = settings().cron_tz
    rows = await db.fetch(
        "SELECT to_char((started_at AT TIME ZONE %s)::date, 'YYYY-MM-DD') AS date, agent,"
        " sum(cost_usd) AS usd, count(*) AS runs FROM hq.runs"
        " WHERE started_at >= ((now() AT TIME ZONE %s)::date - make_interval(days => %s))"
        " AT TIME ZONE %s GROUP BY 1, 2 ORDER BY 1, 2",
        (tz, tz, days - 1, tz),
    )
    return [{**r, "usd": float(r["usd"])} for r in rows]


@router.get("/costs", operation_id="getCosts")
async def costs() -> dict:
    today = await safety.spend_today_usd()
    per_agent = await db.fetch(
        "SELECT agent, sum(cost_usd) AS usd, count(*) AS runs FROM hq.runs"
        " WHERE started_at >= now() - interval '7 days' GROUP BY agent ORDER BY usd DESC"
    )
    return {
        "today_usd": today,
        "daily_cap_usd": settings().daily_spend_cap_usd,
        "week_by_agent": per_agent,
    }
