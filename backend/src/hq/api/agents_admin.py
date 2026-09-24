"""Owner-side agent configuration editor: read, validate, save and apply
``agents/<name>/job.md`` and ``policy.md`` from the console.

Agents load only at startup (DBOSDurability agents are built before
DBOS.launch()), so a saved job.md takes effect after a restart. Saving never
restarts by itself; ``POST /agents/{name}/apply`` schedules the restart the
same way activation does (``factory_tools.schedule_restart``). A policy.md
edit needs no restart: the assembler (``hq.assemble``) re-reads it on every run.

Validation runs the SAME code the loader runs at boot (``parse_job_md``,
``get_tools``, ``validate_trifecta``) against a temporary copy of the folder,
plus the factory checks for cron and caps. The real folder is written only
after validation passes, atomically (tmp + rename).
"""

from __future__ import annotations

import asyncio
import difflib
import os
import subprocess
import tempfile
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any, Literal

import yaml
from dbos._croniter import croniter  # type: ignore[attr-defined]
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from hq import loader
from hq.api.deps import require_auth
from hq.config import Caps, settings
from hq.tools import factory_tools
from hq.tools.registry import OUTBOUND_ACTIONS, TOOL_REGISTRY

router = APIRouter(prefix="/agents", dependencies=[Depends(require_auth)])

GIT_LOG_COMMITS = 5
GIT_TIMEOUT_S = 10
JOB_FILE = "job.md"
POLICY_FILE = "policy.md"

# One writer at a time: two console tabs saving the same agent must not
# interleave their tmp + rename steps.
_write_lock = asyncio.Lock()


class CronBody(BaseModel):
    schedule: str = ""
    prompt: str = ""


class AgentConfigBody(BaseModel):
    """Editable part of job.md. ``name`` is never accepted: the folder name is
    the identity and the manifest must match it."""

    description: str = ""
    model: str = "default"
    tools: list[str] = Field(default_factory=list)
    caps: Caps = Field(default_factory=lambda: settings().default_caps.model_copy())
    cron: list[CronBody] = Field(default_factory=list)
    role_prompt: str = ""
    status: Literal["active", "paused", "draft"] = "active"
    # Only PUT config uses it: None = leave policy.md untouched.
    policy: str | None = None


class PolicyBody(BaseModel):
    policy: str


# --- helpers ------------------------------------------------------------------

def _agent_dir(name: str) -> Path:
    """The real folder, or 400/404. Only the name shape and existence are
    checked here; the factory and running agents are all editable."""
    if not factory_tools.NAME_RE.match(name):
        raise HTTPException(400, f"bad agent name {name!r}: expected [a-z][a-z0-9-]{{2,20}}")
    agent_dir = settings().agents_dir / name
    if not (agent_dir / JOB_FILE).is_file():
        raise HTTPException(404, f"no agents/{name}/{JOB_FILE}")
    return agent_dir


def _read_text(path: Path) -> str:
    return path.read_text() if path.is_file() else ""


def _split_job_md(text: str) -> tuple[dict[str, Any], str]:
    """Frontmatter dict and body, with the loader's split rule. Raises
    ValueError when the file has no readable frontmatter."""
    if not text.startswith("---"):
        raise ValueError("job.md missing frontmatter")
    _, fm, body = text.split("---", 2)
    meta = yaml.safe_load(fm)
    if not isinstance(meta, dict):
        raise TypeError("job.md frontmatter is not a mapping")
    return meta, body.strip()


class _Dumper(yaml.SafeDumper):
    """Indent list items under their key (``tools:\n  - x``), the way the
    hand-written manifests do, so a save does not re-indent every list."""

    def increase_indent(self, flow: bool = False, indentless: bool = False) -> None:
        super().increase_indent(flow, False)


def _render_job_md(name: str, body: AgentConfigBody) -> str:
    """The job.md text for a config. Key order is fixed so a saved file keeps
    the shape of the hand-written ones (name first, role prompt as the body).
    No line wrapping: one value per line keeps diffs small."""
    meta: dict[str, Any] = {
        "name": name,
        "description": " ".join(body.description.split()),
        "status": body.status,
        "model": body.model.strip() or "default",
        "tools": [t.strip() for t in body.tools if t.strip()],
        "caps": body.caps.model_dump(),
        "cron": [
            {"schedule": c.schedule.strip(), "prompt": c.prompt.strip()}
            for c in body.cron
            if c.schedule.strip() or c.prompt.strip()
        ],
    }
    fm = yaml.dump(
        meta, Dumper=_Dumper, sort_keys=False, allow_unicode=True, width=float("inf"),
    )
    if "---" in fm:
        raise ValueError("frontmatter would contain '---'; remove it from the text fields")
    return f"---\n{fm}---\n{body.role_prompt.strip()}\n"


