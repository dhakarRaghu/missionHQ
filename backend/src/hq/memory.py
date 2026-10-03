"""Vault access: markdown files in a git repo, committed once a day.

All vault WRITES go through ``write()``, which holds one process-wide
``asyncio.Lock`` so two writers never interleave. A write is not committed on
its own: it used to be, and the vault collected five commits an hour ("sage:
memory/agents/sage.md" 82 times) that filled his editor's source control. He
asked for one commit per day. ``commit_day()`` makes it, at the nightly
reindex, and its body still says which agent wrote which note. Reads are direct.
``search()`` is a facade: Postgres full-text search over ``hq.memory_chunks``
(migration 003) fused with pgvector cosine search over the same rows
(migration 005, ``embedding`` column) by reciprocal-rank fusion. The vector
half is best-effort: a failed query embedding or an empty column silently
yields FTS-only results, and the original grep scan is still the fallback
until the first reindex has filled the table. Callers never change.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
from datetime import date, datetime
from pathlib import Path, PurePosixPath
from typing import Any, cast
from zoneinfo import ZoneInfo

import psycopg
import yaml

from hq import db, llm, privacy
from hq.config import settings

log = logging.getLogger(__name__)

# Core memory blocks: hard size caps are the feature (Letta lesson).
BLOCK_CAPS = {
    "memory/user.md": 4000,
    "memory/decisions.md": 4000,
    "memory/active_projects.md": 4000,
}
# Per-agent working memory: memory/agents/<name>.md. One small block an agent
# rewrites at the end of every run so it never forgets its own last run. It is
# the agent's own scratch, not trusted shared memory: never injected into
# other agents (``load_core_blocks`` reads BLOCK_CAPS only).
WORKING_MEMORY_CAP = 2000
WORKING_MEMORY_DIR = "memory/agents/"
_WORKING_MEMORY_RE = re.compile(r"^memory/agents/([A-Za-z0-9_-]+)\.md$")

# Blocks no agent may write. Every agent reads them on every run, so a line
# in one is a standing instruction: only the owner writes them. Consolidation
# proposes changes in PROPOSALS_DIR and he promotes what he agrees with, so a
# poisoned or over-eager run can never mint a permanent instruction.
OWNER_ONLY = frozenset(BLOCK_CAPS)
PROPOSALS_DIR = "memory/proposals/"
MEMORY_PREFIX = "memory/"
# Destructive-edit gate: a rewrite of a memory note that drops more than this
# share of its existing non-empty lines is refused (write-time consolidation
# safety: continuous consolidation destroys knowledge unless it is bounded).
MAX_DROP_FRACTION = 0.30

_FRONTMATTER_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?", re.DOTALL)
_FILENAME_DATE_RE = re.compile(r"(?<!\d)(\d{4})-(\d{2})-(\d{2})(?!\d)")
# A markdown heading that starts with a date: "## 2026-09-02 ..." (any level).
_HEADING_DATE_RE = re.compile(r"^#{1,6}\s+(\d{4})-(\d{2})-(\d{2})", re.MULTILINE)


class WriteRefused(ValueError):
    """A vault write that a code gate rejected. The message tells the agent
    what to change; ``vault_write`` turns it into a ``ModelRetry``."""


def today() -> date:
    """Today's calendar date in CRON_TZ. Dates come from code, never from
    the model."""
    return datetime.now(ZoneInfo(settings().cron_tz)).date()

# Chunks are capped near this size so ts_headline snippets stay focused and
# one long note does not dominate ranking with a single huge tsvector.
CHUNK_CHARS = 1500
_HEADING_RE = re.compile(r"^(#{1,3})\s+(.*?)\s*#*\s*$")


def _vault() -> Path:
    return settings().vault_dir


def _safe_path(rel_path: str) -> Path:
    p = (_vault() / rel_path).resolve()
    if not p.is_relative_to(_vault().resolve()):
        raise PermissionError(f"path escapes vault: {rel_path}")
    return p


def normalize(rel_path: str) -> str:
    """Canonical vault-relative posix path. Rejects absolute paths and any
    ``..`` segment before resolving, so scope and cap checks see one spelling."""
    if rel_path.startswith("/") or ".." in PurePosixPath(rel_path).parts:
        raise PermissionError(f"invalid vault path: {rel_path}")
    return _safe_path(rel_path).relative_to(_vault().resolve()).as_posix()


def in_scope(rel_path: str, scopes: list[str]) -> bool:
    """Scoped writes: scope 'quarantine/**' admits only paths under quarantine/.
    ``rel_path`` must already be normalized."""
    if "**" in scopes or not scopes:
        return not scopes or "**" in scopes
    for scope in scopes:
        prefix = scope.removesuffix("/**").removesuffix("/*")
        if rel_path == prefix or rel_path.startswith(prefix.rstrip("/") + "/"):
            return True
    return False


def read(rel_path: str) -> str:
    return _safe_path(rel_path).read_text()


# --- write gates (pure: no I/O, so they can be tested without a vault) ------


def is_memory_note(rel_path: str) -> bool:
    """True for a core block or any note under memory/ (both are consolidated
    memory, so the destructive-edit gate applies).

    Per-agent working memory lives under memory/ too, but is exempt from the
    gate: see ``rewrite_problem``.
    """
    return rel_path in BLOCK_CAPS or rel_path.startswith(MEMORY_PREFIX)


def working_memory_path(agent: str) -> str:
    """Vault path of one agent's working-memory block."""
    return f"{WORKING_MEMORY_DIR}{agent}.md"


