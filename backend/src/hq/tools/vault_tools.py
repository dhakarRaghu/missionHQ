"""Vault tools. Writes honor per-agent scopes (the scoped-trifecta rule).

``vault_write`` is the write path every agent uses, so the memory-layer gates
live here and in ``memory.write_problem``:

- scope check (``in_scope``), owner-only blocks (``memory/rules.md``),
  memory-block caps, future dates in filenames, destructive-edit gate for
  memory notes: all refused with ``ModelRetry`` so the agent adapts.
- provenance + dates on every AI-written note outside memory/: code merges
  ``created`` (today in CRON_TZ), ``author`` and ``provenance`` (``web`` when
  this run read web content, else ``agent``) into the note's frontmatter.
  quarantine/ notes must supply a ``source_urls:`` list.
"""

from __future__ import annotations

import asyncio
import logging
import time

from pydantic_ai import ModelRetry, RunContext

from hq import memory, voice
from hq.config import settings
from hq.safety import ActionClass, Trust
from hq.tools.policy_tools import _run_read_web as run_read_web
from hq.tools.registry import HQDeps, hq_tool

log = logging.getLogger(__name__)

DIR_HINT_ENTRIES = 30   # folder entries shown when vault_read gets a folder path
LIST_LIMIT = 500        # vault_list rows


def _folder_entries(path: str) -> list[str]:
    folder = memory._safe_path(path)
    return sorted(p.name for p in folder.iterdir() if not p.name.startswith("."))


# His own files live in the repo, not the vault, and agents keep looking for
# them here: learning/sources.md, learning/lessons/*.md (2026-09-17, four
# failed reads in one run). Name the tool that does reach them.
_REPO_PATHS = {
    "learning/lessons": "lessons are read with read_lesson; list_lessons gives the paths",
    "learning/courses": "course specs are not read by agents",
    "learning/study-material": "course sources are read with read_course_source",
    "learning/sources.md": "the roster is not readable by a tool; the part you need"
                           " arrives inside your brief",
    "learning/path.md": "his path arrives inside your brief, not through the vault",
}


def _missing_note(path: str) -> str:
    clean = path.strip().lstrip("./")
    for prefix, hint in _REPO_PATHS.items():
        if clean.startswith(prefix):
            return f"{path!r} is a repo file, not a vault note: {hint}"
    return (
        f"no note at {path!r}; use memory_search to find the right path, or create"
        " the note with vault_write if it is meant to be new"
    )


@hq_tool(action=ActionClass.READ, trust=Trust.VAULT)
async def vault_read(ctx: RunContext[HQDeps], path: str) -> str:
    """Read a markdown note from the vault by relative path (a file, not a folder)."""
    try:
        return await asyncio.to_thread(memory.read, path)
    except FileNotFoundError:
        raise ModelRetry(_missing_note(path)) from None
    except IsADirectoryError:
        try:
            entries = await asyncio.to_thread(_folder_entries, path)
        except OSError:
            entries = []
        shown = ", ".join(entries[:DIR_HINT_ENTRIES]) or "(empty)"
        more = f" (+{len(entries) - DIR_HINT_ENTRIES} more)" if len(entries) > DIR_HINT_ENTRIES else ""
        raise ModelRetry(
            f"{path!r} is a folder; entries: {shown}{more} - pass a file path"
            " (for example the folder plus one of these names), or call vault_list"
        ) from None
    except PermissionError as exc:
        raise ModelRetry(str(exc)) from None


def _list_notes(folder: str, since_days: int) -> list[dict]:
    root = memory._vault().resolve()
    base = memory._safe_path(folder) if folder else root
    if not base.exists():
        raise FileNotFoundError(folder)
    if not base.is_dir():
        raise NotADirectoryError(folder)
    cutoff = time.time() - since_days * 86400 if since_days > 0 else None
    rows: list[dict] = []
    for p in base.rglob("*.md"):
        if ".git" in p.parts or not p.is_file():
            continue
        st = p.stat()
        if cutoff is not None and st.st_mtime < cutoff:
            continue
        rows.append({
            "path": p.resolve().relative_to(root).as_posix(),
            "size": st.st_size,
            "mtime": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(st.st_mtime)),
        })
    rows.sort(key=lambda r: r["mtime"], reverse=True)
    return rows[:LIST_LIMIT]


