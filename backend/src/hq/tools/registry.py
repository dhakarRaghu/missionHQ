"""The @hq_tool decorator — the single choke point for agent capabilities.

Composes: DBOS step (durable + audited), registry entry, action class,
provenance trust, and the requires-approval flag surfaced via Pydantic AI's
DeferredToolRequests. Sandboxing later swaps the executor here (one seam).
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from hq.dbos_app import DBOS
from hq.safety import ActionClass, Trust

log = logging.getLogger(__name__)

# Audit event written once per tool call (see ``_audited``).
TOOL_EVENT_KIND = "tool.called"
ARG_CHARS = 120     # each argument value is truncated to this many chars
ERROR_CHARS = 200
RESULT_CHARS = 400  # the tool result is truncated to this many chars

# Retry policy for steps that hit the network (models are auto-stepped by
# DBOSDurability with their own config; this is for tool I/O like web fetches).
NETWORK_RETRIES: dict[str, Any] = {
    "retries_allowed": True, "max_attempts": 3, "interval_seconds": 2.0,
}


@dataclass
class HQDeps:
    """Per-run dependencies passed to every tool via RunContext."""
    agent: str
    task_id: str | None = None
    run_id: str | None = None
    # Set only for work originating in an owner chat. Delegated tasks carry it
    # forward so their final result can return to that same conversation.
    session_id: str | None = None
    vault_write_scopes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class ToolDef:
    name: str
    fn: Callable[..., Any]
    action: ActionClass
    trust: Trust
    requires_approval: bool
    # True when only the owner may answer the ticket. False lets the guard
    # resolve it without waking him, for an action whose whole effect stays
    # inside Mission HQ and is reversible.
    owner_only: bool
    # True when the effect leaves Mission HQ and reaches other people. No
    # agent may hold one of these at all: the owner decided that agents read
    # and draft, and he acts. Enforced at load, not by an approval prompt.
    world_facing: bool
    description: str


TOOL_REGISTRY: dict[str, ToolDef] = {}

# Tools that may NEVER be granted to an agent that also holds web-read tools.
OUTBOUND_ACTIONS = {ActionClass.EXTERNAL_WRITE, ActionClass.SPEND}
# Also barred for web-read agents: they reach the owner or other agents
# directly, so one poisoned page could otherwise fan out.
WEB_FORBIDDEN_TOOLS = {"create_subtask", "notify_owner"}


def web_read_tools() -> set[str]:
    """Registered tools whose results carry web provenance."""
    return {n for n, t in TOOL_REGISTRY.items() if t.trust == Trust.WEB}


def _truncate(value: Any, limit: int) -> Any:
    """Bounded, JSON-safe rendering of one tool argument."""
    text = value if isinstance(value, str) else repr(value)
    return text if len(text) <= limit else text[:limit] + "..."


def _render_result(value: Any) -> str:
    """Bounded text of a tool result: JSON for dicts/lists, str() otherwise."""
    if isinstance(value, (dict, list)):
        try:
            text = json.dumps(value, default=str)
        except (TypeError, ValueError):
            text = repr(value)
    else:
        text = str(value)
    return text if len(text) <= RESULT_CHARS else text[:RESULT_CHARS] + "..."


def _run_context(args: tuple[Any, ...]) -> Any:
    """Every tool takes RunContext[HQDeps] as its first positional argument."""
    deps = getattr(args[0], "deps", None) if args else None
    return deps if isinstance(deps, HQDeps) else None


def _audited(tool_name: str, fn: Callable[..., Any]) -> Callable[..., Any]:
    """Emit one ``tool.called`` hq.events row per call. Logging must never
    break the tool: emit failures are swallowed and the tool result (or its
    exception) is always passed through unchanged."""

    @functools.wraps(fn)
    async def audited(*args: Any, **kwargs: Any) -> Any:
        started = time.monotonic()
        ok = True
        error: str | None = None
        result: Any = None
        try:
            result = await fn(*args, **kwargs)
            return result
        except BaseException as exc:
            ok = False
            error = str(exc)[:ERROR_CHARS] or type(exc).__name__
            raise
        finally:
            duration_ms = int((time.monotonic() - started) * 1000)
            try:
                from hq.obs import (
                    emit,  # late import: obs -> db, keep module load light
                )

                deps = _run_context(args)
                arg_names = [n for n in inspect.signature(fn).parameters][1:]
                shown: dict[str, Any] = {
                    n: _truncate(v, ARG_CHARS)
                    for n, v in zip(arg_names, args[1:], strict=False)
                }
                shown.update({k: _truncate(v, ARG_CHARS) for k, v in kwargs.items()})
                payload: dict[str, Any] = {
                    "tool": tool_name, "args": shown,
                    "duration_ms": duration_ms, "ok": ok,
                }
                if error is not None:
                    payload["error"] = error
                else:
                    payload["result"] = _render_result(result)
                await emit(
                    TOOL_EVENT_KIND,
                    run_id=deps.run_id if deps else None,
                    task_id=deps.task_id if deps else None,
                    agent=deps.agent if deps else None,
                    payload=payload,
                )
            except Exception as exc:  # noqa: BLE001 — audit failure must not break the tool
                log.warning("tool.called emit failed for %s: %s", tool_name, exc)

    return audited


def hq_tool(
    *,
    action: ActionClass,
    trust: Trust = Trust.TOOL,
    name: str | None = None,
    network: bool = False,
    owner_only: bool = True,
    world_facing: bool = False,
):
    """Register one tool.

    ``owner_only`` defaults to True and should stay that way for anything the
    owner would want to see before it happens. Setting it False says: this
    action is contained, reversible, and the coordinator can decide. It is a
    promise about consequences, not about how often the tool is used.

    ``world_facing`` is stronger: it means the effect reaches other people.
    No agent may be granted such a tool, with or without approval. The owner
    is the only one who acts outward; the agents read, draft, and tell him
    what he can do.
    """
    def deco(fn: Callable[..., Any]) -> Callable[..., Any]:
        tool_name = name or fn.__name__
        wrapped: Callable[..., Any]
        if not inspect.iscoroutinefunction(fn):
            plain = fn

            @functools.wraps(plain)
            async def fn_async(*args: Any, **kwargs: Any) -> Any:
                return await asyncio.to_thread(plain, *args, **kwargs)

            wrapped = fn_async
        else:
            wrapped = fn
        stepped = DBOS.step(name=f"tool.{tool_name}", **(NETWORK_RETRIES if network else {}))(
            _audited(tool_name, wrapped)
        )
        TOOL_REGISTRY[tool_name] = ToolDef(
            name=tool_name,
            fn=stepped,
            action=action,
            trust=trust,
            requires_approval=action in OUTBOUND_ACTIONS,
            owner_only=owner_only,
            world_facing=world_facing,
            description=(fn.__doc__ or "").strip().splitlines()[0] if fn.__doc__ else "",
        )
        return stepped

    return deco


def get_tools(names: list[str]) -> list[ToolDef]:
    missing = [n for n in names if n.split(":")[0] not in TOOL_REGISTRY]
    if missing:
        raise KeyError(f"unknown tools in allowlist: {missing}; known: {sorted(TOOL_REGISTRY)}")
    return [TOOL_REGISTRY[n.split(":")[0]] for n in names]