def block_cap(rel_path: str) -> int | None:
    """Size cap for a capped block, else None. Pattern-aware: the core blocks
    use BLOCK_CAPS; every memory/agents/<name>.md gets WORKING_MEMORY_CAP."""
    cap = BLOCK_CAPS.get(rel_path)
    if cap is not None:
        return cap
    if _WORKING_MEMORY_RE.match(rel_path):
        return WORKING_MEMORY_CAP
    return None


def load_working_memory(agent: str) -> str | None:
    """The agent's own block with a ``(N/CAP chars)`` heading, or None when
    the file does not exist yet. Only the owning agent should receive it."""
    rel = working_memory_path(agent)
    p = _vault() / rel
    if not p.exists():
        return None
    text = p.read_text()
    return f"## {rel} ({len(text)}/{WORKING_MEMORY_CAP} chars)\n{text}"


def future_date_in_name(rel_path: str, today_: date | None = None) -> str | None:
    """Problem text when the filename carries a YYYY-MM-DD later than today,
    else None. Only the filename is checked, not the folders."""
    today_ = today_ or today()
    name = PurePosixPath(rel_path).name
    for y, m, d in _FILENAME_DATE_RE.findall(name):
        try:
            found = date(int(y), int(m), int(d))
        except ValueError:
            continue  # not a real date (e.g. 2026-13-40); nothing to enforce
        if found > today_:
            return (
                f"date in filename is in the future ({found.isoformat()}); today is"
                f" {today_.isoformat()}. Use today's date or an earlier one."
            )
    return None


def future_heading_date(content: str, today_: date | None = None) -> str | None:
    """Problem text when any markdown heading starts with a YYYY-MM-DD later
    than today, else None. Agents have no clock, so a heading dated tomorrow
    is a mistake, never intent; the refusal tells them today's date."""
    today_ = today_ or today()
    for y, m, d in _HEADING_DATE_RE.findall(content):
        try:
            found = date(int(y), int(m), int(d))
        except ValueError:
            continue  # not a real date; nothing to enforce
        if found > today_:
            return (
                f"heading date {found.isoformat()} is in the future; today is"
                f" {today_.isoformat()}. Date the heading today or earlier, or append"
                " under the existing heading for today."
            )
    return None


def dropped_lines(old: str, new: str) -> tuple[int, int]:
    """``(dropped, total)``: how many of the distinct non-empty lines of ``old``
    (stripped) are absent from ``new``. Reordering drops nothing; appending
    drops nothing; rewording a line counts as dropping it."""
    old_set = {ln.strip() for ln in old.splitlines() if ln.strip()}
    new_set = {ln.strip() for ln in new.splitlines() if ln.strip()}
    return len(old_set - new_set), len(old_set)


def rewrite_problem(rel_path: str, old: str, new: str) -> str | None:
    """Destructive-edit gate. For a memory note (``is_memory_note``) whose
    rewrite removes more than MAX_DROP_FRACTION of the existing non-empty
    lines, return the refusal text; otherwise None. Pure: callers pass the
    current content.

    Working memory (``memory/agents/<name>.md``) is exempt. That block exists
    to be rewritten at the end of every run: its first section is the last
    run, so replacing it always drops most of the file. Applying the gate here
    made the block impossible to update at all, which failed the run that had
    already done its real work and left every notebook stale. Its protection
    is the size cap (WORKING_MEMORY_CAP), not this gate.
    """
    if (
        not is_memory_note(rel_path)
        or _WORKING_MEMORY_RE.match(rel_path)
        or not old.strip()
    ):
        return None
    dropped, total = dropped_lines(old, new)
    if total and dropped / total > MAX_DROP_FRACTION:
        return (
            f"this rewrite drops {dropped} of {total} lines of {rel_path}; consolidation"
            " must preserve detail — keep the lines you are not replacing, or ask the"
            " owner to approve a rewrite via announce"
        )
    return None


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """``(meta, body)``. ``meta`` is {} when the note has no leading
    ``---`` block. Raises ``WriteRefused`` when the block is not a YAML
    mapping, so the agent fixes it instead of the note silently losing it."""
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError as exc:
        raise WriteRefused(f"frontmatter is not valid YAML: {exc}") from None
    if not isinstance(meta, dict):
        raise WriteRefused("frontmatter must be a YAML mapping of key: value lines")
    return meta, text[m.end():]


def render_frontmatter(meta: dict[str, Any], body: str) -> str:
    block = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, default_flow_style=False)
    return f"---\n{block.rstrip()}\n---\n{body.lstrip(chr(10))}"


