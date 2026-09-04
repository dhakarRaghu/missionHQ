"""Facts with validity: ``hq.facts`` (migration 006).

A fact is one statement about a subject. Recording a new fact about a subject
SUPERSEDES the currently valid facts on that subject at write time: their
``invalid_at`` is set and ``superseded_by`` points at the new row. Nothing is
ever deleted, so stale knowledge is invalidated, not lost. Provenance is
decided by code from the run's audit trail (``hq.events`` ``tool.called``
rows): a run that read web content records ``web`` facts, which
``recall_facts`` leaves out unless asked for. Dates come from ``now()`` in
Postgres, never from the model.
"""

from __future__ import annotations

import re
from typing import Any

import psycopg
from pydantic_ai import ModelRetry, RunContext

from hq import db, llm, memory
from hq.obs import emit
from hq.safety import ActionClass, Trust
from hq.tools.policy_tools import _run_read_web as run_read_web
from hq.tools.registry import HQDeps, hq_tool

FACT_TOOLS = ["record_fact", "recall_facts", "retire_fact"]
FACT_RECORDED_KIND = "fact.recorded"
FACT_RETIRED_KIND = "fact.retired"
CONFIDENCES = ("low", "medium", "high")
MAX_FACT_CHARS = 600
MAX_SUBJECT_CHARS = 120
RECALL_LIMIT_MAX = 25

_WORD_RE = re.compile(r"[a-z0-9]+")
_STOP = frozenset({"the", "a", "an", "of", "and", "or", "for", "to", "in", "on", "is"})


def subject_ish(a: str, b: str) -> bool:
    """Two normalized subjects are about the same thing when one contains the
    other or they share a content word of 3+ chars. Used to keep the
    embedding-distance supersession from crossing subjects."""
    if a == b or a in b or b in a:
        return True
    wa = {w for w in _WORD_RE.findall(a) if len(w) >= 3 and w not in _STOP}
    wb = {w for w in _WORD_RE.findall(b) if len(w) >= 3 and w not in _STOP}
    return bool(wa & wb)


async def _embed_fact(subject: str, fact: str) -> str | None:
    """pgvector literal for ``subject: fact``, or None when the gateway fails
    (the row is then text-searchable only)."""
    try:
        return memory._vec_literal((await llm.embed([f"{subject}: {fact}"]))[0])
    except Exception:  # noqa: BLE001 - embeddings are best-effort by design
        return None


async def _supersede_candidates(conn: Any, subject: str, vec: str | None) -> list[dict]:
    """Currently valid facts with the same normalized subject, or within
    FACT_SAME_DIST of the new embedding on a subject-ish subject."""
    if vec is None:
        cur = await conn.execute(
            "SELECT id, subject FROM hq.facts WHERE invalid_at IS NULL AND subject = %s",
            (subject,),
        )
        return list(await cur.fetchall())
    cur = await conn.execute(
        "SELECT id, subject FROM hq.facts WHERE invalid_at IS NULL"
        " AND (subject = %s OR (embedding IS NOT NULL AND embedding <=> %s::vector < %s))",
        (subject, vec, memory.FACT_SAME_DIST),
    )
    rows = list(await cur.fetchall())
    return [r for r in rows if r["subject"] == subject or subject_ish(r["subject"], subject)]


