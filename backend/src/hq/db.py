"""Postgres access + numbered SQL migrations. App tables live in schema ``hq``.

DBOS keeps its own ``dbos`` schema in the same database; we never touch it.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any

from psycopg.rows import dict_row
from psycopg.types.json import Json
from psycopg_pool import AsyncConnectionPool

from hq.config import settings

MIGRATIONS: list[str] = [
    # 001 — core schema
    """
    CREATE SCHEMA IF NOT EXISTS hq;

    CREATE TABLE hq.tasks (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      title text NOT NULL,
      brief text NOT NULL DEFAULT '',
      agent text NOT NULL,
      status text NOT NULL DEFAULT 'backlog'
        CHECK (status IN ('backlog','running','blocked','needs_approval','done','failed')),
      priority int NOT NULL DEFAULT 0,
      parent_id uuid REFERENCES hq.tasks(id),
      source text NOT NULL,
      payload jsonb NOT NULL DEFAULT '{}'::jsonb,
      dedup_key text UNIQUE,
      not_before timestamptz,
      created_at timestamptz NOT NULL DEFAULT now(),
      updated_at timestamptz NOT NULL DEFAULT now()
    );

    CREATE TABLE hq.task_events (
      id bigserial PRIMARY KEY,
      task_id uuid NOT NULL REFERENCES hq.tasks(id),
      seq int NOT NULL,
      ts timestamptz NOT NULL DEFAULT now(),
      actor text NOT NULL,
      event_type text NOT NULL,
      data jsonb NOT NULL DEFAULT '{}'::jsonb,
      UNIQUE (task_id, seq)
    );

    CREATE TABLE hq.tickets (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      task_id uuid REFERENCES hq.tasks(id),
      run_id uuid,
      wf_id text NOT NULL,
      tool_name text NOT NULL,
      tool_args jsonb NOT NULL DEFAULT '{}'::jsonb,
      tool_call_id text NOT NULL DEFAULT '',
      action_class text NOT NULL,
      status text NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending','approved','denied','expired')),
      created_at timestamptz NOT NULL DEFAULT now(),
      resolved_at timestamptz,
      resolved_via text
    );

    CREATE TABLE hq.runs (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      task_id uuid REFERENCES hq.tasks(id),
      wf_id text,
      agent text NOT NULL,
      model text NOT NULL DEFAULT '',
      job_hash text NOT NULL DEFAULT '',
      started_at timestamptz NOT NULL DEFAULT now(),
      ended_at timestamptz,
      outcome text,
      input_tokens int NOT NULL DEFAULT 0,
      output_tokens int NOT NULL DEFAULT 0,
      cost_usd numeric(12,6) NOT NULL DEFAULT 0,
      stall_count int NOT NULL DEFAULT 0,
      error text
    );

    CREATE TABLE hq.events (
      id bigserial PRIMARY KEY,
      ts timestamptz NOT NULL DEFAULT now(),
      run_id uuid,
      task_id uuid,
      agent text,
      kind text NOT NULL,
      payload jsonb NOT NULL DEFAULT '{}'::jsonb
    );
    CREATE INDEX ix_events_kind_ts ON hq.events (kind, ts);
    CREATE INDEX ix_events_run ON hq.events (run_id);

    CREATE TABLE hq.sessions (
      id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      channel text NOT NULL,
      channel_user_id text NOT NULL,
      thread_id text NOT NULL DEFAULT '',
      conversation_id uuid NOT NULL DEFAULT gen_random_uuid(),
      agent text NOT NULL DEFAULT 'sage',
      last_active timestamptz NOT NULL DEFAULT now(),
      UNIQUE (channel, channel_user_id, thread_id)
    );

    CREATE TABLE hq.messages (
      id bigserial PRIMARY KEY,
      conversation_id uuid NOT NULL,
      ts timestamptz NOT NULL DEFAULT now(),
      agent text NOT NULL DEFAULT '',
      history jsonb NOT NULL
    );
    CREATE INDEX ix_messages_conv ON hq.messages (conversation_id, id);

    CREATE TABLE hq.outbox (
      id bigserial PRIMARY KEY,
      created_at timestamptz NOT NULL DEFAULT now(),
      channel text NOT NULL DEFAULT 'telegram',
      chat_ref text NOT NULL DEFAULT '',
      intent jsonb NOT NULL,
      idempotency_key text UNIQUE,
      sent_at timestamptz,
      attempts int NOT NULL DEFAULT 0,
      last_error text
    );

    CREATE TABLE hq.control (
      key text PRIMARY KEY,
      value jsonb NOT NULL,
      updated_at timestamptz NOT NULL DEFAULT now()
    );
    """,
]

_pool: AsyncConnectionPool | None = None


async def open_pool() -> None:
    global _pool
    if _pool is None:
        _pool = AsyncConnectionPool(
            settings().database_url, min_size=1, max_size=5, open=False,
            kwargs={"row_factory": dict_row},
        )
        await _pool.open(wait=True)


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


def pool() -> AsyncConnectionPool:
    assert _pool is not None, "db.open_pool() not called"
    return _pool


@asynccontextmanager
async def tx():
    """One transaction; commits on success, rolls back on error."""
    async with pool().connection() as conn, conn.transaction():
        yield conn


async def fetch(sql: str, params: tuple = ()) -> list[dict[str, Any]]:
    async with pool().connection() as conn:
        cur = await conn.execute(sql, params)
        return await cur.fetchall()


async def fetchone(sql: str, params: tuple = ()) -> dict[str, Any] | None:
    rows = await fetch(sql, params)
    return rows[0] if rows else None


async def execute(sql: str, params: tuple = ()) -> None:
    async with pool().connection() as conn:
        await conn.execute(sql, params)


def jsonb(value: Any) -> Json:
    return Json(value, dumps=lambda v: json.dumps(v, default=str))


async def migrate() -> None:
    async with pool().connection() as conn:
        await conn.execute(
            "CREATE TABLE IF NOT EXISTS public.hq_migrations ("
            " version int PRIMARY KEY, applied_at timestamptz NOT NULL DEFAULT now())"
        )
        cur = await conn.execute("SELECT coalesce(max(version), 0) AS v FROM public.hq_migrations")
        row = await cur.fetchone()
        current = row["v"]
        for version, sql in enumerate(MIGRATIONS, start=1):
            if version > current:
                async with conn.transaction():
                    await conn.execute(sql)
                    await conn.execute(
                        "INSERT INTO public.hq_migrations (version) VALUES (%s)", (version,)
                    )