def stamp_frontmatter(
    text: str, *, author: str, provenance: str, created: date | None = None,
) -> str:
    """Merge code-owned keys into a note's frontmatter. Agent keys are kept;
    ``created``, ``author`` and ``provenance`` are set by code and win over
    whatever the agent supplied (dates come from code, never the model)."""
    meta, body = parse_frontmatter(text)
    stamped: dict[str, Any] = {
        "created": created or today(),  # a date object: YAML renders it unquoted
        "author": author,
        "provenance": provenance,
    }
    stamped.update({k: v for k, v in meta.items() if k not in stamped})
    return render_frontmatter(stamped, body)


def from_web(rel_path: str, text: str) -> bool:
    """True for a note that carries web-derived text: anything in quarantine/,
    and any note code stamped ``provenance: web`` (its run read the web or the
    owner's browser). Such a note is data; it never feeds shared memory."""
    if rel_path.startswith("quarantine/"):
        return True
    meta, _body = parse_frontmatter(text)
    return str(meta.get("provenance", "")).strip().lower() == "web"


def quarantine_problem(rel_path: str, meta: dict[str, Any]) -> str | None:
    """quarantine/ notes hold web-derived text and must cite their sources:
    a non-empty ``source_urls`` list is required in the agent's frontmatter."""
    if not rel_path.startswith("quarantine/"):
        return None
    urls = meta.get("source_urls")
    if not isinstance(urls, list) or not urls or not all(isinstance(u, str) for u in urls):
        return (
            "quarantine notes need frontmatter with a `source_urls:` list of the pages"
            " the note is based on, e.g. ---\\nsource_urls:\\n  - https://...\\n---"
        )
    return None


def has_title(text: str) -> bool:
    """Light check (warn-only): does the body carry a ``# `` title line."""
    _, body = parse_frontmatter(text)
    return any(ln.startswith("# ") for ln in body.splitlines())


def trim_to_cap(rel_path: str, content: str) -> tuple[str, int]:
    """An agent's own block, cut to its cap by dropping its oldest lines.

    Agents spent three and four calls each night failing the cap by a few
    characters and trying again (2026-09-17: seven refusals in one evening).
    The block is the agent's own scratch memory and its newest lines are the
    ones worth keeping, so the oldest go and the tool says how many. Shared
    blocks are not trimmed here: what to drop from those is a judgement.
    """
    cap = block_cap(rel_path)
    if cap is None or len(content) <= cap or not _WORKING_MEMORY_RE.match(rel_path):
        return content, 0
    _meta, body = parse_frontmatter(content)
    head = content[: len(content) - len(body)]
    lines = body.splitlines()
    keep_first = 1 if lines and lines[0].startswith("# ") else 0
    title, rest = lines[:keep_first], lines[keep_first:]
    dropped = 0
    while rest and len("\n".join([*head.splitlines(), *title, *rest])) > cap:
        rest.pop(0)
        dropped += 1
    return head + "\n".join([*title, *rest]).rstrip() + "\n", dropped


def write_problem(rel_path: str, content: str, *, actor: str, existing: str | None) -> str | None:
    """Every code gate that needs only the target path, the new content and
    the current content: owner-only block, memory-block cap (``block_cap``),
    future date in the filename, future date in a heading, destructive edit.
    Also the employer gate (``hq.privacy``) for every writer but the owner.
    ``actor == 'owner'`` skips the owner-only, employer, future-heading and
    destructive gates (the owner may rewrite anything). Returns the refusal text or None."""
    if actor != "owner" and rel_path in OWNER_ONLY:
        return (
            f"refused: {rel_path} is owner-only; agents never write a shared memory"
            f" block. Write the change you want as a proposal in"
            f" {PROPOSALS_DIR}<YYYY-MM-DD>.md and the owner promotes it"
        )
    if actor != "owner":
        refused = privacy.problem(rel_path, content)
        if refused:
            return refused
    cap = block_cap(rel_path)
    if cap is not None and len(content) > cap:
        return (
            f"{rel_path} is {len(content)} chars; its memory-block cap is {cap}."
            f" Trim at least {len(content) - cap} chars: drop the oldest or duplicated"
            " lines and keep the newest facts. The cap is not negotiable."
        )
    problem = future_date_in_name(rel_path)
    if problem:
        return problem
    if actor != "owner":
        problem = future_heading_date(content)
        if problem:
            return problem
    if actor != "owner" and existing is not None:
        return rewrite_problem(rel_path, existing, content)
    return None


# Who wrote what since the last daily commit. It lives inside `.git`, so it
# is never tracked itself, and it survives a restart between writes and the
# nightly commit, which an in-memory list would not.
PENDING_LEDGER = "hq-pending-writes"


def _ledger() -> Path | None:
    git_dir = _vault() / ".git"
    return git_dir / PENDING_LEDGER if git_dir.is_dir() else None