@hq_tool(action=ActionClass.VAULT_WRITE)
async def record_fact(
    ctx: RunContext[HQDeps], subject: str, fact: str,
    source_path: str = "", confidence: str = "medium",
) -> str:
    """Record one durable fact about a subject (e.g. subject "owner timezone",
    fact "Asia/Kolkata"). A newer fact on the same subject replaces the old
    one at write time (the old row is kept, marked invalid). source_path is
    the vault note the fact comes from. confidence: low, medium or high.
    Facts recorded in a run that read web pages get provenance "web" and are
    hidden from recall_facts by default."""
    subj = memory.normalize_subject(subject)
    text = " ".join(fact.split())
    if not subj or len(subj) > MAX_SUBJECT_CHARS:
        raise ModelRetry(f"subject must be 1-{MAX_SUBJECT_CHARS} chars, a short noun phrase")
    if not text or len(text) > MAX_FACT_CHARS:
        raise ModelRetry(f"fact must be 1-{MAX_FACT_CHARS} chars, one statement")
    if confidence not in CONFIDENCES:
        raise ModelRetry(f"confidence must be one of {list(CONFIDENCES)}")
    src = source_path.strip() or None
    if src is not None:
        try:
            src = memory.normalize(src)
        except PermissionError as exc:
            raise ModelRetry(str(exc)) from None
    provenance = "web" if await run_read_web(ctx.deps.run_id) else "agent"
    vec = await _embed_fact(subj, text)
    try:
        async with db.tx() as conn:
            old = await _supersede_candidates(conn, subj, vec)
            cur = await conn.execute(
                "INSERT INTO hq.facts (subject, fact, source_path, provenance, agent,"
                " confidence, embedding) VALUES (%s, %s, %s, %s, %s, %s, %s::vector)"
                " RETURNING id",
                (subj, text, src, provenance, ctx.deps.agent, confidence, vec),
            )
            row = await cur.fetchone()
            assert row is not None
            new_id = int(row["id"])
            old_ids = [int(r["id"]) for r in old]
            if old_ids:
                await conn.execute(
                    "UPDATE hq.facts SET invalid_at = now(), superseded_by = %s"
                    " WHERE id = ANY(%s) AND invalid_at IS NULL",
                    (new_id, old_ids),
                )
    except psycopg.Error as exc:
        raise ModelRetry(f"facts store unavailable: {exc}") from None
    await emit(
        FACT_RECORDED_KIND, run_id=ctx.deps.run_id, task_id=ctx.deps.task_id,
        agent=ctx.deps.agent,
        payload={"id": new_id, "subject": subj, "provenance": provenance,
                 "superseded": old_ids, "source_path": src},
    )
    note = (
        "; provenance is web (this run read web content), so recall_facts hides it"
        " unless include_web=true"
        if provenance == "web" else ""
    )
    return f"recorded (superseded {len(old_ids)}){note}"


@hq_tool(action=ActionClass.READ, trust=Trust.VAULT)
async def recall_facts(
    ctx: RunContext[HQDeps], query: str, limit: int = 8, include_web: bool = False,
) -> list[dict]:
    """Currently valid facts matching a query (subject text match plus
    semantic similarity). Returns id, subject, fact, provenance, confidence,
    valid_at, source_path. Web-derived facts are left out unless
    include_web=true."""
    if not query.strip():
        raise ModelRetry("query must not be empty")
    return await memory.search_facts(
        query, limit=max(1, min(limit, RECALL_LIMIT_MAX)), include_web=include_web,
    )


@hq_tool(action=ActionClass.VAULT_WRITE)
async def retire_fact(ctx: RunContext[HQDeps], fact_id: int, reason: str) -> str:
    """Mark a fact as no longer valid (it is kept for history, never deleted).
    Use when a fact is wrong or outdated and there is no replacement to
    record. reason: one short sentence."""
    why = " ".join(reason.split())[:200]
    if not why:
        raise ModelRetry("reason must not be empty")
    try:
        row = await db.fetchone(
            "UPDATE hq.facts SET invalid_at = now() WHERE id = %s AND invalid_at IS NULL"
            " RETURNING id, subject",
            (fact_id,),
        )
    except psycopg.Error as exc:
        raise ModelRetry(f"facts store unavailable: {exc}") from None
    if row is None:
        raise ModelRetry(f"no valid fact with id {fact_id}; use recall_facts to find ids")
    await emit(
        FACT_RETIRED_KIND, run_id=ctx.deps.run_id, task_id=ctx.deps.task_id,
        agent=ctx.deps.agent,
        payload={"id": fact_id, "subject": row["subject"], "reason": why},
    )
    return f"retired fact {fact_id} ({row['subject']})"
