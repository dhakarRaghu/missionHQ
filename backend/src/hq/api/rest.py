"""Read/mutate REST endpoints. Every endpoint carries an explicit operation_id
(the generated TypeScript client keys off them). Mutations reuse the exact
paths Telegram uses, so both interfaces resolve the same durable state."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from hq import board, db, safety
from hq.api.deps import require_auth
from hq.config import settings
from hq.dbos_app import DBOS

router = APIRouter(dependencies=[Depends(require_auth)])


@router.get("/health", operation_id="getHealth")
async def health() -> dict:
    row = await db.fetchone("SELECT 1 AS ok")
    return {"ok": bool(row), "halted": safety.halted()}


@router.get("/tasks", operation_id="listTasks")
async def list_tasks(status: str | None = None, limit: int = 100) -> list[dict]:
    if status:
        return await db.fetch(
            "SELECT id::text, title, brief, agent, status, source, parent_id::text,"
            " created_at, updated_at FROM hq.tasks WHERE status = %s"
            " ORDER BY updated_at DESC LIMIT %s", (status, limit))
    return await db.fetch(
        "SELECT id::text, title, brief, agent, status, source, parent_id::text,"
        " created_at, updated_at FROM hq.tasks ORDER BY updated_at DESC LIMIT %s", (limit,))


@router.get("/tasks/{task_id}/events", operation_id="listTaskEvents")
async def list_task_events(task_id: str) -> list[dict]:
    return await db.fetch(
        "SELECT seq, ts, actor, event_type, data FROM hq.task_events"
        " WHERE task_id = %s ORDER BY seq", (task_id,))


@router.get("/runs", operation_id="listRuns")
async def list_runs(limit: int = 50) -> list[dict]:
    return await db.fetch(
        "SELECT id::text, task_id::text, agent, model, job_hash, started_at, ended_at,"
        " outcome, input_tokens, output_tokens, cost_usd, error"
        " FROM hq.runs ORDER BY started_at DESC LIMIT %s", (limit,))


@router.get("/tickets", operation_id="listTickets")
async def list_tickets(status: str = "pending") -> list[dict]:
    return await db.fetch(
        "SELECT id::text, task_id::text, tool_name, tool_args, action_class, status,"
        " created_at, resolved_at, resolved_via FROM hq.tickets WHERE status = %s"
        " ORDER BY created_at DESC LIMIT 100", (status,))


class ResolveTicketBody(BaseModel):
    verdict: str  # approved | denied


@router.post("/tickets/{ticket_id}/resolve", operation_id="resolveTicket")
async def resolve_ticket(ticket_id: str, body: ResolveTicketBody) -> dict:
    if body.verdict not in {"approved", "denied"}:
        raise HTTPException(422, "verdict must be approved or denied")
    row = await board.resolve_ticket(ticket_id, body.verdict, via="web")
    if row is None:
        return {"resolved": False, "reason": "already resolved"}
    await DBOS.send_async(row["wf_id"], f"{ticket_id}:{body.verdict}", topic="approval")
    return {"resolved": True, "verdict": body.verdict}


@router.get("/agents", operation_id="listAgents")
async def list_agents() -> list[dict]:
    from hq import engine

    out = []
    for name, (spec, _agent) in sorted(engine.registered_agents().items()):
        out.append({
            "name": name,
            "description": spec.description,
            "model": spec.model,
            "tools": spec.tools,
            "cron": [c.model_dump() for c in spec.cron],
            "paused": await safety.agent_paused(name),
            "spend_today_usd": await safety.spend_today_usd(name),
            "daily_cap_usd": spec.caps.daily_usd,
        })
    return out


class PauseBody(BaseModel):
    paused: bool


@router.post("/agents/{name}/pause", operation_id="setAgentPaused")
async def set_agent_paused(name: str, body: PauseBody) -> dict:
    from hq import engine

    if name not in engine.registered_agents():
        raise HTTPException(404, f"unknown agent {name}")
    await safety.set_agent_paused(name, body.paused)
    return {"agent": name, "paused": body.paused}


@router.get("/costs", operation_id="getCosts")
async def costs() -> dict:
    today = await safety.spend_today_usd()
    per_agent = await db.fetch(
        "SELECT agent, sum(cost_usd) AS usd, count(*) AS runs FROM hq.runs"
        " WHERE started_at >= now() - interval '7 days' GROUP BY agent ORDER BY usd DESC")
    return {
        "today_usd": today,
        "daily_cap_usd": settings().daily_spend_cap_usd,
        "week_by_agent": per_agent,
    }