def write_sync(rel_path: str, content: str, *, actor: str) -> str:
    """Blocking write. Call ONLY via ``write()``. Runs the code gates in
    ``write_problem`` against the current file and raises ``WriteRefused``
    (a ValueError) when one refuses. Not committed here: the write is noted in
    the ledger, and ``commit_day`` commits the day's writes together."""
    rel_path = normalize(rel_path)
    p = _safe_path(rel_path)
    existing = p.read_text() if p.exists() else None
    problem = write_problem(rel_path, content, actor=actor, existing=existing)
    if problem:
        raise WriteRefused(problem)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    ledger = _ledger()
    if ledger is not None:
        with ledger.open("a") as fh:
            fh.write(f"{actor}\t{rel_path}\n")
    return rel_path


def commit_day_sync(day: date | None = None) -> list[str]:
    """Blocking. Commit every change in the vault as one commit for the day.
    Call ONLY via ``commit_day``.

    The subject says how many notes changed; the body lists each one with the
    agent that wrote it, taken from the ledger. A changed path the ledger does
    not know was edited by hand, and is listed as the owner's. Returns the
    changed paths, ``[]`` when there was nothing to commit.
    """
    status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all"],
        cwd=_vault(), check=True, capture_output=True, text=True,
    ).stdout
    paths = sorted({line[3:].strip().strip('"') for line in status.splitlines() if line.strip()})
    ledger = _ledger()
    if not paths:
        if ledger is not None:
            ledger.unlink(missing_ok=True)
        return []
    authors: dict[str, set[str]] = {}
    if ledger is not None and ledger.exists():
        for line in ledger.read_text().splitlines():
            actor, _, rel = line.partition("\t")
            if rel:
                authors.setdefault(rel, set()).add(actor)
    body = "\n".join(f"{', '.join(sorted(authors.get(rel) or {'owner'}))}: {rel}" for rel in paths)
    who = sorted({a for rel in paths for a in (authors.get(rel) or {"owner"})})
    subject = (f"vault {(day or datetime.now(ZoneInfo(settings().cron_tz)).date()).isoformat()}: {len(paths)} note"
               f"{'' if len(paths) == 1 else 's'} ({', '.join(who)})")
    subprocess.run(["git", "add", "-A"], cwd=_vault(), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", subject, "-m", body],
                   cwd=_vault(), check=True, capture_output=True)
    if ledger is not None:
        ledger.unlink(missing_ok=True)
    return paths


def push_sync() -> bool | None:
    """Blocking. Push the vault to its `origin` remote. None when it has no
    remote, else whether the push worked.

    Since 2026-10-03 the vault is shared with his other laptop through a
    private GitHub repo. The push runs here, in the backend, because a
    launchd job running /bin/bash may not read ~/Desktop (macOS answered
    "Operation not permitted"), and because here it follows the commit it
    pushes. It runs every night, so a push that failed is retried with the
    next one."""
    remote = subprocess.run(["git", "remote", "get-url", "origin"], cwd=_vault(),
                            capture_output=True, text=True, check=False)
    if remote.returncode != 0:
        return None
    pushed = subprocess.run(
        ["git", "push", "--quiet", "origin", "HEAD"], cwd=_vault(), capture_output=True,
        text=True, timeout=PUSH_TIMEOUT_S, env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}, check=False)
    if pushed.returncode != 0:
        log.warning("memory: could not push the vault: %s", pushed.stderr.strip()[:300])
    return pushed.returncode == 0


PUSH_TIMEOUT_S = 60
_write_lock = asyncio.Lock()


async def commit_day() -> list[str]:
    """The day's one vault commit, serialized with writes, then the push.
    Best-effort: a git failure is logged and yields ``[]``; it never stops
    the nightly run."""
    async with _write_lock:
        try:
            paths = await asyncio.to_thread(commit_day_sync)
        except (subprocess.CalledProcessError, OSError) as exc:
            log.warning("memory: could not make the daily vault commit: %s", exc)
            paths = []
    if paths:
        log.info("memory: committed %d vault notes for the day", len(paths))
    try:
        if await asyncio.to_thread(push_sync):
            log.info("memory: pushed the vault")
    except (subprocess.TimeoutExpired, OSError) as exc:
        log.warning("memory: could not push the vault: %s", exc)
    return paths


async def write(rel_path: str, content: str, *, actor: str) -> str:
    """Serialized vault write: one writer at a time.
    The FTS index is refreshed after the write; an index failure is logged,
    never raised — a vault write must not fail because of the index."""
    async with _write_lock:
        rel = await asyncio.to_thread(write_sync, rel_path, content, actor=actor)
        try:
            await index_note(rel)
        except Exception as exc:  # noqa: BLE001 - index is best-effort by design
            log.warning("memory: could not index %s after write: %s", rel, exc)
        return rel


def block_status() -> list[dict]:
    """Fill level of every core memory block: ``{path, chars, cap, pct}``.
    A missing block reports 0 chars. ``pct`` is rounded to a whole number."""
    rows: list[dict] = []
    for rel, cap in BLOCK_CAPS.items():
        p = _vault() / rel
        chars = len(p.read_text()) if p.exists() else 0
        rows.append({"path": rel, "chars": chars, "cap": cap, "pct": round(100 * chars / cap)})
    return rows


