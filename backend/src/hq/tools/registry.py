"""The @hq_tool decorator — the single choke point for agent capabilities.

Composes: DBOS step (durable + audited), registry entry, action class,
provenance trust, and the requires-approval flag surfaced via Pydantic AI's
DeferredToolRequests. Sandboxing later swaps the executor here (one seam).
"""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from hq.dbos_app import DBOS
from hq.safety import ActionClass, Trust

# Retry policy for steps that hit the network (models are auto-stepped by
# DBOSDurability with their own config; this is for tool I/O like web fetches).
NETWORK_RETRIES = {"retries_allowed": True, "max_attempts": 3, "interval_seconds": 2.0}


@dataclass
class HQDeps:
    """Per-run dependencies passed to every tool via RunContext."""
    agent: str
    task_id: str | None = None
    run_id: str | None = None
    vault_write_scopes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ToolDef:
    name: str
    fn: Callable[..., Any]
    action: ActionClass
    trust: Trust
    requires_approval: bool
    description: str


TOOL_REGISTRY: dict[str, ToolDef] = {}

# Tools that may NEVER be granted to an agent that also holds web-read tools.
OUTBOUND_ACTIONS = {ActionClass.EXTERNAL_WRITE, ActionClass.SPEND}
WEB_READ_TOOLS = {"web_fetch"}


def hq_tool(
    *,
    action: ActionClass,
    trust: Trust = Trust.TOOL,
    name: str | None = None,
    network: bool = False,
):
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        tool_name = name or fn.__name__
        if not inspect.iscoroutinefunction(fn):
            plain = fn

            async def fn_async(*args: Any, **kwargs: Any) -> Any:
                return await asyncio.to_thread(plain, *args, **kwargs)

            fn_async.__name__ = plain.__name__
            fn_async.__doc__ = plain.__doc__
            wrapped = fn_async
        else:
            wrapped = fn
        stepped = DBOS.step(name=f"tool.{tool_name}", **(NETWORK_RETRIES if network else {}))(wrapped)
        TOOL_REGISTRY[tool_name] = ToolDef(
            name=tool_name,
            fn=stepped,
            action=action,
            trust=trust,
            requires_approval=action in OUTBOUND_ACTIONS,
            description=(fn.__doc__ or "").strip().splitlines()[0] if fn.__doc__ else "",
        )
        return stepped

    return deco


def get_tools(names: list[str]) -> list[ToolDef]:
    missing = [n for n in names if n.split(":")[0] not in TOOL_REGISTRY]
    if missing:
        raise KeyError(f"unknown tools in allowlist: {missing}; known: {sorted(TOOL_REGISTRY)}")
    return [TOOL_REGISTRY[n.split(":")[0]] for n in names]
