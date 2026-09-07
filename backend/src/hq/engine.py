"""Workflows, queues, cron fan-out, reaper, watchdog.

``dispatch()`` is the ONE enqueue path: cron handlers, chat, the REST API and
agent delegation all go through it. Agents + cron workflows are registered in
the API lifespan BEFORE DBOS.launch(); queues + schedules after.
"""

from __future__ import annotations

import json
import re
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx
from dbos import (
    Queue,
    ScheduleInput,
    SetWorkflowID,
    SetWorkflowTimeout,
    WorkflowHandleAsync,
)
from dbos._croniter import croniter  # type: ignore[attr-defined]
from dbos._registrations import get_dbos_func_name
from pydantic_ai import Agent, DeferredToolRequests
from pydantic_ai.durable_exec.dbos import DBOSDurability
from pydantic_ai.messages import ModelMessagesTypeAdapter

from hq import board, db, digest, llm, memory, runner, safety
from hq.config import settings
from hq.dbos_app import DBOS
from hq.loader import AgentSpec, build_agent, scan

TASK_TIMEOUT_S = 20 * 60   # a cron/board run may not exceed 20 minutes
CHAT_TIMEOUT_S = 6 * 60    # a chat turn may not exceed 6 minutes (approval waits excluded: they block in recv)

AGENTS: dict[str, tuple[AgentSpec, Agent[runner.HQDeps, str | DeferredToolRequests]]] = {}
_queues: dict[str, Queue] = {}
_schedules: list[ScheduleInput] = []  # built pre-launch, applied post-launch

# --- artifact assertion + exit status ----------------------------------------
# An LLM judge cannot reliably tell a real success from a claimed one, so a run
# that was asked to write something must leave a side effect on record: one
# ``tool.called`` event with ok=true for one of these tools.
ARTIFACT_TOOLS = ("vault_write", "record_fact", "create_subtask", "announce")
ARTIFACT_SOURCES = {"cron", "web", "agent"}
NO_ARTIFACT_REASON = "run reported success but produced no artifact"
# A folder reference such as ``daily/`` or ``projects/content/``. The lookbehind
# keeps URL pieces (``example.com/``, ``https://``) from matching.
_FOLDER_RE = re.compile(r"(?<![\w.:/])[A-Za-z][\w-]*/")
# "append" counts as a write verb: scout's cron says "Append them ... in
# projects/content/ideas.md" and must leave a vault_write behind.
_WRITE_VERBS = ("write", "append")

EXIT_STATUSES = ("complete", "no_artifact", "stalled", "timeout", "tool_failure",
                 "blocked", "failed")
# Chars of the final answer kept on the task's run_* event (the console renders
# it as markdown). The Telegram notification and the digest keep their own caps.
TASK_OUTPUT_CHARS = 12000
# Board title for a cron task: the prompt up to its first sentence end, at
# most this many chars. The full prompt goes into the brief.
CRON_TITLE_CHARS = 70


# "do not write", "don't append", "never write", "without writing": a task that
# forbids a write must not be judged for failing to produce one.
_NEGATED_WRITE_RE = re.compile(
    r"\b(?:do\s+not|don'?t|never|without|no\s+need\s+to)\s+(?:\w+\s+){0,2}?(?:writ|append)",
    re.IGNORECASE,
)


def expects_artifact(text: str) -> bool:
    """Pure text rule: the task asks to *write* something into the vault.

    True when the text contains "write" (or "append") and one of: "vault",
    ".md", or a folder name like ``daily/``, ``quarantine/``, ``projects/``.

    A negated write verb ("do not write anything") makes it False. Without
    that check, a task that explicitly forbids writing was read as demanding
    one, and the agent was marked no_artifact for obeying the instruction.
    """
    low = text.lower()
    if not any(v in low for v in _WRITE_VERBS):
        return False
    if _NEGATED_WRITE_RE.search(low):
        return False
    return "vault" in low or ".md" in low or _FOLDER_RE.search(text) is not None


def cron_title(prompt: str) -> str:
    """Short board title for a cron prompt: the text up to the first sentence
    end ("." or ":"), cut at CRON_TITLE_CHARS with an ellipsis when shortened."""
    text = " ".join(prompt.split())
    cut = len(text)
    for mark in (".", ":"):
        idx = text.find(mark)
        if idx != -1:
            cut = min(cut, idx)
    head = text[:cut].rstrip()
    if len(head) > CRON_TITLE_CHARS:
        head = head[:CRON_TITLE_CHARS].rstrip()
    if not head:
        head = text[:CRON_TITLE_CHARS].rstrip()
    return head + ("…" if len(head) < len(text) else "")