def load_core_blocks(names: list[str] | None = None) -> str:
    """Memory blocks injected into an agent's instructions. ``names`` picks
    blocks by file stem ("user", "decisions", ...); None means every block.
    Each heading carries ``(N/CAP chars)`` so agents see how full a block is
    before they try to add to it."""
    parts = []
    for rel, cap in BLOCK_CAPS.items():
        if names is not None and Path(rel).stem not in names:
            continue
        p = _vault() / rel
        if p.exists():
            text = p.read_text()
            parts.append(f"## {rel} ({len(text)}/{cap} chars)\n{text}")
    return "\n\n".join(parts)


# --- chunking ---------------------------------------------------------------


def _split_paragraphs(section: str) -> list[str]:
    """Pack blank-line-separated paragraphs into pieces of at most CHUNK_CHARS.
    A single paragraph longer than the cap is cut at the cap."""
    pieces: list[str] = []
    current = ""
    for para in re.split(r"\n\s*\n", section):
        para = para.strip()
        if not para:
            continue
        while len(para) > CHUNK_CHARS:
            if current:
                pieces.append(current)
                current = ""
            pieces.append(para[:CHUNK_CHARS])
            para = para[CHUNK_CHARS:].lstrip()
        if not para:
            continue
        candidate = f"{current}\n\n{para}" if current else para
        if len(candidate) > CHUNK_CHARS and current:
            pieces.append(current)
            current = para
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def chunk_note(rel_path: str, text: str) -> list[tuple[int, str, str]]:
    """Split a note into ``(chunk_no, heading, body)`` tuples.

    Sections start at markdown headings (#, ##, ###); ``heading`` is the text
    of the nearest heading above the chunk ('' before the first one). Sections
    longer than CHUNK_CHARS are split on blank lines. ``rel_path`` is accepted
    for symmetry with the index row and future per-path rules."""
    sections: list[tuple[str, list[str]]] = [("", [])]
    for line in text.splitlines():
        m = _HEADING_RE.match(line)
        if m:
            sections.append((m.group(2).strip(), []))
        else:
            sections[-1][1].append(line)
    chunks: list[tuple[int, str, str]] = []
    for heading, lines in sections:
        for body in _split_paragraphs("\n".join(lines)):
            chunks.append((len(chunks), heading, body))
    return chunks


# --- indexing ---------------------------------------------------------------


async def _replace_chunks(conn: psycopg.AsyncConnection, rel_path: str,
                          chunks: list[tuple[int, str, str]]) -> int:
    """Make the rows for ``rel_path`` equal ``chunks``. Rows whose
    (chunk_no, heading, body) are unchanged are left alone so they keep their
    embedding; only changed or new chunks are rewritten (embedding NULL until
    ``_embed_missing`` fills it). Returns the number of rows rewritten.

    One writer per path at a time: two runs writing the same note in the same
    minute (the daily note and consolidation, 2026-09-24 05:15) both read the
    old rows, both inserted chunk 0, and the second failed its workflow on a
    unique violation. The lock is held to the end of the caller's transaction.
    """
    await conn.execute("SELECT pg_advisory_xact_lock(hashtext('memory_chunks:' || %s))",
                       (rel_path,))
    cur = await conn.execute(
        "SELECT chunk_no, heading, body FROM hq.memory_chunks WHERE path = %s", (rel_path,)
    )
    rows = cast(list[dict[str, Any]], await cur.fetchall())  # pool uses dict_row
    existing = {r["chunk_no"]: (r["heading"], r["body"]) for r in rows}
    unchanged = [n for n, h, b in chunks if existing.get(n) == (h, b)]
    await conn.execute(
        "DELETE FROM hq.memory_chunks WHERE path = %s AND NOT (chunk_no = ANY(%s))",
        (rel_path, unchanged),
    )
    changed = [(rel_path, n, h, b) for n, h, b in chunks if existing.get(n) != (h, b)]
    if changed:
        async with conn.cursor() as cur2:
            await cur2.executemany(
                "INSERT INTO hq.memory_chunks (path, chunk_no, heading, body)"
                " VALUES (%s, %s, %s, %s) ON CONFLICT (path, chunk_no) DO UPDATE"
                " SET heading = EXCLUDED.heading, body = EXCLUDED.body, embedding = NULL",
                changed,
            )
    return len(changed)


def _vec_literal(vec: list[float]) -> str:
    """pgvector text form; psycopg has no vector adapter, so SQL casts it."""
    return "[" + ",".join(repr(x) for x in vec) + "]"


def _embed_text(heading: str, body: str) -> str:
    return f"{heading}\n\n{body}" if heading else body


