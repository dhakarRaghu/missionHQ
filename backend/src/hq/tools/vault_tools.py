"""Vault tools. Writes honor per-agent scopes (the scoped-trifecta rule)."""

from __future__ import annotations

from pydantic_ai import RunContext

from hq import memory
from hq.safety import ActionClass, Trust
from hq.tools.registry import HQDeps, hq_tool


@hq_tool(action=ActionClass.READ, trust=Trust.VAULT)
async def vault_read(ctx: RunContext[HQDeps], path: str) -> str:
    """Read a markdown note from the vault by relative path."""
    return memory.read(path)


@hq_tool(action=ActionClass.READ, trust=Trust.VAULT)
async def memory_search(ctx: RunContext[HQDeps], query: str) -> list[dict]:
    """Search the vault; returns matching paths with snippets."""
    return await memory.search(query)


@hq_tool(action=ActionClass.VAULT_WRITE)
async def vault_write(ctx: RunContext[HQDeps], path: str, content: str) -> str:
    """Write a markdown note into the vault (git-committed). Path must be inside
    this agent's write scope."""
    scopes = ctx.deps.vault_write_scopes
    if not memory.in_scope(path, scopes):
        raise PermissionError(
            f"agent {ctx.deps.agent} may only write inside {scopes or ['(nothing)']}"
        )
    await memory.write(path, content, actor=ctx.deps.agent)
    return f"wrote {path}"