def exit_status(outcome: str, error: str | None) -> str:
    """Structured exit status for the ``run.finished`` event, derived from the
    run outcome and error text only (no model involved)."""
    err = (error or "").lower()
    if outcome == "done":
        return "complete"
    if outcome == "no_artifact":
        return "no_artifact"
    if err.startswith("stalled:"):
        return "stalled"
    if "timed out" in err or "timeout" in err or "expired" in err:
        return "timeout"
    if "tool" in err:
        return "tool_failure"
    if outcome == "blocked":
        return "blocked"
    return "failed"


@DBOS.step()
async def _artifact_check_step(run_id: str) -> bool:
    """True when this run made at least one successful artifact tool call."""
    row = await db.fetchone(
        "SELECT 1 FROM hq.events WHERE kind = 'tool.called' AND run_id = %s"
        " AND payload->>'tool' = ANY(%s) AND payload->>'ok' = 'true' LIMIT 1",
        (run_id, list(ARTIFACT_TOOLS)),
    )
    return row is not None


def registered_agents() -> dict[str, tuple[AgentSpec, Agent[runner.HQDeps, str | DeferredToolRequests]]]:
    return AGENTS


def bootstrap_pre_launch() -> None:
    """Agents + cron workflows. MUST run BEFORE DBOS.launch()."""
    # One durable retry on model requests: the OpenAI client has max_retries=0
    # (DBOS owns retries), so a single gateway hiccup must not fail a whole run.
    durability = DBOSDurability(
        models=llm.registry().all_instances(),
        model_step_config={"retries_allowed": True, "max_attempts": 2, "interval_seconds": 2.0},
    )
    for name, spec in scan().items():
        AGENTS[name] = (spec, build_agent(spec, durability))
    _register_cron()


async def bootstrap_post_launch() -> None:
    """Queues + schedules. Both need a launched executor."""
    # tasks=2 so one run waiting on approval cannot block every other task;
    # vault writes stay serialized by memory._write_lock.
    _queues["tasks"] = await DBOS.register_queue_async("tasks", worker_concurrency=2)
    _queues["chat"] = await DBOS.register_queue_async("chat", worker_concurrency=2)
    await DBOS.apply_schedules_async(_schedules)
    wanted = {s["schedule_name"] for s in _schedules}
    for sched in await DBOS.list_schedules_async(schedule_name_prefix="cron_"):
        if sched["schedule_name"] not in wanted:  # agent or cron entry removed
            await DBOS.delete_schedule_async(sched["schedule_name"])


async def dispatch(
    *, agent: str, title: str, brief: str = "", source: str = "system",
    parent_task_id: str | None = None, dedup_key: str | None = None,
    payload: dict | None = None,
) -> str:
    """Create (or find, on dedup_key) a task and make sure it is enqueued."""
    if agent not in AGENTS:
        raise KeyError(f"unknown agent {agent!r}; loaded: {sorted(AGENTS)}")
    task_id, status, inserted = await board.create_task(
        title=title, brief=brief, agent=agent, source=source,
        parent_id=parent_task_id, payload=payload, dedup_key=dedup_key,
    )
    if inserted or status == "backlog":
        await _enqueue(task_id)
    return task_id


async def _enqueue(task_id: str) -> None:
    """Deterministic workflow id, so a replayed dispatch cannot start a second run."""
    if DBOS.step_id is not None:
        # DBOS forbids starting workflows from inside a step (e.g. the
        # create_subtask tool). The task stays in backlog and the owning
        # workflow picks it up via enqueue_agent_tasks() after its run.
        return
    # Durable wall-clock cap enforced by DBOS, outside the agent: a stalled or
    # hung run is cancelled instead of sitting in "running" all night.
    with SetWorkflowID(f"task-{task_id}"), SetWorkflowTimeout(TASK_TIMEOUT_S):
        await _queues["tasks"].enqueue_async(run_task, task_id)