async def _embed_missing(paths: list[str] | None = None) -> int:
    """Fill ``embedding`` for rows where it is NULL (all paths when ``paths``
    is None). Best-effort by design: gateway or DB errors, including a
    missing column before migration 005, are logged and never raised, so FTS
    keeps working. Each batch is written as soon as it returns, so a failure
    mid-way keeps the progress made. Returns the number of chunks embedded."""
    done = 0
    try:
        sql = "SELECT id, heading, body FROM hq.memory_chunks WHERE embedding IS NULL"
        params: tuple = ()
        if paths is not None:
            sql += " AND path = ANY(%s)"
            params = (paths,)
        rows = await db.fetch(sql + " ORDER BY id", params)
        for start in range(0, len(rows), llm.EMBED_BATCH):
            batch = rows[start:start + llm.EMBED_BATCH]
            vectors = await llm.embed([_embed_text(r["heading"], r["body"]) for r in batch])
            async with db.tx() as conn, conn.cursor() as cur:
                await cur.executemany(
                    "UPDATE hq.memory_chunks SET embedding = %s::vector WHERE id = %s",
                    [(_vec_literal(v), r["id"]) for v, r in zip(vectors, batch, strict=True)],
                )
            done += len(batch)
    except Exception as exc:  # noqa: BLE001 - embeddings are best-effort by design
        log.warning("memory: embedding stopped after %d chunks: %s", done, exc)
    log.debug("memory: embedded %d chunks", done)
    return done


async def index_note(rel_path: str) -> int:
    """(Re)index one note in one transaction, then embed its changed chunks
    (best-effort, outside the transaction). A missing file clears its
    chunks. Returns the number of chunks stored. Raises on DB errors; the
    caller in ``write()`` turns that into a warning."""
    rel_path = normalize(rel_path)
    try:
        text = await asyncio.to_thread(read, rel_path)
    except FileNotFoundError:
        text = ""
    chunks = chunk_note(rel_path, text)
    async with db.tx() as conn:
        changed = await _replace_chunks(conn, rel_path, chunks)
    if changed:
        await _embed_missing([rel_path])
    return len(chunks)


def _read_all_notes() -> dict[str, str]:
    root = _vault()
    notes: dict[str, str] = {}
    for p in root.rglob("*.md"):
        if ".git" in p.parts:
            continue
        try:
            notes[p.relative_to(root).as_posix()] = p.read_text()
        except OSError as exc:
            log.warning("memory: skipping unreadable %s: %s", p, exc)
    return notes


async def reindex_all() -> int:
    """Rebuild the whole index in one transaction: every *.md under the vault
    (skipping .git) is re-chunked, and chunks for deleted notes are removed.
    The day's vault commit is made first (``commit_day``): the agents' writes
    and any hand edits, as one commit. Returns the total chunk count."""
    await commit_day()
    notes = await asyncio.to_thread(_read_all_notes)
    total = 0
    changed = 0
    async with db.tx() as conn:
        for rel_path, text in sorted(notes.items()):
            chunks = chunk_note(rel_path, text)
            changed += await _replace_chunks(conn, rel_path, chunks)
            total += len(chunks)
        await conn.execute(
            "DELETE FROM hq.memory_chunks WHERE NOT (path = ANY(%s))", (list(notes),)
        )
    log.info("memory: reindexed %d notes into %d chunks (%d rewritten)",
             len(notes), total, changed)
    # Embeds every row still NULL, not only the rewritten ones, so a reindex
    # also repairs rows an earlier gateway failure left behind.
    embedded = await _embed_missing()
    log.debug("memory: reindex embedded %d of %d chunks", embedded, total)
    return total


_background: set[asyncio.Task] = set()


async def ensure_index() -> int:
    """Startup hook: fill the index when ``hq.memory_chunks`` is empty (first
    boot after migration 003). When it is already filled, rows without an
    embedding (first boot after migration 005, or a past gateway failure)
    are embedded in a background task so startup is not delayed. Returns
    chunks written, 0 when nothing was needed or when indexing failed
    (failure is logged, never raised, so the API still starts and
    ``search()`` falls back to grep)."""
    try:
        row = await db.fetchone("SELECT EXISTS (SELECT 1 FROM hq.memory_chunks) AS filled")
        if row and row["filled"]:
            task = asyncio.create_task(_embed_missing(), name="memory.embed_missing")
            _background.add(task)
            task.add_done_callback(_background.discard)
            return 0
        return await reindex_all()
    except Exception as exc:  # noqa: BLE001 - startup must not fail on the index
        log.warning("memory: ensure_index failed, search falls back to grep: %s", exc)
        return 0


# --- search -----------------------------------------------------------------

_FTS_SQL = """
WITH q AS (SELECT websearch_to_tsquery('english', %s) AS q),
best AS (
  SELECT DISTINCT ON (c.path)
         c.path, c.heading, c.body, ts_rank_cd(c.tsv, q.q) AS rank
  FROM hq.memory_chunks c, q
  WHERE c.tsv @@ q.q
  ORDER BY c.path, rank DESC, c.chunk_no
)
SELECT b.path, b.heading, b.rank,
       ts_headline('english', b.body, q.q,
                   'MaxWords=40, MinWords=15, StartSel=**, StopSel=**') AS snippet
FROM best b, q
ORDER BY b.rank DESC, b.path
LIMIT %s
"""


