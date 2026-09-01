"""Workflows, queues, cron fan-out, reaper, watchdog.

``dispatch()`` is the ONE enqueue path: cron handlers, chat, and agent
delegation all go through it. Agents + queues are registered in the API
lifespan BEFORE DBOS.launch().
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime

import httpx
from pydantic_ai import Agent
from pydantic_ai.durable_exec.dbos import DBOSDurability
from pydantic_ai.messages import ModelMessagesTypeAdapter

from hq import board, db, llm, runner, safety
from hq.config import settings
from hq.dbos_app import DBOS
from hq.loader import AgentSpec, build_agent, scan
from hq.obs import emit

AGENTS: dict[str, tuple[AgentSpec, Agent]] = {}
_queues: dict[str, object] = {}


def registered_agents() -> dict[str, tuple[AgentSpec, Agent]]:
    return AGENTS


def bootstrap_pre_launch() -> None:
    """Agents + cron workflows. MUST run BEFORE DBOS.launch()."""
    set_process_timezone()
    durability = DBOSDurability(models=llm.registry().all_instances())
    for name, spec in scan().items():
        AGENTS[name] = (spec, build_agent(spec, durability))
    _register_cron()


async def bootstrap_post_launch() -> None:
    """Queues. The async registration API requires a launched executor."""
    _queues["tasks"] = await DBOS.register_queue_async("tasks", worker_concurrency=1)
    _queues["chat"] = await DBOS.register_queue_async("chat", worker_concurrency=2)


async def dispatch(
    *, agent: str, title: str, brief: str = "", source: str = "system",
    parent_task_id: str | None = None, dedup_key: str | None = None,
    payload: dict | None = None,
) -> str | None:
    if agent not in AGENTS:
        raise KeyError(f"unknown agent {agent!r}; loaded: {sorted(AGENTS)}")
    task_id = await board.create_task(
        title=title, brief=brief, agent=agent, source=source,
        parent_id=parent_task_id, payload=payload, dedup_key=dedup_key,
    )
    if task_id is None:  # dedup collision (e.g. cron caught up twice)
        return None
    await _queues["tasks"].enqueue_async(run_task, task_id)
    return task_id


# --- workflows ---------------------------------------------------------------

@DBOS.workflow()
async def run_task(task_id: str) -> str:
    task = await _load_task(task_id)
    agent_name = task["agent"]
    spec, agent = AGENTS[agent_name]

    reason = await _preflight(agent_name, spec)
    if reason:
        await board.apply(task_id, "blocked", status="blocked", data={"reason": reason})
        return f"blocked: {reason}"

    await board.apply(task_id, "status_changed", status="running")
    run_id = await _start_run(task_id, spec)
    deps = runner.HQDeps(
        agent=agent_name, task_id=task_id, run_id=run_id,
        vault_write_scopes=spec.vault_write_scopes(),
    )
    prompt = task["title"] + ("\n\n" + task["brief"] if task["brief"] else "")

    try:
        outcome = await runner.execute(agent, spec, prompt=prompt, deps=deps)
    except Exception as exc:  # noqa: BLE001 — a run must never wedge the board
        await _finish_run(run_id, "failed", 0, 0, 0.0, error=str(exc)[:2000])
        await board.apply(task_id, "run_failed", status="failed", data={"error": str(exc)[:500]})
        await emit("run.failed", run_id=run_id, task_id=task_id, agent=agent_name,
                   payload={"error": str(exc)[:500]})
        return "failed"

    await _finish_run(run_id, outcome.outcome, outcome.input_tokens,
                      outcome.output_tokens, outcome.cost_usd, error=outcome.error)
    status = {"done": "done", "blocked": "blocked"}.get(outcome.outcome, "failed")
    await board.apply(task_id, f"run_{outcome.outcome}", status=status,
                      data={"output": outcome.output[:500]})
    await emit("run.finished", run_id=run_id, task_id=task_id, agent=agent_name,
               payload={"outcome": outcome.outcome, "cost_usd": outcome.cost_usd})
    if task["source"] == "cron" and await safety.notification_budget_left():
        await board.queue_outbound(
            {"kind": "text", "text": f"[{agent_name}] {task['title']}\n{outcome.output[:800]}"},
            idempotency_key=f"task-done:{task_id}",
        )
        await emit("notify", task_id=task_id, agent=agent_name, payload={"text": task["title"]})
    return outcome.outcome


@DBOS.workflow()
async def chat_turn(session_id: str, text: str) -> str:
    session = await db.fetchone("SELECT * FROM hq.sessions WHERE id = %s", (session_id,))
    agent_name = session["agent"]
    spec, agent = AGENTS[agent_name]

    reason = await _preflight(agent_name, spec)
    if reason:
        await board.queue_outbound({"kind": "text", "text": f"Cannot run: {reason}"})
        return "blocked"

    run_id = await _start_run(None, spec)
    deps = runner.HQDeps(agent=agent_name, run_id=run_id,
                         vault_write_scopes=spec.vault_write_scopes())
    history = await _load_history(str(session["conversation_id"]))
    outcome = await runner.execute(agent, spec, prompt=text, deps=deps,
                                   message_history=history)
    await _finish_run(run_id, outcome.outcome, outcome.input_tokens,
                      outcome.output_tokens, outcome.cost_usd, error=outcome.error)
    if outcome.messages_json is not None:
        await store_history(str(session["conversation_id"]), agent_name, outcome.messages_json)
    await board.queue_outbound(
        {"kind": "text", "text": outcome.output[:4000]},
        idempotency_key=f"chat-reply:{run_id}",
    )
    return outcome.outcome


# --- cron / watchdog ---------------------------------------------------------

def set_process_timezone() -> None:
    """This DBOS version schedules in the process timezone, so we set it once
    from CRON_TZ. Call before any scheduled workflow is registered."""
    os.environ["TZ"] = settings().cron_tz
    time.tzset()


def _register_cron() -> None:
    for name, (spec, _agent) in AGENTS.items():
        for i, entry in enumerate(spec.cron):
            def make(agent_name: str, idx: int, prompt: str):
                async def fire(scheduled: datetime, actual: datetime) -> None:
                    await dispatch(
                        agent=agent_name, title=prompt, source="cron",
                        dedup_key=f"cron:{agent_name}:{idx}:{scheduled:%Y-%m-%d-%H%M}",
                    )
                fire.__name__ = f"cron_{agent_name}_{idx}"
                return fire
            DBOS.scheduled(entry.schedule)(make(name, i, entry.prompt))

    DBOS.scheduled("* * * * *")(_watchdog_tick)
    DBOS.scheduled("* * * * *")(_drain_outbox_tick)


async def _watchdog_tick(scheduled: datetime, actual: datetime) -> None:
    if safety.halted():
        row = await db.fetchone("SELECT value FROM hq.control WHERE key = 'halt_notified'")
        if not (row and row["value"]):
            await board.queue_outbound({"kind": "text", "text": "HALT file present — dispatch paused."},
                                       idempotency_key="halt-notice")
            await db.execute(
                "INSERT INTO hq.control (key, value) VALUES ('halt_notified', 'true'::jsonb)"
                " ON CONFLICT (key) DO UPDATE SET value = 'true'::jsonb"
            )
        return
    await db.execute("DELETE FROM hq.control WHERE key = 'halt_notified'")

    # dead-man ping (external check catches a dead process; this proves liveness)
    url = settings().healthchecks_ping_url
    if url:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.get(url)
        except httpx.HTTPError:
            pass

    # expire ancient pending tickets
    stale = await db.fetch(
        "SELECT id::text FROM hq.tickets WHERE status = 'pending'"
        " AND created_at < now() - interval '24 hours'"
    )
    for row in stale:
        await board.resolve_ticket(row["id"], "expired", via="watchdog")


async def _drain_outbox_tick(scheduled: datetime, actual: datetime) -> None:
    from hq.channels import telegram
    await telegram.drain_outbox()


async def reap() -> None:
    """Boot-time reconciliation. DBOS recovery resumes live workflows; anything
    still marked running with no fresh activity is stale — block it visibly."""
    stale = await db.fetch(
        "SELECT id::text FROM hq.tasks WHERE status = 'running'"
        " AND updated_at < now() - interval '2 hours'"
    )
    for row in stale:
        await board.apply(row["id"], "reaped", status="blocked",
                          data={"reason": "stale running task at boot"})


# --- helpers -----------------------------------------------------------------

async def _preflight(agent_name: str, spec: AgentSpec) -> str | None:
    if safety.halted():
        return "HALT file present"
    if await safety.agent_paused(agent_name):
        return f"agent {agent_name} is paused"
    return await safety.spend_cap_hit(agent_name, spec.caps.daily_usd)


async def _load_task(task_id: str) -> dict:
    row = await db.fetchone(
        "SELECT id::text, title, brief, agent, status, source FROM hq.tasks WHERE id = %s",
        (task_id,),
    )
    assert row is not None, f"task {task_id} missing"
    return row


@DBOS.step()
async def _start_run(task_id: str | None, spec: AgentSpec) -> str:
    row = await db.fetchone(
        "INSERT INTO hq.runs (task_id, wf_id, agent, model, job_hash)"
        " VALUES (%s, %s, %s, %s, %s) RETURNING id::text",
        (task_id, DBOS.workflow_id, spec.name, llm.registry().canonical(spec.model),
         spec.job_hash()),
    )
    await emit("run.started", run_id=row["id"], task_id=task_id, agent=spec.name)
    return row["id"]


@DBOS.step()
async def _finish_run(run_id: str, outcome: str, input_tokens: int,
                      output_tokens: int, cost_usd: float, error: str | None = None) -> None:
    await db.execute(
        "UPDATE hq.runs SET ended_at = now(), outcome = %s, input_tokens = %s,"
        " output_tokens = %s, cost_usd = %s, error = %s WHERE id = %s",
        (outcome, input_tokens, output_tokens, cost_usd, error, run_id),
    )


async def _load_history(conversation_id: str):
    row = await db.fetchone(
        "SELECT history FROM hq.messages WHERE conversation_id = %s ORDER BY id DESC LIMIT 1",
        (conversation_id,),
    )
    if row is None:
        return None
    return ModelMessagesTypeAdapter.validate_python(row["history"])


async def store_history(conversation_id: str, agent: str, messages_json: bytes) -> None:
    payload = json.loads(messages_json) if isinstance(messages_json, (bytes, str)) else messages_json
    await db.execute(
        "INSERT INTO hq.messages (conversation_id, agent, history) VALUES (%s, %s, %s)",
        (conversation_id, agent, db.jsonb(payload)),
    )