async def enqueue_chat(session_id: str, text: str, client_id: str) -> WorkflowHandleAsync[str]:
    """The one enqueue path for chat turns (Telegram and web). The workflow id
    derives from the caller's client_id, so a retried send cannot start a
    second run; DBOS hands back the handle of the existing workflow instead."""
    with SetWorkflowID(f"chat-{client_id}"), SetWorkflowTimeout(CHAT_TIMEOUT_S):
        return await _queues["chat"].enqueue_async(chat_turn, session_id, text)


async def enqueue_agent_tasks(run_id: str) -> None:
    """Enqueue backlog tasks that tools created during ``run_id``."""
    rows = await db.fetch(
        "SELECT id::text FROM hq.tasks WHERE status = 'backlog' AND source = 'agent'"
        " AND payload->>'run_id' = %s ORDER BY created_at",
        (run_id,),
    )
    for row in rows:
        await _enqueue(row["id"])


# --- workflows ---------------------------------------------------------------

def friendly_error(exc: BaseException) -> str:
    """One plain sentence for the owner; the raw text stays in the run.exception event."""
    raw = str(exc)
    low = raw.lower()
    if "is a directory" in low:
        return "a tool was given a folder where a file path was expected"
    if "exceeded its maximum" in low and "retries" in low:
        # DBOS names the step it gave up on. A model request and a tool call
        # fail for different reasons, and saying "a tool" for a gateway
        # failure sends the reader looking in the wrong place.
        if "model.request" in low:
            return "the model gateway kept failing after several attempts"
        return "a tool kept failing after several attempts (network or a bad page)"
    if "connection error" in low or "connecterror" in low or "timed out" in low:
        return "the model gateway was unreachable for a moment"
    if "rate limit" in low or "429" in low:
        return "the model gateway rate-limited the request"
    if "usagelimit" in low or "token" in low and "limit" in low:
        return "the run hit its token or cost budget"
    return raw[:200]


def _partial_usage(exc: BaseException) -> tuple[int, int, float]:
    """Tokens and cost the run consumed before it crashed (runner attaches them)."""
    partial = getattr(exc, "partial_outcome", None)
    if partial is None:
        return 0, 0, 0.0
    return partial.input_tokens, partial.output_tokens, partial.cost_usd


@DBOS.workflow()
async def run_task(task_id: str) -> str:
    task = await _load_task(task_id)
    agent_name = task["agent"]
    spec, agent = AGENTS[agent_name]

    reason = await _preflight(agent_name, spec)
    if reason:
        await runner.apply_step(task_id, "blocked", status="blocked", data={"reason": reason})
        return f"blocked: {reason}"

    await runner.apply_step(task_id, "status_changed", status="running")
    run_id = await _start_run(task_id, spec)
    deps = runner.HQDeps(
        agent=agent_name, task_id=task_id, run_id=run_id,
        vault_write_scopes=spec.vault_write_scopes(),
    )
    task_text = task["title"] + ("\n\n" + task["brief"] if task["brief"] else "")
    prompt = _anchored_prompt(agent_name, spec, task["title"], task["brief"])

    try:
        if spec.runtime == "claude":
            # This runtime drives a browser the owner is signed into, outside
            # our loop, so the whole run is approved before it starts rather
            # than one tool call at a time.
            if not await runner.await_runtime_approval(spec, deps, task_text):
                await _finish_run(run_id, "blocked", 0, 0, 0.0,
                                  error="the owner did not approve this run")
                await runner.apply_step(task_id, "run_blocked", status="blocked",
                                        data={"reason": "runtime approval not granted"})
                return "blocked: not approved"
            outcome = await runner.execute_claude(spec, prompt=prompt, deps=deps)
            outcome = await _file_claude_output(spec, task_id, run_id, outcome)
        else:
            outcome = await runner.execute(agent, spec, prompt=prompt, deps=deps)
    except Exception as exc:  # noqa: BLE001 — a run must never wedge the board
        exc_text = friendly_error(exc)
        p_in, p_out, p_cost = _partial_usage(exc)
        await _finish_run(run_id, "failed", p_in, p_out, p_cost, error=exc_text)
        await runner.apply_step(task_id, "run_failed", status="failed",
                                data={"error": exc_text[:500], "raw_error": str(exc)[:500]})
        await runner.emit_step("run.failed", run_id=run_id, task_id=task_id, agent=agent_name,
                               payload={"error": exc_text[:500],
                                        "exit_status": exit_status("failed", exc_text)})
        return "failed"

    # Artifact assertion: "done" without a recorded side effect is not done.
    result: str = outcome.outcome
    error: str | None = outcome.error
    if (result == "done" and task["source"] in ARTIFACT_SOURCES
            and expects_artifact(task_text) and not await _artifact_check_step(run_id)):
        result, error = "no_artifact", NO_ARTIFACT_REASON

    await _finish_run(run_id, result, outcome.input_tokens,
                      outcome.output_tokens, outcome.cost_usd, error=error)
    status = {"done": "done", "blocked": "blocked", "no_artifact": "blocked"}.get(result, "failed")
    data: dict[str, Any] = {"output": outcome.output[:TASK_OUTPUT_CHARS]}
    if result == "no_artifact":
        data["reason"] = NO_ARTIFACT_REASON
    await runner.apply_step(task_id, f"run_{result}", status=status, data=data)
    if result == "no_artifact":
        await runner.emit_step("run.no_artifact", run_id=run_id, task_id=task_id,
                               agent=agent_name,
                               payload={"reason": NO_ARTIFACT_REASON,
                                        "expected_tools": list(ARTIFACT_TOOLS)})
    await runner.emit_step("run.finished", run_id=run_id, task_id=task_id, agent=agent_name,
                           payload={"outcome": result, "exit_status": exit_status(result, error),
                                    "cost_usd": outcome.cost_usd})
    await enqueue_agent_tasks(run_id)
    if task["source"] == "cron" and await safety.notification_budget_left():
        head = f"[{agent_name}] {task['title']}"
        if result == "no_artifact":
            head = f"⚠ [{agent_name}] no artifact: {task['title']}"
        await runner.queue_outbound_step(
            {"kind": "text", "text": f"{head}\n{outcome.output[:800]}"},
            idempotency_key=f"task-done:{task_id}",
        )
        await runner.emit_step("notify", task_id=task_id, agent=agent_name,
                               payload={"text": task["title"]})
        await runner.flush_outbox_step()
    return result