async def _fts_search(query: str, limit: int) -> list[dict] | None:
    """Ranked FTS hits, best chunk per path. ``None`` means the index is
    empty, so the caller should use grep instead."""
    row = await db.fetchone("SELECT EXISTS (SELECT 1 FROM hq.memory_chunks) AS filled")
    if not row or not row["filled"]:
        return None
    rows = await db.fetch(_FTS_SQL, (query, limit))
    return [
        {
            "path": r["path"],
            "heading": r["heading"],
            "snippet": r["snippet"],
            "rank": float(r["rank"]),
        }
        for r in rows
    ]


# Nearest chunks first (index-friendly: ORDER BY distance LIMIT n), then one
# best chunk per path. The inner LIMIT is a multiple of the requested count
# so a note with many close chunks does not crowd out other notes.
_VEC_SQL = """
WITH near AS (
  SELECT path, heading, body, embedding <=> %s::vector AS dist
  FROM hq.memory_chunks
  WHERE embedding IS NOT NULL
  ORDER BY dist
  LIMIT %s
)
SELECT DISTINCT ON (path) path, heading, body, dist
FROM near
ORDER BY path, dist
"""

SNIPPET_CHARS = 300
RRF_K = 60


async def _vector_search(query: str, limit: int) -> list[dict]:
    """Cosine-nearest chunk per path, ``{path, heading, body, dist}`` ordered
    by distance. Returns ``[]`` when no row has an embedding yet (the
    query is not embedded in that case), when the column does not exist
    (migration 005 not applied), or when embedding the query fails."""
    try:
        row = await db.fetchone(
            "SELECT EXISTS (SELECT 1 FROM hq.memory_chunks WHERE embedding IS NOT NULL) AS vec"
        )
        if not row or not row["vec"]:
            return []
        qvec = (await llm.embed([query]))[0]
        rows = await db.fetch(_VEC_SQL, (_vec_literal(qvec), limit * 4))
    except Exception as exc:  # noqa: BLE001 - vector half is best-effort; FTS still answers
        log.debug("memory: vector search skipped: %s", exc)
        return []
    rows.sort(key=lambda r: r["dist"])
    return [
        {"path": r["path"], "heading": r["heading"], "body": r["body"],
         "dist": float(r["dist"])}
        for r in rows[:limit]
    ]


def _fuse(fts: list[dict], vec: list[dict], limit: int) -> list[dict]:
    """Reciprocal-rank fusion: score(path) = sum over lists of 1/(RRF_K + rank),
    rank starting at 1. Each list already holds one row per path, so paths
    dedupe by key. Snippet and heading come from the FTS hit (ts_headline)
    when the path has one, else from the vector hit (first SNIPPET_CHARS of
    the body). ``rank`` in the result is the fused score."""
    score: dict[str, float] = {}
    for hits in (fts, vec):
        for i, h in enumerate(hits, start=1):
            score[h["path"]] = score.get(h["path"], 0.0) + 1.0 / (RRF_K + i)
    by_path_fts = {h["path"]: h for h in fts}
    by_path_vec = {h["path"]: h for h in vec}
    out: list[dict] = []
    for path, s in sorted(score.items(), key=lambda kv: (-kv[1], kv[0]))[:limit]:
        if path in by_path_fts:
            f = by_path_fts[path]
            heading, snippet = f["heading"], f["snippet"]
        else:
            v = by_path_vec[path]
            heading, snippet = v["heading"], v["body"][:SNIPPET_CHARS]
        out.append({"path": path, "heading": heading, "snippet": snippet, "rank": s})
    return out


async def _grep_search(query: str, *, limit: int = 8) -> list[dict]:
    """v1 fallback: whole-file word-count scan. Used until the FTS index has
    rows, or when the table is missing."""
    def _scan() -> list[dict]:
        words = [w for w in re.split(r"\W+", query.lower()) if len(w) > 2]
        hits: list[tuple[int, str, str]] = []
        for p in _vault().rglob("*.md"):
            if ".git" in p.parts:
                continue
            try:
                text = p.read_text()
            except OSError:
                continue
            rel = p.relative_to(_vault()).as_posix()
            # Folder and file names carry meaning ("quarantine", "daily"), so
            # they count as matches too — weighted above a body mention.
            low = text.lower()
            score = sum(low.count(w) + 3 * rel.lower().count(w) for w in words)
            if score > 0:
                hits.append((score, rel, text[:400]))
        hits.sort(reverse=True)
        return [{"path": path, "snippet": snip} for _, path, snip in hits[:limit]]

    return await asyncio.to_thread(_scan)


