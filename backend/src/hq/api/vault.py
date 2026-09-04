"""Vault endpoints for the console: the folder tree, one note with its git
history, hybrid search, and one owner edit. Every client-supplied path goes
through ``memory.normalize`` and is refused outside the vault. ``.git`` is
never listed or served. Writing still goes through ``memory.write``, which
stays the only writer, so an owner edit gets the same gates and the same one
commit per write as an agent's."""

from __future__ import annotations

import asyncio
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from hq import engagement, memory
from hq.api.deps import require_auth
from hq.config import settings

router = APIRouter(prefix="/vault", dependencies=[Depends(require_auth)])

SKIP_DIRS = {".git"}
GIT_LOG_COMMITS = 5
GIT_TIMEOUT_S = 10
SEARCH_LIMIT_MAX = 50
GIT_HASH_RE = re.compile(r"^[0-9a-f]{7,40}$")
DIFF_MAX_CHARS = 200_000


def _root() -> Path:
    return settings().vault_dir.resolve()


def _iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=UTC).isoformat()


def _walk(directory: Path, root: Path) -> dict[str, Any]:
    """One folder node: folders first, then files, each group sorted by name.
    ``file_count`` is recursive so the tree can show it on collapsed folders."""
    folders: list[dict[str, Any]] = []
    files: list[dict[str, Any]] = []
    try:
        entries = sorted(directory.iterdir(), key=lambda p: p.name.lower())
    except OSError:
        entries = []
    for entry in entries:
        if entry.name in SKIP_DIRS:
            continue
        if entry.is_dir():
            folders.append(_walk(entry, root))
        elif entry.is_file():
            st = entry.stat()
            files.append({
                "name": entry.name,
                "path": entry.relative_to(root).as_posix(),
                "kind": "file",
                "size": st.st_size,
                "mtime": _iso(st.st_mtime),
            })
    rel_dir = "" if directory == root else directory.relative_to(root).as_posix()
    return {
        "name": directory.name if rel_dir else "",
        "path": rel_dir,
        "kind": "folder",
        "mtime": _iso(directory.stat().st_mtime),
        "file_count": len(files) + sum(f["file_count"] for f in folders),
        "children": folders + files,
    }


@router.get("/tree", operation_id="getVaultTree")
async def get_vault_tree() -> dict:
    """Nested folders and files (sizes, mtimes) plus the memory-block fill levels."""
    root = _root()
    if not root.is_dir():
        raise HTTPException(404, "vault directory does not exist")
    tree, blocks = await asyncio.gather(
        asyncio.to_thread(_walk, root, root),
        asyncio.to_thread(_blocks_with_commits),
    )
    return {"root": tree, "blocks": blocks}


def _blocks_with_commits() -> list[dict[str, Any]]:
    """memory.block_status() plus ``last_commit`` (newest commit touching the
    block, or None). The commit subject starts with the actor, e.g.
    ``librarian: memory/user.md``, so the console can show who wrote last."""
    out = []
    for block in memory.block_status():
        log = _git_log(block["path"], limit=1)
        out.append({**block, "last_commit": log[0] if log else None})
    return out


def _validated(path: str) -> str:
    """Canonical vault-relative path, or 403 for anything outside the vault."""
    try:
        rel = memory.normalize(path)
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from None
    if rel in {"", "."} or SKIP_DIRS & set(PurePosixPath(rel).parts):
        raise HTTPException(403, f"invalid vault path: {path}")
    return rel


def _git_log(rel: str, limit: int = GIT_LOG_COMMITS) -> list[dict[str, str]]:
    """Last commits touching ``rel``: ``{hash, ts, message}``. A vault that
    is not a git repo, or a file with no history, yields an empty list."""
    try:
        proc = subprocess.run(
            ["git", "log", f"-{limit}", "--format=%h|%aI|%s", "--", rel],
            cwd=_root(), capture_output=True, text=True, check=False, timeout=GIT_TIMEOUT_S,
        )
    except (OSError, subprocess.TimeoutExpired):
        return []
    if proc.returncode != 0:
        return []
    out: list[dict[str, str]] = []
    for line in proc.stdout.splitlines():
        parts = line.split("|", 2)
        if len(parts) == 3:
            out.append({"hash": parts[0], "ts": parts[1], "message": parts[2]})
    return out