def _anchored_prompt(agent_name: str, spec: AgentSpec, title: str, brief: str) -> str:
    """Identity re-anchor: one line of who the agent is and what it is for,
    right before the task. The instructions already carry the full job; this
    short repeat right next to the task keeps a long cron run on purpose."""
    purpose = " ".join(spec.description.split()) or "Mission HQ agent"
    text = f"[{agent_name} — {purpose}]\nTask: {title}"
    if brief:
        text += "\n" + brief
    return text


@DBOS.workflow()
async def chat_turn(session_id: str, text: str) -> str:
    """One conversational turn. Returns the reply text (or a "blocked: ..." /
    "failed: ..." string). Telegram sessions also get the reply through the
    outbox; web sessions read it from the workflow result or the transcript."""
    session = await db.fetchone("SELECT * FROM hq.sessions WHERE id = %s", (session_id,))
    assert session is not None, f"session {session_id} missing"
    agent_name = session["agent"]
    spec, agent = AGENTS[agent_name]
    via_telegram = session["channel"] == "telegram"

    reason = await _preflight(agent_name, spec)
    if reason:
        if via_telegram:
            await _reply_outbound(f"Cannot run: {reason}",
                                  idempotency_key=f"chat-blocked:{session_id}:{DBOS.workflow_id}")
        return f"blocked: {reason}"

    run_id = await _start_run(None, spec)
    deps = runner.HQDeps(agent=agent_name, run_id=run_id,
                         vault_write_scopes=spec.vault_write_scopes())
    history = await _load_history(str(session["conversation_id"]))
    try:
        outcome = await runner.execute(agent, spec, prompt=text, deps=deps,
                                       message_history=history)
    except Exception as exc:  # noqa: BLE001 — the owner must hear back either way
        exc_text = friendly_error(exc)
        p_in, p_out, p_cost = _partial_usage(exc)
        await _finish_run(run_id, "failed", p_in, p_out, p_cost, error=exc_text)
        await runner.emit_step("run.failed", run_id=run_id, agent=agent_name,
                               payload={"error": exc_text, "raw_error": str(exc)[:500]})
        if via_telegram:
            await _reply_outbound(f"run failed: {exc_text}",
                                  idempotency_key=f"chat-fail:{run_id}")
        return f"failed: {exc_text}"

    await _finish_run(run_id, outcome.outcome, outcome.input_tokens,
                      outcome.output_tokens, outcome.cost_usd, error=outcome.error)
    if outcome.messages_json is not None:
        await store_history(str(session["conversation_id"]), agent_name, outcome.messages_json,
                            run_id=run_id)
    await runner.emit_step("run.finished", run_id=run_id, agent=agent_name,
                           payload={"outcome": outcome.outcome,
                                    "exit_status": exit_status(outcome.outcome, outcome.error),
                                    "cost_usd": outcome.cost_usd})
    await enqueue_agent_tasks(run_id)
    if via_telegram:
        await _reply_outbound(outcome.output[:4000], idempotency_key=f"chat-reply:{run_id}")
    if outcome.outcome == "done":
        return outcome.output
    return f"{outcome.outcome}: {outcome.output}"


