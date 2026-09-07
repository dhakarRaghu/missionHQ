"""Postgres access + numbered SQL migrations. App tables live in schema ``hq``.

DBOS keeps its own ``dbos`` schema in the same database; we never touch it.
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from typing import Any, cast

from psycopg.rows import dict_row
from psycopg.types.json import Json
from psycopg_pool import AsyncConnectionPool

from hq.config import BACKEND_DIR, settings

MIGRATIONS_DIR = BACKEND_DIR / "migrations"


def load_migrations() -> list[tuple[int, str]]:
    """Numbered SQL files: migrations/NNN_name.sql, applied in order. One file
    per change means parallel work never edits the same list."""
    out = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        version = int(path.name.split("_", 1)[0])
        out.append((version, path.read_text()))
    versions = [v for v, _ in out]
    assert versions == list(range(1, len(versions) + 1)), f"migration gap: {versions}"
    return out

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


async def fetch(sql: str, params: tuple | dict[str, Any] = ()) -> list[dict[str, Any]]:
    async with pool().connection() as conn:
        cur = await conn.execute(sql, params)
        return cast(list[dict[str, Any]], await cur.fetchall())  # pool uses dict_row


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
        current = int(cast(dict[str, Any], row)["v"]) if row else 0
        for version, sql in load_migrations():
            if version > current:
                async with conn.transaction():
                    await conn.execute(sql)
                    await conn.execute(
                        "INSERT INTO public.hq_migrations (version) VALUES (%s)", (version,)
                    )