async def search(query: str, *, limit: int = 8) -> list[dict]:
    """Facade: hybrid search, one best chunk per path, each hit
    ``{path, heading, snippet, rank}``.

    FTS (``ts_rank_cd``) and pgvector cosine search run concurrently over
    ``max(3 * limit, 20)`` candidates each and are fused by reciprocal-rank
    fusion; ``rank`` is then the fused score. When the vector half yields
    nothing (query embedding failed, no embeddings stored yet, migration 005
    not applied) the FTS hits are returned as-is with ``rank`` =
    ``ts_rank_cd``. Falls back to grep hits ``{path, snippet}`` while the
    index is empty or the table is missing."""
    cand = max(3 * limit, 20)
    try:
        fts, vec = await asyncio.gather(_fts_search(query, cand), _vector_search(query, cand))
    except psycopg.Error as exc:
        log.warning("memory: FTS unavailable, using grep: %s", exc)
        return await _grep_search(query, limit=limit)
    if fts is None:
        return await _grep_search(query, limit=limit)
    if not vec:
        return fts[:limit]
    return _fuse(fts, vec, limit)


# --- facts (migration 006, hq.facts) -----------------------------------------

# Cosine distance under which two fact embeddings are "the same statement".
FACT_SAME_DIST = 0.15
# Cosine distance under which a fact counts as a recall hit for a query.
FACT_RECALL_DIST = 0.5
FACT_COLUMNS = "id, subject, fact, provenance, confidence, valid_at, source_path"


def normalize_subject(subject: str) -> str:
    """Canonical subject key: lowercase, single-spaced, no trailing
    punctuation. Stored as-is so ``subject = %s`` uses the index."""
    return " ".join(subject.split()).lower().strip(" .:;,")


def _fact_row(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": int(r["id"]),
        "subject": r["subject"],
        "fact": r["fact"],
        "provenance": r["provenance"],
        "confidence": r["confidence"],
        "valid_at": r["valid_at"].isoformat(),
        "source_path": r["source_path"],
    }


_FACTS_TEXT_SQL = f"""
SELECT {FACT_COLUMNS}, (subject ILIKE %s) AS subj_hit, NULL::float AS dist
FROM hq.facts
WHERE invalid_at IS NULL AND (provenance <> 'web' OR %s)
  AND (subject ILIKE %s OR fact ILIKE %s)
ORDER BY subj_hit DESC, valid_at DESC
LIMIT %s
"""

_FACTS_HYBRID_SQL = f"""
SELECT {FACT_COLUMNS}, (subject ILIKE %s) AS subj_hit,
       CASE WHEN embedding IS NULL THEN NULL ELSE embedding <=> %s::vector END AS dist
FROM hq.facts
WHERE invalid_at IS NULL AND (provenance <> 'web' OR %s)
  AND (subject ILIKE %s OR fact ILIKE %s
       OR (embedding IS NOT NULL AND embedding <=> %s::vector < %s))
ORDER BY subj_hit DESC, dist ASC NULLS LAST, valid_at DESC
LIMIT %s
"""


async def search_facts(query: str, *, limit: int = 8, include_web: bool = False) -> list[dict]:
    """Currently valid facts (``invalid_at IS NULL``) matching ``query``:
    ``subject ILIKE`` / ``fact ILIKE`` plus pgvector cosine on the fact
    embedding, subject matches first. ``provenance = 'web'`` rows are left
    out unless ``include_web``. Best-effort: when the query embedding fails
    the text half alone answers; when the table is missing (migration 006
    not applied) the result is ``[]``. Each hit is
    ``{id, subject, fact, provenance, confidence, valid_at, source_path}``."""
    like = f"%{query.strip()}%"
    try:
        try:
            qvec = _vec_literal((await llm.embed([query]))[0])
        except Exception as exc:  # noqa: BLE001 - vector half is best-effort
            log.debug("memory: fact query embedding skipped: %s", exc)
            qvec = None
        if qvec is None:
            rows = await db.fetch(_FACTS_TEXT_SQL, (like, include_web, like, like, limit))
        else:
            rows = await db.fetch(
                _FACTS_HYBRID_SQL,
                (like, qvec, include_web, like, like, qvec, FACT_RECALL_DIST, limit),
            )
    except psycopg.Error as exc:
        log.warning("memory: facts unavailable: %s", exc)
        return []
    return [_fact_row(r) for r in rows]


async def recall_context(query: str, *, limit: int = 8, include_web: bool = False) -> dict:
    """Everything a run should see about ``query`` before it starts:
    ``{"notes": [...], "facts": [...]}``.

    ``notes`` are ``search()`` hits (``{path, heading, snippet, rank}``) and
    ``facts`` are ``search_facts()`` hits (valid facts only, web provenance
    excluded unless ``include_web``). The two searches run concurrently and
    each is best-effort, so a missing facts table or a failed embedding still
    returns the other half. Unit shape: ``recall_context("dbos cron")`` on an
    empty vault and DB returns ``{"notes": [], "facts": []}``; after
    ``record_fact("dbos", "cron runs in CRON_TZ")`` the ``facts`` list holds
    one row whose ``subject`` is ``"dbos"``; after a second record_fact on
    the same subject the first row is gone (superseded) and the new one is
    returned."""
    notes, facts = await asyncio.gather(
        search(query, limit=limit),
        search_facts(query, limit=limit, include_web=include_web),
    )
    return {"notes": notes, "facts": facts}