async def _reply_outbound(text: str, *, idempotency_key: str) -> None:
    await runner.queue_outbound_step({"kind": "text", "text": text},
                                     idempotency_key=idempotency_key)
    await runner.flush_outbox_step()


# --- cron / watchdog ---------------------------------------------------------

def _register_cron() -> None:
    """Register every scheduled function as a NAMED workflow (closures would
    otherwise collide on __qualname__) and build the schedule list. Schedules
    are applied post-launch with CRON_TZ; DBOS evaluates cron in UTC otherwise."""
    tz = settings().cron_tz
    _schedules.clear()
    for name, (spec, _agent) in AGENTS.items():
        for i, entry in enumerate(spec.cron):
            wf_name = f"cron_{name}_{i}"
            fire = DBOS.workflow(name=wf_name)(_make_cron(name, i, entry.prompt))
            _schedules.append({
                "schedule_name": wf_name, "workflow_fn": fire,
                "schedule": entry.schedule, "cron_timezone": tz,
            })
    watchdog = DBOS.workflow(name="watchdog")(_watchdog_tick)
    outbox = DBOS.workflow(name="drain_outbox")(_drain_outbox_tick)
    daily_digest = DBOS.workflow(name="daily_digest")(_daily_digest_tick)
    reindex_vault = DBOS.workflow(name="reindex_vault")(_reindex_vault_tick)
    _schedules.append({"schedule_name": "watchdog", "workflow_fn": watchdog,
                       "schedule": "* * * * *", "cron_timezone": tz})
    _schedules.append({"schedule_name": "drain_outbox", "workflow_fn": outbox,
                       "schedule": "* * * * *", "cron_timezone": tz})
    # Evening digest: the outlet for everything the notification cap held back.
    # It is not a budgeted 'notify' itself.
    _schedules.append({"schedule_name": "daily_digest", "workflow_fn": daily_digest,
                       "schedule": "30 20 * * *", "cron_timezone": tz})
    # Nightly full reindex: index-on-write covers agent writes; this catches
    # notes the owner edits by hand (Obsidian) that the app never sees.
    _schedules.append({"schedule_name": "reindex_vault", "workflow_fn": reindex_vault,
                       "schedule": "0 3 * * *", "cron_timezone": tz})
    for sched in _schedules:
        get_dbos_func_name(sched["workflow_fn"])  # raises unless registered as a workflow


def _make_cron(agent_name: str, idx: int, prompt: str):
    async def fire(scheduled: datetime, context: Any) -> None:
        local = scheduled.astimezone(ZoneInfo(settings().cron_tz))
        await dispatch(
            agent=agent_name, title=cron_title(prompt), brief=prompt, source="cron",
            dedup_key=f"cron:{agent_name}:{idx}:{local:%Y-%m-%d-%H%M}",
        )
    fire.__name__ = fire.__qualname__ = f"cron_{agent_name}_{idx}"
    return fire


async def _watchdog_tick(scheduled: datetime, context: Any) -> None:
    if safety.halted():
        row = await db.fetchone("SELECT value FROM hq.control WHERE key = 'halt_notified'")
        if not (row and row["value"]):
            await runner.queue_outbound_step(
                {"kind": "text", "text": "HALT file present — dispatch paused."},
                idempotency_key=f"halt-notice:{scheduled:%Y-%m-%d-%H%M}",
            )
            await db.execute(
                "INSERT INTO hq.control (key, value) VALUES ('halt_notified', 'true'::jsonb)"
                " ON CONFLICT (key) DO UPDATE SET value = 'true'::jsonb"
            )
            await runner.flush_outbox_step()
        return
    await db.execute("DELETE FROM hq.control WHERE key = 'halt_notified'")
    await _catch_up_missed(scheduled)
    await _deadman_check(scheduled)
    await _cap_overrunning_tasks()

    # dead-man ping (external check catches a dead process; this proves liveness)
    url = settings().healthchecks_ping_url
    if url:
        try:
            async with httpx.AsyncClient(timeout=5) as client:
                await client.get(url)
        except httpx.HTTPError:
            pass

    # expire ancient pending tickets and wake the workflows waiting on them
    stale = await db.fetch(
        "SELECT id::text FROM hq.tickets WHERE status = 'pending'"
        " AND created_at < now() - interval '24 hours'"
    )
    for row in stale:
        wf_id = await runner.expire_ticket_step(row["id"], "watchdog")
        if wf_id:
            await DBOS.send_async(wf_id, f"{row['id']}:expired", topic=runner.APPROVAL_TOPIC)


