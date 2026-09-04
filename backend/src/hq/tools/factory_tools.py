"""Agent factory: agents propose new agents, the owner approves and activates.

Data decides what an agent tries to do; code decides what is possible. The
validator in this module is the only path that turns a proposal into an
``agents/<name>/`` folder, and the same validator runs again at activation.

Flow:
1. The factory agent calls ``draft_agent`` (EXTERNAL_WRITE, so the owner sees
   the full spec as an approval ticket before anything is written).
2. The tool validates in code, then writes ``agents/<name>/job.md`` with
   ``status: draft`` and ``policy.md`` from ``backend/templates/policy-base.md``.
3. The owner runs ``/activate <name>`` (Telegram) or ``POST /api/agents/<name>/activate``.
   ``activate_agent`` re-validates and flips the status; the caller then
   schedules a process exit so launchd restarts the backend, because agents
   load only at startup (DBOSDurability agents are built before DBOS.launch()).
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path
from typing import Any

import yaml
from dbos._croniter import croniter  # type: ignore[attr-defined]
from pydantic_ai import RunContext

from hq.config import BACKEND_DIR, Caps, settings
from hq.safety import ActionClass, Trust
from hq.tools.registry import (
    OUTBOUND_ACTIONS,
    TOOL_REGISTRY,
    WEB_FORBIDDEN_TOOLS,
    HQDeps,
    hq_tool,
    web_read_tools,
)

log = logging.getLogger(__name__)

NAME_RE = re.compile(r"^[a-z][a-z0-9-]{2,20}$")
# One or more folder segments, e.g. "projects/foo". No leading slash, no "..".
SCOPE_FOLDER_RE = re.compile(r"^[a-z0-9_-]+(/[a-z0-9_-]+)*$")
MIN_CRON_INTERVAL = timedelta(hours=1)
CRON_SAMPLE_FIRES = 12  # consecutive fire times inspected for the minimum gap
# safety.GUARD_MAX_ARGS_CHARS is 8000 for the whole ticket; keep the prompt
# well under it so a draft ticket is never auto-denied by the guardrail.
MAX_PROMPT_CHARS = 6000
MAX_DESCRIPTION_CHARS = 200
POLICY_TEMPLATE = BACKEND_DIR / "templates" / "policy-base.md"
RESTART_DELAY_S = 2.0

# Probation ceiling. Every factory-made agent starts here; the owner raises the
# numbers by editing the caps block in agents/<name>/job.md.
FACTORY_CAPS = Caps(cost_per_run_usd=0.25, tool_calls=20, daily_usd=0.50)


@dataclass
class DraftSpec:
    """A validated proposal. Only ``validate_draft`` constructs one."""

    name: str
    description: str
    role_prompt: str
    tools: list[str]
    model: str
    cron: list[dict[str, str]] = field(default_factory=list)
    caps: Caps = field(default_factory=lambda: FACTORY_CAPS.model_copy())


# --- validator (pure code, no model, no I/O beyond reading models.yaml) --------

def protected_tools() -> set[str]:
    """Tools an agent may never grant to another agent: anything that acts
    outward or spends. Only the owner adds these, by editing job.md."""
    return {n for n, t in TOOL_REGISTRY.items() if t.action in OUTBOUND_ACTIONS}


def _check_name(name: str, *, existing_ok: bool) -> None:
    if not NAME_RE.match(name):
        raise ValueError(
            f"name {name!r} must match [a-z][a-z0-9-]{{2,20}} (lowercase, 3-21 chars)"
        )
    if not existing_ok and (settings().agents_dir / name).exists():
        raise ValueError(f"agents/{name} already exists")


def _check_tools(tools: list[str]) -> None:
    seen: set[str] = set()
    for entry in tools:
        base, _, scope = entry.partition(":")
        if base not in TOOL_REGISTRY:
            raise ValueError(
                f"unknown tool {base!r}; known: {sorted(TOOL_REGISTRY)}"
            )
        if base in seen:
            raise ValueError(f"tool {base!r} listed twice")
        seen.add(base)
        if base in protected_tools():
            raise ValueError(
                f"tool {base!r} is {TOOL_REGISTRY[base].action.value}; only the owner"
                " may grant it (edit job.md after activation)"
            )
        if base == "vault_write":
            if not scope or scope == "**":
                raise ValueError(
                    "vault_write must be scoped: use vault_write:<folder>/**"
                )
            folder = scope.removesuffix("/**")
            if folder == scope or not SCOPE_FOLDER_RE.match(folder):
                raise ValueError(
                    f"vault_write scope {scope!r} must look like <folder>/**"
                    " (lowercase folder path, no leading slash, no '..')"
                )
        elif scope:
            raise ValueError(f"tool {base!r} does not take a scope ({entry!r})")
    # Scoped-trifecta rule, the same one loader.validate_trifecta enforces.
    if seen & web_read_tools():
        forbidden = seen & WEB_FORBIDDEN_TOOLS
        if forbidden:
            raise ValueError(
                f"web-read tools cannot combine with {sorted(forbidden)}"
            )
        for entry in tools:
            base, _, scope = entry.partition(":")
            if base == "vault_write" and scope != "quarantine/**":
                raise ValueError(
                    "an agent with a web-read tool may only hold"
                    f" vault_write:quarantine/**, got {entry!r}"
                )


def _check_cron(schedule: str, prompt: str) -> list[dict[str, str]]:
    schedule = schedule.strip()
    prompt = prompt.strip()
    if not schedule and not prompt:
        return []
    if not schedule or not prompt:
        raise ValueError("cron_schedule and cron_prompt must be given together")
    if "\n" in schedule:
        raise ValueError("only one cron entry is allowed")
    base = datetime(2026, 1, 1, tzinfo=UTC)
    try:
        it = croniter(schedule, base)
        fires = [it.get_next(datetime) for _ in range(CRON_SAMPLE_FIRES)]
    except Exception as exc:  # noqa: BLE001 — croniter raises its own hierarchy
        raise ValueError(f"cron_schedule {schedule!r} is not a valid cron line: {exc}") from None
    gaps = [b - a for a, b in pairwise(fires)]
    if gaps and min(gaps) < MIN_CRON_INTERVAL:
        raise ValueError(
            f"cron_schedule {schedule!r} fires every {int(min(gaps).total_seconds() // 60)} min;"
            " the minimum interval is 1 hour"
        )
    return [{"schedule": schedule, "prompt": prompt}]


def _check_model(model: str) -> str:
    from hq import llm  # late import: llm reads models.yaml and settings

    try:
        llm.registry().canonical(model)
    except KeyError as exc:
        raise ValueError(str(exc)) from None
    return model


def validate_draft(
    *,
    name: str,
    description: str,
    role_prompt: str,
    tools: list[str],
    cron_schedule: str = "",
    cron_prompt: str = "",
    model: str = "default",
    existing_ok: bool = False,
) -> DraftSpec:
    """Return a DraftSpec or raise ValueError with a reason the owner can read.

    ``existing_ok=True`` is for activation, where the folder already exists.
    Rules: name shape and uniqueness; every tool registered; no EXTERNAL_WRITE
    or SPEND tool; vault_write always scoped; web-read only with
    quarantine/**; at most one cron entry, valid, at least 1 hour apart; model
    known to the registry; caps fixed to FACTORY_CAPS.
    """
    _check_name(name, existing_ok=existing_ok)
    description = " ".join(description.split())
    if not description:
        raise ValueError("description is required")
    if len(description) > MAX_DESCRIPTION_CHARS:
        raise ValueError(f"description is over {MAX_DESCRIPTION_CHARS} chars")
    role_prompt = role_prompt.strip()
    if not role_prompt:
        raise ValueError("role_prompt is required")
    if len(role_prompt) > MAX_PROMPT_CHARS:
        raise ValueError(f"role_prompt is {len(role_prompt)} chars; limit {MAX_PROMPT_CHARS}")
    if not isinstance(tools, list) or not all(isinstance(t, str) for t in tools):
        raise ValueError("tools must be a list of tool names")
    tools = [t.strip() for t in tools if t.strip()]
    _check_tools(tools)
    cron = _check_cron(cron_schedule, cron_prompt)
    model = _check_model(model.strip() or "default")
    return DraftSpec(
        name=name, description=description, role_prompt=role_prompt,
        tools=tools, model=model, cron=cron,
    )


# --- files ---------------------------------------------------------------------

def render_job_md(spec: DraftSpec, *, status: str = "draft") -> str:
    meta: dict[str, Any] = {
        "name": spec.name,
        "description": spec.description,
        "status": status,
        "model": spec.model,
        "tools": list(spec.tools),
        "caps": spec.caps.model_dump(),
        "cron": spec.cron,
    }
    fm = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True, width=100)
    if "---" in fm:
        raise ValueError("frontmatter would contain '---'; remove it from the text fields")
    return f"---\n{fm}---\n{spec.role_prompt}\n"


def _write_draft(spec: DraftSpec) -> Path:
    folder = settings().agents_dir / spec.name
    if folder.exists():
        raise ValueError(f"agents/{spec.name} already exists")
    policy = POLICY_TEMPLATE.read_text()
    folder.mkdir(parents=True)
    (folder / "job.md").write_text(render_job_md(spec))
    (folder / "policy.md").write_text(policy)
    return folder


def _read_frontmatter(agent_dir: Path) -> tuple[dict[str, Any], str] | None:
    job = agent_dir / "job.md"
    if not job.exists():
        return None
    text = job.read_text()
    if not text.startswith("---"):
        return None
    try:
        _, fm, body = text.split("---", 2)
        meta = yaml.safe_load(fm)
    except (ValueError, yaml.YAMLError):
        return None
    return (meta, body.strip()) if isinstance(meta, dict) else None


def list_drafts() -> list[dict[str, Any]]:
    """Every agents/<name>/ folder whose job.md says ``status: draft``."""
    out: list[dict[str, Any]] = []
    root = settings().agents_dir
    for agent_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        parsed = _read_frontmatter(agent_dir)
        if parsed is None or parsed[0].get("status") != "draft":
            continue
        meta = parsed[0]
        out.append({
            "name": agent_dir.name,
            "description": meta.get("description", ""),
            "model": meta.get("model", "default"),
            "tools": meta.get("tools", []),
            "cron": meta.get("cron", []),
            "caps": meta.get("caps", {}),
        })
    return out


def activate_agent(name: str) -> str:
    """Flip agents/<name>/job.md from draft to active after re-validation.

    Raises ValueError (bad name / not a draft / validation failed) and
    FileNotFoundError (no such draft). Blocking file I/O: call it via
    asyncio.to_thread from async code. The caller schedules the restart.
    """
    if not NAME_RE.match(name):
        raise ValueError(f"bad agent name {name!r}")
    agent_dir = settings().agents_dir / name
    if not (agent_dir / "job.md").exists():
        raise FileNotFoundError(f"no agents/{name}/job.md")
    parsed = _read_frontmatter(agent_dir)
    if parsed is None:
        raise ValueError(f"agents/{name}/job.md has no readable frontmatter")
    meta, body = parsed
    if meta.get("status") != "draft":
        raise ValueError(f"agents/{name} is not a draft (status: {meta.get('status')!r})")
    if meta.get("name") != name:
        raise ValueError(f"agents/{name}/job.md names {meta.get('name')!r}")
    cron = meta.get("cron") or []
    if len(cron) > 1:
        raise ValueError("only one cron entry is allowed")
    entry = cron[0] if cron else {}
    validate_draft(
        name=name,
        description=str(meta.get("description", "")),
        role_prompt=body,
        tools=list(meta.get("tools") or []),
        cron_schedule=str(entry.get("schedule", "")),
        cron_prompt=str(entry.get("prompt", "")),
        model=str(meta.get("model", "default")),
        existing_ok=True,
    )
    job = agent_dir / "job.md"
    text = job.read_text()
    fm_end = text.index("---", 3)
    fm, tail = text[:fm_end], text[fm_end:]
    new_fm, n = re.subn(r"(?m)^status:\s*draft\s*$", "status: active", fm, count=1)
    if n != 1:
        raise ValueError(f"could not find 'status: draft' line in agents/{name}/job.md")
    tmp = job.with_suffix(".md.tmp")
    tmp.write_text(new_fm + tail)
    os.replace(tmp, job)
    caps = meta.get("caps") or {}
    return (
        f"activated agents/{name}. The backend restarts in {int(RESTART_DELAY_S)} s so the"
        " agent loads (launchd brings it back).\n"
        f"Probation caps stay at cost_per_run_usd={caps.get('cost_per_run_usd')},"
        f" tool_calls={caps.get('tool_calls')}, daily_usd={caps.get('daily_usd')};"
        f" edit the caps block in agents/{name}/job.md to raise them."
    )


def schedule_restart(delay: float = RESTART_DELAY_S) -> None:
    """Exit the process after ``delay`` seconds so launchd (KeepAlive) restarts
    it and the new agent loads. The reply must already be on its way."""
    log.warning("restart scheduled in %.0fs: agent activation needs a fresh process", delay)
    asyncio.get_running_loop().call_later(delay, os._exit, 0)


def registry_catalog() -> list[dict[str, str]]:
    """Name, action, trust and one-line description of every registered tool.
    For prompt authors: the factory job.md carries this list as static text."""
    return [
        {
            "name": n, "action": t.action.value, "trust": t.trust.value,
            "grantable": "no" if t.action in OUTBOUND_ACTIONS else "yes",
            "description": t.description,
        }
        for n, t in sorted(TOOL_REGISTRY.items())
    ]


# --- tools ----------------------------------------------------------------------

def _format_check(spec: DraftSpec) -> str:
    cron = f"{spec.cron[0]['schedule']!r}" if spec.cron else "none"
    return (
        f"ok: name={spec.name} model={spec.model} tools={spec.tools} cron={cron}"
        f" caps={spec.caps.model_dump()}"
    )


@hq_tool(action=ActionClass.READ, trust=Trust.TOOL)
async def validate_agent_draft(
    ctx: RunContext[HQDeps],
    name: str,
    description: str,
    role_prompt: str,
    tools: list[str],
    cron_schedule: str = "",
    cron_prompt: str = "",
    model: str = "default",
) -> str:
    """Check a proposed agent spec against the factory rules without writing anything.
    Call this before draft_agent with the same arguments; fix every 'rejected' reason first."""
    try:
        spec = await asyncio.to_thread(
            lambda: validate_draft(
                name=name, description=description, role_prompt=role_prompt, tools=tools,
                cron_schedule=cron_schedule, cron_prompt=cron_prompt, model=model,
            )
        )
    except ValueError as exc:
        return f"rejected: {exc}"
    return _format_check(spec)


@hq_tool(action=ActionClass.EXTERNAL_WRITE, trust=Trust.TOOL)
async def draft_agent(
    ctx: RunContext[HQDeps],
    name: str,
    description: str,
    role_prompt: str,
    tools: list[str],
    cron_schedule: str = "",
    cron_prompt: str = "",
    model: str = "default",
) -> str:
    """Propose a new agent. The owner reviews the full spec as an approval ticket;
    on approval this writes agents/<name>/job.md (status: draft) and policy.md.
    Rules enforced in code: 3-21 char lowercase name; only registered tools; no
    tool that acts outward or spends; vault_write always scoped to <folder>/**;
    a web-read tool only with vault_write:quarantine/**; at most one cron entry,
    at least 1 hour apart; caps fixed to the factory ceiling."""
    try:
        spec = await asyncio.to_thread(
            lambda: validate_draft(
                name=name, description=description, role_prompt=role_prompt, tools=tools,
                cron_schedule=cron_schedule, cron_prompt=cron_prompt, model=model,
            )
        )
        folder = await asyncio.to_thread(_write_draft, spec)
    except ValueError as exc:
        return f"rejected: {exc}"
    log.info("agent %s drafted agents/%s", ctx.deps.agent, folder.name)
    return (
        f"drafted agents/{spec.name} (status: draft) — the owner activates it with"
        f" /activate {spec.name}"
    )


@hq_tool(action=ActionClass.READ, trust=Trust.TOOL)
async def list_agent_drafts(ctx: RunContext[HQDeps]) -> list[dict]:
    """List agent folders whose job.md has status: draft (name, description, tools, cron)."""
    return await asyncio.to_thread(list_drafts)
