"""Web chat endpoints. A web session is an hq.sessions row with channel='web';
each turn is the same durable ``chat_turn`` workflow Telegram uses, enqueued
through ``engine.enqueue_chat``. No token streaming: the handler waits for the
workflow result up to ``REPLY_WAIT_S`` and otherwise reports "pending"; the
client then learns completion from the SSE stream and refetches the transcript."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from dbos._error import DBOSConflictingWorkflowError
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from hq import db, engagement
from hq.api.deps import require_auth

router = APIRouter(prefix="/chat", dependencies=[Depends(require_auth)])

WEB_CHANNEL = "web"
WEB_USER = "owner"
# Next's rewrite proxy closes upstream requests after 30 seconds by default.
# Return "pending" first; the durable workflow keeps running and its SSE event
# refreshes the transcript when the reply lands.
REPLY_WAIT_S = 20
# hq.messages rows written before migration 007 carry no run_id. An assistant
# turn is matched to the chat run of the same agent whose start..end window,
# widened by this much on both sides, contains the turn's timestamp.
RUN_MATCH_SLACK = timedelta(seconds=90)


class CreateSessionBody(BaseModel):
    agent: str


class SetAgentBody(BaseModel):
    agent: str


class SendMessageBody(BaseModel):
    text: str
    client_id: str


def _check_agent(agent: str) -> None:
    from hq import engine

    if agent not in engine.registered_agents():
        raise HTTPException(404, f"unknown agent {agent}")


async def _web_session(session_id: str) -> dict[str, Any]:
    row = await db.fetchone(
        "SELECT id::text, conversation_id::text, agent, last_active FROM hq.sessions"
        " WHERE id = %s AND channel = %s",
        (session_id, WEB_CHANNEL),
    )
    if row is None:
        raise HTTPException(404, "unknown chat session")
    return row


@router.post("/sessions", operation_id="createChatSession", status_code=201)
async def create_session(body: CreateSessionBody) -> dict:
    _check_agent(body.agent)
    # Same upsert shape as telegram._session_for; the fresh thread_id makes
    # the conflict branch unreachable in practice but keeps one convention.
    row = await db.fetchone(
        """
        INSERT INTO hq.sessions (channel, channel_user_id, thread_id, agent)
        VALUES (%s, %s, %s, %s)
        ON CONFLICT (channel, channel_user_id, thread_id)
        DO UPDATE SET last_active = now()
        RETURNING id::text, agent, (xmax = 0) AS created
        """,
        (WEB_CHANNEL, WEB_USER, str(uuid.uuid4()), body.agent),
    )
    assert row is not None
    return {"session_id": row["id"], "agent": row["agent"], "created": bool(row["created"])}


@router.get("/sessions", operation_id="listChatSessions")
async def list_sessions(limit: int = 100) -> list[dict]:
    rows = await db.fetch(
        """
        SELECT s.id::text, s.agent, s.last_active, m.history
        FROM hq.sessions s
        LEFT JOIN LATERAL (
          SELECT history FROM hq.messages
          WHERE conversation_id = s.conversation_id ORDER BY id DESC LIMIT 1
        ) m ON true
        WHERE s.channel = %s
        ORDER BY s.last_active DESC LIMIT %s
        """,
        (WEB_CHANNEL, limit),
    )
    out = []
    for row in rows:
        transcript = _transcript(row["history"])
        preview = next((m["text"] for m in transcript if m["role"] == "user"), None)
        out.append({
            "id": row["id"], "agent": row["agent"], "last_active": row["last_active"],
            "preview": preview[:120] if preview else None,
        })
    return out


@router.delete("/sessions/{session_id}", operation_id="deleteChatSession")
async def delete_session(session_id: str) -> dict:
    """Remove one web chat and its history.

    A chat is a scratchpad, so the owner must be able to clear the ones that
    were experiments. Runs are NOT touched: they are the cost and audit record
    and stay readable under /runs even once their chat is gone.
    """
    session = await _web_session(session_id)
    await db.execute(
        "DELETE FROM hq.messages WHERE conversation_id = %s",
        (session["conversation_id"],),
    )
    await db.execute("DELETE FROM hq.sessions WHERE id = %s", (session_id,))
    return {"session_id": session_id, "deleted": True}


@router.post("/sessions/{session_id}/agent", operation_id="setChatSessionAgent")
async def set_session_agent(session_id: str, body: SetAgentBody) -> dict:
    _check_agent(body.agent)
    await _web_session(session_id)
    await db.execute(
        "UPDATE hq.sessions SET agent = %s, last_active = now() WHERE id = %s",
        (body.agent, session_id),
    )
    return {"session_id": session_id, "agent": body.agent}


@router.get("/sessions/{session_id}/messages", operation_id="listChatMessages")
async def list_messages(session_id: str) -> list[dict]:
    session = await _web_session(session_id)
    row = await db.fetchone(
        "SELECT history FROM hq.messages WHERE conversation_id = %s ORDER BY id DESC LIMIT 1",
        (session["conversation_id"],),
    )
    turns = _transcript(row["history"] if row else None)
    messages = await _attach_runs(turns, session["agent"])
    messages.extend(await _chat_deliveries(session_id))
    # History timestamps and PostgreSQL timestamps may use different timezone
    # offsets, so compare parsed instants rather than their ISO strings.
    floor = datetime.min.replace(tzinfo=UTC)
    messages.sort(key=lambda message: _parse_ts(message.get("ts")) or floor)
    return messages


@router.get("/sessions/{session_id}/tickets", operation_id="listChatTickets")
async def list_chat_tickets(session_id: str) -> list[dict]:
    """Approvals blocking work this chat started.

    An approval reaches the owner in the Inbox and on Telegram, but the run
    that raised it was started here, so answering it here is the shortest
    path. Two ways a ticket belongs to this chat: its run is this session's
    chat run, or its task was delegated from this session.
    """
    session = await _web_session(session_id)
    # Runs have no session column: a chat run is linked through the message
    # row it produced, and a delegated task through origin_session_id.
    rows = await db.fetch(
        """
        SELECT tk.id::text, tk.tool_name, tk.tool_args, tk.action_class,
               tk.created_at, r.agent
        FROM hq.tickets tk
        LEFT JOIN hq.runs r ON r.id = tk.run_id
        LEFT JOIN hq.tasks t ON t.id = tk.task_id
        WHERE tk.status = 'pending'
          AND (
            t.origin_session_id = %(sid)s
            OR tk.run_id IN (
              SELECT run_id FROM hq.messages
              WHERE conversation_id = %(conv)s AND run_id IS NOT NULL
            )
          )
        ORDER BY tk.created_at
        """,
        {"sid": session_id, "conv": session["conversation_id"]},
    )
    return [
        {
            "id": row["id"],
            "tool_name": row["tool_name"],
            "tool_args": row["tool_args"],
            "action_class": row["action_class"],
            "agent": row["agent"],
            "created_at": row["created_at"],
        }
        for row in rows
    ]


@router.post("/sessions/{session_id}/messages", operation_id="sendChatMessage")
async def send_message(session_id: str, body: SendMessageBody) -> dict:
    from hq import engine

    text = body.text.strip()
    if not text:
        raise HTTPException(422, "text must not be empty")
    if not body.client_id:
        raise HTTPException(422, "client_id is required")
    session = await _web_session(session_id)
    await db.execute("UPDATE hq.sessions SET last_active = now() WHERE id = %s", (session_id,))
    sent_at = datetime.now(UTC)

    try:
        handle = await engine.enqueue_chat(session_id, text, client_id=body.client_id)
    except DBOSConflictingWorkflowError as exc:
        raise HTTPException(409, "client_id already used for a different message") from exc
    await engagement.record_owner_action("web", "chat")
    try:
        reply = await asyncio.wait_for(handle.get_result(), timeout=REPLY_WAIT_S)
    except TimeoutError:
        # Still running (typically waiting on an approval ticket). The workflow
        # keeps going; the transcript picks up the reply when it lands.
        return {"status": "pending"}
    except Exception as exc:
        raise HTTPException(502, f"chat run failed: {str(exc)[:300]}") from exc
    run = await _latest_chat_run(session["agent"], since=sent_at - RUN_MATCH_SLACK)
    # A turn that ended in "failed: …" / "blocked: …" is not a normal reply.
    status = "failed" if str(reply).startswith(("failed:", "blocked:")) else "done"
    return {"status": status, "reply": reply, **await _run_fields(run)}


# --- run linkage -------------------------------------------------------------

async def _latest_chat_run(agent: str, *, since: datetime) -> dict[str, Any] | None:
    """The newest task-less run of ``agent`` started at or after ``since``."""
    return await db.fetchone(
        "SELECT id::text, cost_usd, started_at, ended_at FROM hq.runs"
        " WHERE agent = %s AND task_id IS NULL AND started_at >= %s"
        " ORDER BY started_at DESC LIMIT 1",
        (agent, since),
    )


async def _tools_by_run(run_ids: list[str]) -> dict[str, list[str]]:
    """Tool names of the tool.called events of each run, in call order."""
    if not run_ids:
        return {}
    rows = await db.fetch(
        "SELECT run_id::text AS run_id, payload->>'tool' AS tool FROM hq.events"
        " WHERE kind = 'tool.called' AND run_id = ANY(%s::uuid[]) ORDER BY id",
        (run_ids,),
    )
    out: dict[str, list[str]] = {rid: [] for rid in run_ids}
    for row in rows:
        if row["tool"]:
            out.setdefault(row["run_id"], []).append(row["tool"])
    return out


async def _run_fields(run: dict[str, Any] | None) -> dict[str, Any]:
    """``{run_id, cost_usd, tools}`` for one run, all None when no run matched."""
    if run is None:
        return {"run_id": None, "cost_usd": None, "tools": None}
    tools = await _tools_by_run([run["id"]])
    return {"run_id": run["id"], "cost_usd": float(run["cost_usd"]),
            "tools": tools.get(run["id"], [])}


async def _chat_deliveries(session_id: str) -> list[dict[str, Any]]:
    """System-delivered task results shown in chat but excluded from model history."""
    rows = await db.fetch(
        """
        SELECT d.ts, d.text, d.run_id::text, r.cost_usd, r.agent
        FROM hq.chat_deliveries d
        LEFT JOIN hq.runs r ON r.id = d.run_id
        WHERE d.session_id = %s
        ORDER BY d.ts, d.id
        """,
        (session_id,),
    )
    tools = await _tools_by_run([row["run_id"] for row in rows if row["run_id"]])
    return [
        {
            "role": "assistant",
            # Which agent actually produced this. A delegated result is not
            # from the agent the owner is talking to, and saying otherwise
            # hides the whole point of handing work over.
            "agent": row["agent"],
            "delivered": True,
            "text": row["text"],
            "ts": row["ts"].isoformat(),
            "run_id": row["run_id"],
            "cost_usd": float(row["cost_usd"]) if row["cost_usd"] is not None else None,
            "tools": tools.get(row["run_id"], []) if row["run_id"] else None,
        }
        for row in rows
    ]


def _parse_ts(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        ts = datetime.fromisoformat(value)
    except ValueError:
        return None
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


async def _attach_runs(turns: list[dict], agent: str) -> list[dict]:
    """Add ``run_id``, ``cost_usd`` and ``tools`` to every turn. Assistant turns
    get the chat run of ``agent`` whose window (started_at - slack .. ended_at
    + slack) holds the turn's timestamp; the closest start wins when several
    do. User turns, and assistant turns without a match, carry None."""
    stamps = [(i, _parse_ts(t.get("ts"))) for i, t in enumerate(turns)
              if t.get("role") == "assistant"]
    known = [ts for _, ts in stamps if ts is not None]
    runs: list[dict[str, Any]] = []
    if known:
        runs = await db.fetch(
            "SELECT id::text, cost_usd, started_at, ended_at FROM hq.runs"
            " WHERE agent = %s AND task_id IS NULL AND started_at <= %s"
            " AND coalesce(ended_at, now()) >= %s ORDER BY started_at",
            (agent, max(known) + RUN_MATCH_SLACK, min(known) - RUN_MATCH_SLACK),
        )
    matched: dict[int, dict[str, Any]] = {}
    for index, ts in stamps:
        if ts is None:
            continue
        best: dict[str, Any] | None = None
        for candidate in runs:
            start = candidate["started_at"] - RUN_MATCH_SLACK
            end = (candidate["ended_at"] or datetime.now(UTC)) + RUN_MATCH_SLACK
            if start <= ts <= end and (best is None or abs(candidate["started_at"] - ts)
                                       < abs(best["started_at"] - ts)):
                best = candidate
        if best is not None:
            matched[index] = best
    tools = await _tools_by_run(sorted({r["id"] for r in matched.values()}))
    out = []
    for index, turn in enumerate(turns):
        run: dict[str, Any] | None = matched.get(index)
        out.append({
            **turn,
            "run_id": run["id"] if run else None,
            "cost_usd": float(run["cost_usd"]) if run else None,
            "tools": tools.get(run["id"], []) if run else None,
        })
    return out


# --- transcript --------------------------------------------------------------

def _transcript(history: Any) -> list[dict]:
    """Flatten a pydantic-ai serialized message list into user/assistant turns.
    Tool, system and thinking parts are skipped."""
    if not history:
        return []
    out: list[dict] = []
    for message in history:
        if not isinstance(message, dict):
            continue
        kind = message.get("kind")
        for part in message.get("parts") or []:
            if not isinstance(part, dict):
                continue
            part_kind = part.get("part_kind")
            if kind == "request" and part_kind == "user-prompt":
                text = _prompt_text(part.get("content"))
                if text:
                    out.append({"role": "user", "text": text,
                                "ts": part.get("timestamp") or message.get("timestamp")})
            elif kind == "response" and part_kind == "text":
                content = part.get("content")
                if isinstance(content, str) and content:
                    out.append({"role": "assistant", "text": content,
                                "ts": message.get("timestamp")})
    return out


def _prompt_text(content: Any) -> str:
    """UserPromptPart.content is a string or a list of string / typed items."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        pieces = []
        for item in content:
            if isinstance(item, str):
                pieces.append(item)
            elif isinstance(item, dict) and item.get("kind") == "text-content":
                pieces.append(str(item.get("text", "")))
        return "\n".join(p for p in pieces if p)
    return ""