async def _cap_overrunning_tasks() -> None:
    """Block any task that has been running far longer than the task timeout.

    SetWorkflowTimeout cannot help when the host suspends the process: while a
    laptop sleeps mid-run, no timer advances, so a run started at 08:22 was
    still "running" hours later. This is the backstop that closes the task on
    the next tick after the machine wakes, so the board never shows work that
    is not happening. It marks the task, not the workflow: DBOS owns the
    workflow's own lifecycle.
    """
    stale = await db.fetch(
        "SELECT id::text FROM hq.tasks WHERE status = 'running'"
        " AND updated_at < now() - make_interval(secs => %s)",
        (TASK_TIMEOUT_S * 2,),
    )
    for row in stale:
        await board.apply(
            row["id"],
            "timed_out",
            status="blocked",
            data={
                "reason": (
                    "no progress for over "
                    f"{TASK_TIMEOUT_S * 2 // 60} minutes; the host was most "
                    "likely asleep or the process was suspended mid-run"
                )
            },
        )


async def _drain_outbox_tick(scheduled: datetime, context: Any) -> None:
    from hq.channels import telegram
    await telegram.drain_outbox()


async def _daily_digest_tick(scheduled: datetime, context: Any) -> None:
    await digest.send_digest(now=scheduled)


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
    # A crash between create_task and enqueue leaves a task in backlog forever.
    # Re-enqueue is safe: the workflow id is derived from the task id.
    for row in await db.fetch("SELECT id::text FROM hq.tasks WHERE status = 'backlog'"):
        await _enqueue(row["id"])


_URL_RE = re.compile(r"https?://[^\s<>\)\]\"']+")


async def _file_claude_output(
    spec: AgentSpec, task_id: str, run_id: str, outcome: runner.RunOutcome,
) -> runner.RunOutcome:
    """Write what the external agent reported into quarantine, as web-derived.

    The CLI process cannot write anywhere; Mission HQ does it here. It runs the
    same gates ``vault_write`` runs, in the same order, rather than calling
    ``memory.write`` directly: a quarantine note must cite its sources, and the
    frontmatter is stamped by code so the note carries the same author and
    provenance as anything an in-process agent writes. Routing around those
    checks would make this the one note in the vault that nobody vouched for.
    """
    if outcome.outcome != "done" or not outcome.output.strip():
        return outcome
    text = outcome.output.strip()
    today = datetime.now(ZoneInfo(settings().cron_tz)).date()
    rel = f"quarantine/{today:%Y-%m-%d}-{spec.name}-{task_id[:8]}.md"

    # The pages it read are the sources. The gate requires them, and an answer
    # with no URL in it is an answer we cannot attribute, so it is not filed.
    urls = list(dict.fromkeys(_URL_RE.findall(text)))[:20]
    if not urls:
        await runner.emit_step(
            "run.no_artifact", run_id=run_id, task_id=task_id, agent=spec.name,
            payload={"reason": "the reply named no source URL, so it was not filed"},
        )
        return outcome

    front = "\n".join(f"  - {u}" for u in urls)
    content = (
        f"---\nsource_urls:\n{front}\nconfidence: medium\n---\n"
        f"# {spec.name}: browser session {today:%Y-%m-%d}\n\n{text}\n"
    )
    try:
        meta, _body = memory.parse_frontmatter(content)
        problem = memory.quarantine_problem(rel, meta)
        if problem:
            raise ValueError(problem)
        content = memory.stamp_frontmatter(
            content, author=spec.name, provenance="web",
        )
        problem = memory.write_problem(rel, content, actor=spec.name, existing=None)
        if problem:
            raise ValueError(problem)
        await memory.write(rel, content, actor=spec.name)
    except Exception as exc:  # noqa: BLE001 — the reading still happened
        await runner.emit_step(
            "run.no_artifact", run_id=run_id, task_id=task_id, agent=spec.name,
            payload={"reason": f"could not file the result: {exc}"[:200]},
        )
        return outcome
    await runner.emit_step(
        "tool.called", run_id=run_id, task_id=task_id, agent=spec.name,
        payload={"tool": "vault_write", "ok": True, "args": {"path": rel},
                 "duration_ms": 0},
    )
    return replace(outcome, output=f"{text}\n\nFiled to {rel}")


