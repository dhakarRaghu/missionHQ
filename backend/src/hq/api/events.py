"""App-wide SSE stream: typed envelopes {seq, ts, type, payload}. Clients pass
?since=<seq> (or Last-Event-ID) to resume; the in-process replay ring plus a
DB backfill close the gap."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import StreamingResponse

from hq import db, obs
from hq.api.deps import require_auth

router = APIRouter(dependencies=[Depends(require_auth)])


async def _backfill(since: int) -> list[dict]:
    rows = await db.fetch(
        "SELECT id, ts, kind, task_id::text, run_id::text, agent, payload"
        " FROM hq.events WHERE id > %s ORDER BY id LIMIT 200", (since,))
    return [
        {
            "seq": r["id"], "ts": r["ts"].isoformat(), "type": r["kind"],
            "task_id": r["task_id"], "run_id": r["run_id"], "agent": r["agent"],
            "payload": r["payload"],
        }
        for r in rows
    ]


@router.get("/events", operation_id="streamEvents")
async def stream_events(
    request: Request,
    since: int | None = None,
    last_event_id: str | None = Header(default=None),
):
    start_seq = since if since is not None else (
        int(last_event_id) if last_event_id and last_event_id.isdigit() else None
    )

    async def gen():
        queue, missed = obs.subscribe(start_seq)
        try:
            if start_seq is not None:
                sent = set()
                for env in await _backfill(start_seq):
                    sent.add(env["seq"])
                    yield _frame(env)
                for env in missed:
                    if env["seq"] not in sent:
                        yield _frame(env)
            # First bytes right away: EventSource only reports "open" once the
            # response body starts, and proxies (the Next dev rewrite included)
            # hold small bodies until ~2 KB has accumulated. Comment lines are
            # ignored by clients, so the padding is invisible.
            yield ": connected" + " " * 2048 + "\n\n"
            while True:
                if await request.is_disconnected():
                    return
                try:
                    env = await asyncio.wait_for(queue.get(), timeout=15)
                    yield _frame(env)
                except TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            obs.unsubscribe(queue)

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _frame(env: dict) -> str:
    return f"id: {env['seq']}\nevent: {env['type']}\ndata: {json.dumps(env, default=str)}\n\n"