def _read_note(rel: str) -> dict[str, Any]:
    p = _root() / rel
    if not p.is_file():
        raise FileNotFoundError(rel)
    st = p.stat()
    return {
        "path": rel,
        "content": memory.read(rel),
        "size": st.st_size,
        "mtime": _iso(st.st_mtime),
    }


@router.get("/note", operation_id="getVaultNote")
async def get_vault_note(path: Annotated[str, Query(min_length=1)]) -> dict:
    """One note's text, size, mtime and its last commits."""
    rel = _validated(path)
    try:
        note, git = await asyncio.gather(
            asyncio.to_thread(_read_note, rel),
            asyncio.to_thread(_git_log, rel),
        )
    except FileNotFoundError:
        raise HTTPException(404, f"no such note: {rel}") from None
    except UnicodeDecodeError:
        raise HTTPException(415, f"{rel} is not a text file") from None
    return {**note, "git": git}


def _git_show(commit: str, rel: str) -> str:
    """Unified diff of one commit limited to ``rel`` (``git show --format=``).
    Raises FileNotFoundError when git rejects the hash."""
    proc = subprocess.run(
        ["git", "show", "--format=", "--no-color", commit, "--", rel],
        cwd=_root(), capture_output=True, text=True, check=False, timeout=GIT_TIMEOUT_S,
    )
    if proc.returncode != 0:
        raise FileNotFoundError(proc.stderr.strip()[:200] or commit)
    text = proc.stdout
    if len(text) > DIFF_MAX_CHARS:
        text = text[:DIFF_MAX_CHARS] + "\n... (diff truncated)\n"
    return text


class NoteBody(BaseModel):
    """New full content for one note. Empty is allowed: a memory block the
    owner clears is a deliberate reset, not a mistake."""

    content: str = Field(max_length=200_000)


@router.put("/note", operation_id="putVaultNote")
async def put_vault_note(
    path: Annotated[str, Query(min_length=1)], body: NoteBody
) -> dict:
    """Save one note as the owner.

    The owner may rewrite anything, including the rules block agents cannot
    touch and a consolidation that drops most of a file. The one gate that
    still applies is a memory block's size cap, because the cap is what keeps
    the block readable inside every agent's prompt.
    """
    rel = _validated(path)
    if not rel.lower().endswith(".md"):
        raise HTTPException(400, "only markdown notes can be edited here")
    try:
        await memory.write(rel, body.content, actor="owner")
    except memory.WriteRefused as exc:
        raise HTTPException(422, str(exc)) from exc
    await engagement.record_owner_action("web", "vault_edit")
    return _read_note(rel)


@router.get("/note/diff", operation_id="getVaultNoteDiff")
async def get_vault_note_diff(
    path: Annotated[str, Query(min_length=1)],
    hash: Annotated[str, Query(min_length=7, max_length=40)],
) -> dict:
    """What one commit changed in one note, as a unified diff. The hash must be
    7 to 40 hex chars; the path is validated like every other vault path."""
    rel = _validated(path)
    commit = hash.strip().lower()
    if not GIT_HASH_RE.fullmatch(commit):
        raise HTTPException(422, "hash must be 7 to 40 hex characters")
    try:
        diff = await asyncio.to_thread(_git_show, commit, rel)
    except FileNotFoundError as exc:
        raise HTTPException(404, f"no such commit for {rel}: {exc}") from None
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HTTPException(503, f"git unavailable: {exc}") from None
    return {"path": rel, "hash": commit, "diff": diff}


@router.get("/search", operation_id="searchVault")
async def search_vault(q: Annotated[str, Query(min_length=1)], limit: int = 10) -> list[dict]:
    """Hybrid FTS + vector search, one best chunk per note. Snippets mark
    matches with ``**``; the console renders them as bold."""
    query = q.strip()
    if not query:
        raise HTTPException(422, "q must not be blank")
    return await memory.search(query, limit=max(1, min(limit, SEARCH_LIMIT_MAX)))