# --- helpers -----------------------------------------------------------------

async def _preflight(agent_name: str, spec: AgentSpec) -> str | None:
    if safety.halted():
        return "HALT file present"
    if spec.status == "paused":
        return f"agent {agent_name} is paused in its manifest"
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
         spec.job_hash),
    )
    assert row is not None
    await runner.emit_step("run.started", run_id=row["id"], task_id=task_id, agent=spec.name)
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


@DBOS.step()
async def store_history(conversation_id: str, agent: str, messages_json: bytes,
                        run_id: str | None = None) -> None:
    payload = json.loads(messages_json) if isinstance(messages_json, (bytes, str)) else messages_json
    await db.execute(
        "INSERT INTO hq.messages (conversation_id, agent, history, run_id) VALUES (%s, %s, %s, %s)",
        (conversation_id, agent, db.jsonb(payload), run_id),
    )


async def _reindex_vault_tick(scheduled: datetime, context: Any) -> None:
    n = await memory.reindex_all()
    await runner.emit_step("vault.reindexed", payload={"chunks": n})


CATCH_UP_WINDOW = timedelta(hours=12)


async def _catch_up_missed(now_utc: datetime) -> None:
    """Fire schedules the machine slept through.

    DBOS backfills a schedule only if it has fired before; a laptop asleep at
    the exact minute of a daily schedule loses that day. Every tick, compute
    each schedule's most recent slot and run it if it has not run. Agent crons
    dedup on the slot key, the digest dedups on the date, reindex on a control
    key — so this is idempotent and cheap.
    """
    tz = ZoneInfo(settings().cron_tz)
    now = now_utc.astimezone(tz)
    for agent_name, (spec, _agent) in AGENTS.items():
        if await safety.agent_paused(agent_name):
            continue
        for idx, entry in enumerate(spec.cron):
            slot = croniter(entry.schedule, now).get_prev(datetime)
            if now - slot > CATCH_UP_WINDOW:
                continue
            key = f"cron:{agent_name}:{idx}:{slot:%Y-%m-%d-%H%M}"
            if await db.fetchone("SELECT 1 FROM hq.tasks WHERE dedup_key = %s", (key,)):
                continue
            await dispatch(agent=agent_name, title=cron_title(entry.prompt),
                           brief=entry.prompt, source="cron", dedup_key=key)
            await runner.emit_step("cron.caught_up", agent=agent_name, payload={"slot": key})

    # digest: 20:30 local, at most once per date (send_digest dedups by date)
    if now.hour * 60 + now.minute >= 20 * 60 + 30:
        row = await db.fetchone(
            "SELECT 1 FROM hq.outbox WHERE idempotency_key = %s", (f"digest:{now:%Y-%m-%d}",))
        if row is None:
            await digest.send_digest(now=now_utc)

    # reindex: 03:00 local, once per date
    if now.hour >= 3:
        row = await db.fetchone("SELECT value FROM hq.control WHERE key = 'reindex:last_date'")
        if not row or row["value"] != f"{now:%Y-%m-%d}":
            n = await memory.reindex_all()
            await db.execute(
                "INSERT INTO hq.control (key, value) VALUES ('reindex:last_date', %s)"
                " ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = now()",
                (db.jsonb(f"{now:%Y-%m-%d}"),),
            )
            await runner.emit_step("vault.reindexed", payload={"chunks": n, "via": "catch-up"})


# --- dead-man per cron entry -------------------------------------------------
# The catch-up above re-fires slots the machine slept through; this is the
# other half: say so out loud when a slot came and went with no successful
# run, so a scheduler that fails silently cannot stay silent.

