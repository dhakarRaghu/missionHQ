"""Event log + live event bus + tracing.

``emit()`` is the single choke point: it writes hq.events AND pushes to every
SSE subscriber, so the stream and the log can never disagree. The row id is the
monotonic ``seq`` clients resume from.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

from hq import db

_subscribers: set[asyncio.Queue] = set()
_replay: list[dict] = []  # bounded ring of recent envelopes for reconnects
_REPLAY_MAX = 500


async def emit(
    kind: str,
    *,
    run_id: str | None = None,
    task_id: str | None = None,
    agent: str | None = None,
    payload: dict[str, Any] | None = None,
) -> int:
    row = await db.fetchone(
        """
        INSERT INTO hq.events (run_id, task_id, agent, kind, payload)
        VALUES (%s, %s, %s, %s, %s) RETURNING id, ts
        """,
        (run_id, task_id, agent, kind, db.jsonb(payload or {})),
    )
    assert row is not None
    envelope = {
        "seq": row["id"],
        "ts": row["ts"].isoformat(),
        "type": kind,
        "task_id": task_id,
        "run_id": run_id,
        "agent": agent,
        "payload": payload or {},
    }
    _replay.append(envelope)
    del _replay[:-_REPLAY_MAX]
    for q in list(_subscribers):
        with contextlib.suppress(asyncio.QueueFull):
            q.put_nowait(envelope)
    return row["id"]


def subscribe(since_seq: int | None = None) -> tuple[asyncio.Queue, list[dict]]:
    """Returns (queue, missed) — missed are replay-ring envelopes after since_seq."""
    q: asyncio.Queue = asyncio.Queue(maxsize=1000)
    _subscribers.add(q)
    missed = [e for e in _replay if since_seq is not None and e["seq"] > since_seq]
    return q, missed


def unsubscribe(q: asyncio.Queue) -> None:
    _subscribers.discard(q)


def configure_tracing() -> None:
    """Local-only tracing; exports via OTLP only if an endpoint is configured."""
    import os

    import logfire

    logfire.configure(
        send_to_logfire=False,
        console=False if os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT") else None,
    )
    logfire.instrument_pydantic_ai()