@hq_tool(action=ActionClass.READ, trust=Trust.VAULT)
async def vault_list(ctx: RunContext[HQDeps], folder: str = "", since_days: int = 0) -> list[dict]:
    """List markdown notes under a vault folder (recursive): path, size in bytes,
    mtime (newest first). folder="" means the whole vault. since_days > 0 keeps
    only notes modified in the last N days. One call replaces many searches
    when you only need to know what exists or what changed recently."""
    try:
        return await asyncio.to_thread(_list_notes, folder, max(0, int(since_days)))
    except FileNotFoundError:
        raise ModelRetry(_missing_note(folder) if folder.strip().lstrip('./').startswith('learning')
                         else f"no folder {folder!r} in the vault; call vault_list with"
                              " folder='' to see the top level") from None
    except NotADirectoryError:
        raise ModelRetry(f"{folder!r} is a file, not a folder; use vault_read for it") from None
    except PermissionError as exc:
        raise ModelRetry(str(exc)) from None


@hq_tool(action=ActionClass.READ, trust=Trust.VAULT)
async def memory_search(ctx: RunContext[HQDeps], query: str) -> list[dict]:
    """Search the vault; returns matching paths with snippets."""
    return await memory.search(query)


async def _run_provenance(ctx: RunContext[HQDeps]) -> str:
    """``web`` when this run already called a web-read tool, else ``agent``."""
    return "web" if await run_read_web(ctx.deps.run_id) else "agent"


def _existing(rel: str) -> str | None:
    try:
        return memory.read(rel)
    except FileNotFoundError:
        return None


@hq_tool(action=ActionClass.VAULT_WRITE)
async def vault_write(ctx: RunContext[HQDeps], path: str, content: str) -> str:
    """Write a markdown note into the vault (committed with the day's other writes, nightly). Path must be inside
    this agent's write scope. Notes outside memory/ get frontmatter with
    created, author and provenance set by code; quarantine/ notes must carry a
    source_urls list. Rewrites of memory/ notes may not drop more than 30% of
    the existing lines; memory/rules.md is owner-only."""
    scopes = ctx.deps.vault_write_scopes
    try:
        rel = memory.normalize(path)
    except PermissionError as exc:
        raise ModelRetry(str(exc)) from None
    if not memory.in_scope(rel, scopes):
        # A retry hint, not a crash: the agent learns its scope and adapts.
        raise ModelRetry(
            f"refused: agent {ctx.deps.agent} may only write inside {scopes or ['(nothing)']}"
        )
    # A content draft is his voice or it is not written. Checked on what the
    # agent wrote, before frontmatter is stamped, the way publish_post checks
    # a post before it reaches his site.
    if voice.is_draft_path(rel):
        off = voice.register_problems(content)
        if off:
            raise ModelRetry(
                "this draft is not in his register: " + "; ".join(off)
                + ". Rewrite it the way he writes, then call vault_write again"
            )
    warnings: list[str] = []
    try:
        if not memory.is_memory_note(rel):
            meta, _body = memory.parse_frontmatter(content)
            problem = memory.quarantine_problem(rel, meta)
            if problem:
                raise ModelRetry(problem)
            content = memory.stamp_frontmatter(
                content, author=ctx.deps.agent, provenance=await _run_provenance(ctx),
            )
        if not memory.has_title(content):
            warnings.append("note has no '# ' title line")
        # Same gates as memory.write_sync, run early so the refusal reaches the
        # agent as a ModelRetry with the current file in hand.
        existing = await asyncio.to_thread(_existing, rel)
        content, dropped = memory.trim_to_cap(rel, content)
        if dropped:
            warnings.append(
                f"over its cap, so the {dropped} oldest line(s) were dropped; write the"
                " block shorter next time rather than relying on this"
            )
        problem = memory.write_problem(rel, content, actor=ctx.deps.agent, existing=existing)
        if problem:
            raise ModelRetry(problem)
        await memory.write(rel, content, actor=ctx.deps.agent)
    except memory.WriteRefused as exc:
        raise ModelRetry(str(exc)) from None
    if warnings:
        log.warning("vault_write %s by %s: %s", rel, ctx.deps.agent, "; ".join(warnings))
        return f"wrote {rel} (warning: {'; '.join(warnings)})"
    return f"wrote {rel}"


@hq_tool(action=ActionClass.READ, trust=Trust.VAULT)
async def load_skill(ctx: RunContext[HQDeps], name: str) -> str:
    """Load the full instructions of one of your skills by name (see the skills
    list in your instructions)."""
    if not name.replace("-", "").replace("_", "").isalnum():
        raise ValueError("skill name must be alnum/dash")
    path = settings().agents_dir / ctx.deps.agent / "skills" / name / "SKILL.md"
    if not path.exists():
        return f"no skill named {name!r}"
    return await asyncio.to_thread(path.read_text)