DEADMAN_INTERVAL = timedelta(hours=1)      # how often the check runs
DEADMAN_GRACE = timedelta(minutes=90)      # slot age before it counts as missed
DEADMAN_LAST_KEY = "deadman:last_check"
# A run that completed and was caught by the artifact assertion is already on
# the board as blocked; it is not a *silent* miss, so it counts as completed here.
DEADMAN_COMPLETED = ("done", "no_artifact")


async def _deadman_check(now_utc: datetime) -> None:
    """Once per hour: for every agent cron entry, the latest slot must have a
    task (by dedup_key) with a completed run. Older than DEADMAN_GRACE without
    one -> ``cron.missed`` event once per slot + one owner notification."""
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=UTC)
    if not await _deadman_due(now_utc):
        return
    tz = ZoneInfo(settings().cron_tz)
    now = now_utc.astimezone(tz)
    queued = False
    for agent_name, (spec, _agent) in AGENTS.items():
        if await safety.agent_paused(agent_name):
            continue
        for idx, entry in enumerate(spec.cron):
            slot = croniter(entry.schedule, now).get_prev(datetime)
            if now - slot < DEADMAN_GRACE:
                continue
            # A slot from before this agent's manifest existed was never owed.
            born = datetime.fromtimestamp((spec.dir / "job.md").stat().st_mtime, tz=now.tzinfo)
            if slot < born:
                continue
            key = f"cron:{agent_name}:{idx}:{slot:%Y-%m-%d-%H%M}"
            if await _deadman_seen(key):
                continue
            state = await _slot_state(key)
            if state["completed"]:
                continue
            await _deadman_mark(key)
            detail = f"task is {state['status']}" if state["status"] else "no task was created"
            text = (f"⚠ {agent_name} did not complete its {entry.schedule} run"
                    f" for {slot:%Y-%m-%d %H:%M} ({detail})")
            await runner.emit_step("cron.missed", agent=agent_name, payload={
                "agent": agent_name, "slot": key, "schedule": entry.schedule,
                "slot_at": slot.isoformat(), "task_status": state["status"],
                "last_outcome": state["outcome"],
            })
            if await safety.notification_budget_left():
                await runner.queue_outbound_step({"kind": "text", "text": text},
                                                 idempotency_key=f"cron-missed:{key}")
                await runner.emit_step("notify", agent=agent_name, payload={"text": text[:200]})
                queued = True
            else:
                await runner.emit_step("notify_digested", agent=agent_name,
                                       payload={"text": text[:200]})
    if queued:
        await runner.flush_outbox_step()


async def _deadman_due(now_utc: datetime) -> bool:
    """Hourly guard on hq.control; also records this check as the latest."""
    row = await db.fetchone("SELECT value FROM hq.control WHERE key = %s", (DEADMAN_LAST_KEY,))
    if row and isinstance(row["value"], str):
        try:
            last = datetime.fromisoformat(row["value"])
        except ValueError:
            last = None
        if last is not None and now_utc - last < DEADMAN_INTERVAL:
            return False
    await db.execute(
        "INSERT INTO hq.control (key, value, updated_at) VALUES (%s, %s, now())"
        " ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = now()",
        (DEADMAN_LAST_KEY, db.jsonb(now_utc.isoformat())),
    )
    return True


async def _deadman_seen(slot_key: str) -> bool:
    row = await db.fetchone("SELECT 1 FROM hq.control WHERE key = %s", (f"deadman:{slot_key}",))
    return row is not None


async def _deadman_mark(slot_key: str) -> None:
    await db.execute(
        "INSERT INTO hq.control (key, value) VALUES (%s, 'true'::jsonb)"
        " ON CONFLICT (key) DO NOTHING",
        (f"deadman:{slot_key}",),
    )


async def _slot_state(slot_key: str) -> dict[str, Any]:
    """{completed, status, outcome} for the task behind one cron slot."""
    row = await db.fetchone(
        """
        SELECT t.status,
               (SELECT r.outcome FROM hq.runs r WHERE r.task_id = t.id
                ORDER BY r.started_at DESC LIMIT 1) AS outcome,
               EXISTS (SELECT 1 FROM hq.runs r WHERE r.task_id = t.id
                       AND r.outcome = ANY(%s)) AS completed
        FROM hq.tasks t WHERE t.dedup_key = %s
        """,
        (list(DEADMAN_COMPLETED), slot_key),
    )
    if row is None:
        return {"completed": False, "status": None, "outcome": None}
    return {"completed": bool(row["completed"]), "status": row["status"],
            "outcome": row["outcome"]}