def _same_job(old_text: str, new_text: str) -> bool:
    """True when both files parse to the same frontmatter and body. Quoting,
    indentation and ``0.50`` vs ``0.5`` do not count as a change."""
    try:
        return _split_job_md(old_text) == _split_job_md(new_text)
    except (ValueError, TypeError, yaml.YAMLError):
        return False


def _msg(exc: BaseException) -> str:
    """KeyError repr-quotes its message; strip that for the owner."""
    return str(exc).strip("'\"")


def _diff(old: str, new: str, rel: str) -> str:
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True), new.splitlines(keepends=True),
            fromfile=f"a/{rel}", tofile=f"b/{rel}",
        )
    )


def _git_log(name: str) -> list[dict[str, str]]:
    """Last commits touching agents/<name>: ``{hash, ts, message}``. An
    uncommitted folder, or no git at all, yields an empty list."""
    root = settings().agents_dir
    try:
        proc = subprocess.run(
            ["git", "log", f"-{GIT_LOG_COMMITS}", "--format=%h|%aI|%s", "--", str(root / name)],
            cwd=root.parent, capture_output=True, text=True, check=False, timeout=GIT_TIMEOUT_S,
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


def _vault_write_scopes(tools: list[str]) -> list[str]:
    scopes: list[str] = []
    for t in tools:
        base, _, scope = t.partition(":")
        if base == "vault_write":
            scopes.append(scope or "**")
    return scopes


def _check_cron(entries: list[CronBody], errors: list[str]) -> None:
    """Every entry parses and fires at least MIN_CRON_INTERVAL apart. The
    loader accepts any number of entries; only the factory limits drafts to one."""
    base = datetime(2026, 1, 1, tzinfo=UTC)
    for i, entry in enumerate(entries, start=1):
        schedule, prompt = entry.schedule.strip(), entry.prompt.strip()
        if not schedule and not prompt:
            continue  # blank row, dropped at render time
        if not schedule or not prompt:
            errors.append(f"cron #{i}: schedule and prompt must be given together")
            continue
        try:
            it = croniter(schedule, base)
            fires = [it.get_next(datetime) for _ in range(factory_tools.CRON_SAMPLE_FIRES)]
        except Exception as exc:  # noqa: BLE001 — croniter raises its own hierarchy
            errors.append(f"cron #{i}: {schedule!r} is not a valid cron line: {exc}")
            continue
        gaps = [b - a for a, b in pairwise(fires)]
        if gaps and min(gaps) < factory_tools.MIN_CRON_INTERVAL:
            minutes = int(min(gaps).total_seconds() // 60)
            errors.append(
                f"cron #{i}: {schedule!r} fires every {minutes} min; the minimum interval is 1 hour"
            )


def _check_caps(caps: Caps, errors: list[str], warnings: list[str]) -> None:
    if caps.cost_per_run_usd <= 0:
        errors.append("caps.cost_per_run_usd must be > 0")
    if caps.tool_calls <= 0:
        errors.append("caps.tool_calls must be > 0")
    if caps.daily_usd <= 0:
        errors.append("caps.daily_usd must be > 0")
    global_cap = settings().daily_spend_cap_usd
    if caps.daily_usd > global_cap:
        errors.append(
            f"caps.daily_usd {caps.daily_usd} is over the global DAILY_SPEND_CAP_USD {global_cap}"
        )
    if 0 < caps.daily_usd < caps.cost_per_run_usd:
        warnings.append(
            "caps.cost_per_run_usd is above caps.daily_usd: one run can use the whole daily cap"
        )


def _check_tools_soft(tools: list[str], warnings: list[str]) -> None:
    """Things the loader allows but the owner should see."""
    seen: set[str] = set()
    for entry in tools:
        base, _, scope = entry.partition(":")
        if base in seen:
            warnings.append(f"tool {base!r} is listed more than once")
        seen.add(base)
        if base == "vault_write" and (not scope or scope == "**"):
            warnings.append(
                "vault_write has no scope: the agent may write anywhere in the vault"
            )
        elif base != "vault_write" and scope:
            warnings.append(f"tool {base!r} does not take a scope; {entry!r} is treated as {base!r}")
        if base in TOOL_REGISTRY and TOOL_REGISTRY[base].action in OUTBOUND_ACTIONS:
            warnings.append(
                f"tool {base!r} is {TOOL_REGISTRY[base].action.value}: every call opens an"
                " approval ticket"
            )


def _validate(name: str, body: AgentConfigBody, agent_dir: Path) -> dict[str, Any]:
    """Blocking. Runs the loader against a temp copy of the folder, then the
    factory-style cron/caps checks. Never touches ``agent_dir``."""
    errors: list[str] = []
    warnings: list[str] = []
    current_job = _read_text(agent_dir / JOB_FILE)
    current_policy = _read_text(agent_dir / POLICY_FILE)

    if not body.description.strip():
        errors.append("description is required")
    elif len(" ".join(body.description.split())) > factory_tools.MAX_DESCRIPTION_CHARS:
        warnings.append(f"description is over {factory_tools.MAX_DESCRIPTION_CHARS} chars")
    if not body.role_prompt.strip():
        errors.append("role_prompt is required")
    elif len(body.role_prompt) > factory_tools.MAX_PROMPT_CHARS:
        warnings.append(
            f"role_prompt is {len(body.role_prompt)} chars; the factory limit is"
            f" {factory_tools.MAX_PROMPT_CHARS}"
        )

    try:
        new_job = _render_job_md(name, body)
    except ValueError as exc:
        errors.append(str(exc))
        return {"ok": False, "errors": errors, "warnings": warnings, "diff": ""}

    # The exact loader path, on a throwaway copy named like the real folder.
    with tempfile.TemporaryDirectory(prefix="hq-agents-tmp-") as tmp:
        tmp_dir = Path(tmp) / "agents-tmp" / name
        tmp_dir.mkdir(parents=True)
        (tmp_dir / JOB_FILE).write_text(new_job)
        policy = current_policy if body.policy is None else body.policy
        (tmp_dir / POLICY_FILE).write_text(policy)
        try:
            spec = loader.parse_job_md(tmp_dir)
            loader.get_tools(spec.tools)
            spec.validate_trifecta()
        except (ValueError, KeyError, AssertionError, yaml.YAMLError) as exc:
            errors.append(_msg(exc))
            spec = None

    if spec is not None:
        try:
            factory_tools._check_model(spec.model)
        except ValueError as exc:
            errors.append(str(exc))
        _check_tools_soft(spec.tools, warnings)
        _check_caps(spec.caps, errors, warnings)
    _check_cron(body.cron, errors)

    from hq import engine

    loaded = name in engine.registered_agents()
    if body.status == "draft" and loaded:
        warnings.append("status draft: the agent unloads on the next restart")
    if body.status == "paused":
        warnings.append(
            "status paused in job.md only documents intent; the Pause button on the"
            " agents page is what stops runs"
        )

    diff = "" if _same_job(current_job, new_job) else _diff(
        current_job, new_job, f"agents/{name}/{JOB_FILE}"
    )
    if body.policy is not None and body.policy != current_policy:
        diff += _diff(current_policy, body.policy, f"agents/{name}/{POLICY_FILE}")
    return {"ok": not errors, "errors": errors, "warnings": warnings, "diff": diff}


def _atomic_write(path: Path, text: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text)
    os.replace(tmp, path)


def _load_config(name: str, agent_dir: Path) -> dict[str, Any]:
    """Blocking. Reads the folder leniently: a hand-edited job.md that no
    longer parses still comes back as raw text with ``parse_error`` set, so
    the console can show it and the owner can fix it."""
    job_raw = _read_text(agent_dir / JOB_FILE)
    policy_raw = _read_text(agent_dir / POLICY_FILE)
    meta: dict[str, Any] = {}
    body = ""
    parse_error: str | None = None
    try:
        meta, body = _split_job_md(job_raw)
    except (ValueError, TypeError, yaml.YAMLError) as exc:
        parse_error = str(exc)
    caps_raw = meta.get("caps") or {}
    try:
        caps = Caps(**caps_raw) if isinstance(caps_raw, dict) else settings().default_caps
    except (TypeError, ValueError) as exc:
        caps = settings().default_caps
        parse_error = parse_error or f"caps: {exc}"
    tools = [str(t) for t in (meta.get("tools") or [])]
    cron = [
        {"schedule": str(c.get("schedule", "")), "prompt": str(c.get("prompt", ""))}
        for c in (meta.get("cron") or [])
        if isinstance(c, dict)
    ]
    from hq import engine

    return {
        "name": name,
        "status": str(meta.get("status", "active")),
        "description": str(meta.get("description", "")),
        "model": str(meta.get("model", "default")),
        "tools": tools,
        "caps": caps.model_dump(),
        "cron": cron,
        "role_prompt": body,
        "policy": policy_raw.strip(),
        "job_md_raw": job_raw,
        "policy_md_raw": policy_raw,
        "git": _git_log(name),
        "loaded": name in engine.registered_agents(),
        "memory_refs": _vault_write_scopes(tools),
        "daily_spend_cap_usd": settings().daily_spend_cap_usd,
        "parse_error": parse_error,
    }


def _check_all_agents_load() -> None:
    """Blocking. What ``engine.bootstrap_pre_launch`` will do on the next
    boot, minus building the agents: ``loader.scan`` plus the model lookup.
    Raises ValueError/KeyError with the loader's own message."""
    for spec in loader.scan(strict=True).values():
        factory_tools._check_model(spec.model)


# --- endpoints ----------------------------------------------------------------

@router.get("/tools-catalog", operation_id="getToolsCatalog")
async def get_tools_catalog() -> list[dict[str, str]]:
    """Every registered tool: name, action class, provenance trust, whether the
    factory may grant it, and its one-line description."""
    return factory_tools.registry_catalog()


@router.get("/{name}/config", operation_id="getAgentConfig")
async def get_agent_config(name: str) -> dict:
    """Parsed and raw job.md and policy.md, the folder's last commits, and
    whether the running process has this agent loaded."""
    agent_dir = _agent_dir(name)
    return await asyncio.to_thread(_load_config, name, agent_dir)


@router.post("/{name}/config/validate", operation_id="validateAgentConfig")
async def validate_agent_config(name: str, body: AgentConfigBody) -> dict:
    """Loader + factory rules against a temp copy. Writes nothing."""
    agent_dir = _agent_dir(name)
    return await asyncio.to_thread(_validate, name, body, agent_dir)


@router.put("/{name}/config", operation_id="updateAgentConfig")
async def update_agent_config(name: str, body: AgentConfigBody) -> dict:
    """Validate, then write job.md (and policy.md when given) atomically.
    Does NOT restart: call ``POST /agents/{name}/apply`` for that."""
    agent_dir = _agent_dir(name)
    async with _write_lock:
        result = await asyncio.to_thread(_validate, name, body, agent_dir)
        if not result["ok"]:
            raise HTTPException(422, "validation failed: " + "; ".join(result["errors"]))
        new_job = _render_job_md(name, body)
        job_changed = not _same_job(_read_text(agent_dir / JOB_FILE), new_job)

        def write() -> None:
            if job_changed:
                _atomic_write(agent_dir / JOB_FILE, new_job)
            if body.policy is not None:
                _atomic_write(agent_dir / POLICY_FILE, body.policy.rstrip("\n") + "\n")

        await asyncio.to_thread(write)
    return {
        "saved": True,
        # A policy-only save needs no restart; instructions re-read policy.md per run.
        "restart_required": job_changed,
        "diff": result["diff"],
        "warnings": result["warnings"],
    }


@router.put("/{name}/policy", operation_id="updateAgentPolicy")
async def update_agent_policy(name: str, body: PolicyBody) -> dict:
    """Write policy.md only. No restart: the assembler (``hq.assemble``) reads
    policy.md at the start of every run, so the next run sees it."""
    agent_dir = _agent_dir(name)
    text = body.policy.rstrip("\n") + "\n"
    async with _write_lock:
        await asyncio.to_thread(_atomic_write, agent_dir / POLICY_FILE, text)
    return {
        "saved": True,
        "restart_required": False,
        "message": "policy.md saved; it applies on the agent's next run, no restart needed",
    }


@router.post("/{name}/apply", operation_id="applyAgentConfig")
async def apply_agent_config(name: str) -> dict:
    """Restart the backend so the saved job.md loads (launchd KeepAlive brings
    the process back; running DBOS workflows recover on their own).

    Refuses when any agent folder would fail ``loader.scan`` at boot: a
    restart into a broken folder would crash-loop the whole backend."""
    _agent_dir(name)
    try:
        await asyncio.to_thread(_check_all_agents_load)
    except (ValueError, KeyError, AssertionError, yaml.YAMLError, OSError) as exc:
        raise HTTPException(
            422, f"refusing to restart: agents would not load: {_msg(exc)}"
        ) from None
    factory_tools.schedule_restart()
    return {
        "restarting": True,
        "delay_s": factory_tools.RESTART_DELAY_S,
        "message": (
            f"backend restarts in {int(factory_tools.RESTART_DELAY_S)} s so agents/{name}"
            " reloads; launchd brings it back"
        ),
    }

