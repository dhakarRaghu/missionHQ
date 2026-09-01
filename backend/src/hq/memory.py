"""Vault access: markdown files in a git repo, one commit per write.

All vault WRITES must go through the ``vault`` DBOS queue (engine enqueues
``vault_write_wf``) so git never sees two writers. Reads are direct.
``search()`` is a facade: grep now, Postgres FTS in phase 4, +pgvector later —
callers never change.
"""

from __future__ import annotations

import asyncio
import re
import subprocess
from pathlib import Path

from hq.config import settings

# Core memory blocks: hard size caps are the feature (Letta lesson).
BLOCK_CAPS = {"memory/user.md": 4000, "memory/active_projects.md": 6000, "memory/rules.md": 4000}


def _vault() -> Path:
    return settings().vault_dir


def _safe_path(rel_path: str) -> Path:
    p = (_vault() / rel_path).resolve()
    if not p.is_relative_to(_vault().resolve()):
        raise PermissionError(f"path escapes vault: {rel_path}")
    return p


def in_scope(rel_path: str, scopes: list[str]) -> bool:
    """Scoped writes: scope 'quarantine/**' admits only paths under quarantine/."""
    if "**" in scopes or not scopes:
        return not scopes or "**" in scopes
    for scope in scopes:
        prefix = scope.removesuffix("/**").removesuffix("/*")
        if rel_path == prefix or rel_path.startswith(prefix.rstrip("/") + "/"):
            return True
    return False


def read(rel_path: str) -> str:
    return _safe_path(rel_path).read_text()


def write_sync(rel_path: str, content: str, *, actor: str) -> str:
    """Blocking write + git commit. Call ONLY from the vault queue workflow."""
    cap = BLOCK_CAPS.get(rel_path)
    if cap is not None and len(content) > cap:
        raise ValueError(f"{rel_path} exceeds its {cap}-char memory-block cap")
    p = _safe_path(rel_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)
    subprocess.run(["git", "add", "-A"], cwd=_vault(), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", f"{actor}: {rel_path}", "--allow-empty"],
        cwd=_vault(), check=True, capture_output=True,
    )
    return rel_path


_write_lock = asyncio.Lock()


async def write(rel_path: str, content: str, *, actor: str) -> str:
    """Serialized vault write: one writer at a time, so git commits never race."""
    async with _write_lock:
        return await asyncio.to_thread(write_sync, rel_path, content, actor=actor)


def load_core_blocks() -> str:
    """Concatenated memory blocks injected into every agent's instructions."""
    parts = []
    for rel in BLOCK_CAPS:
        p = _vault() / rel
        if p.exists():
            parts.append(f"## {rel}\n{p.read_text()}")
    return "\n\n".join(parts)


async def search(query: str, *, limit: int = 8) -> list[dict]:
    """v1: ripgrep-style scan. Facade — phase 4 swaps the internals for FTS."""
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
            low = text.lower()
            score = sum(low.count(w) for w in words)
            if score > 0:
                snippet = text[:400]
                hits.append((score, str(p.relative_to(_vault())), snippet))
        hits.sort(reverse=True)
        return [{"path": path, "snippet": snip} for _, path, snip in hits[:limit]]

    return await asyncio.to_thread(_scan)
