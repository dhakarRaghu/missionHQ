"""Agent loader: scan agents/ folders -> validated AgentSpec -> Pydantic AI Agent.

Adding an agent is adding a folder. The scoped-trifecta validator runs here and
fails LOUDLY at load: web-read tools never combine with outbound-send tools or
with vault writes outside quarantine/**.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml
from pydantic import BaseModel, field_validator
from pydantic_ai import Agent
from pydantic_ai.tools import Tool

from hq import memory
from hq.config import Caps, settings
from hq.tools.registry import TOOL_REGISTRY, WEB_READ_TOOLS, HQDeps, get_tools


class CronEntry(BaseModel):
    schedule: str
    prompt: str


class AgentSpec(BaseModel):
    name: str
    description: str = ""
    status: str = "active"  # active | paused | draft
    model: str = "default"  # registry name or role alias
    tools: list[str] = []
    caps: Caps = Caps()
    cron: list[CronEntry] = []
    system_prompt: str = ""
    policy: str = ""
    dir: Path

    @field_validator("name")
    @classmethod
    def _name_ok(cls, v: str) -> str:
        assert v.replace("-", "").replace("_", "").isalnum(), "agent name must be alnum/dash"
        return v

    def base_tool_names(self) -> set[str]:
        return {t.split(":")[0] for t in self.tools}

    def vault_write_scopes(self) -> list[str]:
        scopes: list[str] = []
        for t in self.tools:
            if t.split(":")[0] == "vault_write":
                scopes.append(t.split(":", 1)[1] if ":" in t else "**")
        return scopes

    def validate_trifecta(self) -> None:
        names = self.base_tool_names()
        has_web = bool(names & WEB_READ_TOOLS)
        if not has_web:
            return
        outbound = {
            n for n in names
            if n in TOOL_REGISTRY and TOOL_REGISTRY[n].requires_approval is False
            and TOOL_REGISTRY[n].action.value in ("external_write", "spend")
        }
        # Any outbound-send tool at all is forbidden alongside web reads.
        gated = {
            n for n in names
            if n in TOOL_REGISTRY and TOOL_REGISTRY[n].action.value in ("external_write", "spend")
        }
        if gated or outbound:
            raise ValueError(
                f"agent {self.name}: web-read tools cannot combine with outbound tools {gated}"
            )
        for scope in self.vault_write_scopes():
            if not scope.startswith("quarantine"):
                raise ValueError(
                    f"agent {self.name}: web-read agents may write only vault_write:quarantine/**,"
                    f" got scope {scope!r}"
                )

    def job_hash(self) -> str:
        try:
            out = subprocess.run(
                ["git", "log", "-1", "--format=%h", "--", str(self.dir)],
                cwd=settings().agents_dir.parent, capture_output=True, text=True, check=True,
            ).stdout.strip()
            return out or "uncommitted"
        except (subprocess.CalledProcessError, FileNotFoundError):
            return "unknown"


def parse_job_md(agent_dir: Path) -> AgentSpec:
    text = (agent_dir / "job.md").read_text()
    if not text.startswith("---"):
        raise ValueError(f"{agent_dir.name}/job.md missing frontmatter")
    _, fm, body = text.split("---", 2)
    meta = yaml.safe_load(fm)
    policy_file = agent_dir / "policy.md"
    spec = AgentSpec(
        **meta,
        system_prompt=body.strip(),
        policy=policy_file.read_text().strip() if policy_file.exists() else "",
        dir=agent_dir,
    )
    if spec.name != agent_dir.name:
        raise ValueError(f"agent folder {agent_dir.name} vs manifest name {spec.name}")
    return spec


def scan() -> dict[str, AgentSpec]:
    """All non-draft agent specs, trifecta-validated. Raises on any invalid folder."""
    specs: dict[str, AgentSpec] = {}
    root = settings().agents_dir
    for agent_dir in sorted(p for p in root.iterdir() if p.is_dir()):
        if not (agent_dir / "job.md").exists():
            continue
        spec = parse_job_md(agent_dir)
        if spec.status == "draft":
            continue
        get_tools(spec.tools)  # unknown tool names fail here
        spec.validate_trifecta()
        specs[spec.name] = spec
    return specs


def skills_index(agent_dir: Path) -> str:
    """Progressive disclosure: only names + first lines are injected."""
    lines = []
    for skill_md in sorted(agent_dir.glob("skills/*/SKILL.md")):
        first = skill_md.read_text().strip().splitlines()
        title = first[0].lstrip("# ") if first else skill_md.parent.name
        lines.append(f"- {skill_md.parent.name}: {title}")
    return "\n".join(lines)


def instructions_for(spec: AgentSpec) -> str:
    parts = [spec.system_prompt]
    if spec.policy:
        parts.append(f"# Standing policies (owner-approved; always follow)\n{spec.policy}")
    blocks = memory.load_core_blocks()
    if blocks:
        parts.append(f"# Shared memory\n{blocks}")
    skills = skills_index(spec.dir)
    if skills:
        parts.append(
            "# Skills available (call load_skill with a name for the full instructions)\n" + skills
        )
    return "\n\n".join(parts)


def build_agent(spec: AgentSpec, durability) -> Agent:
    """Construct the Pydantic AI Agent. Must happen BEFORE DBOS.launch().

    The model is bound here (DBOS forbids choosing it at run time). The manifest
    names a role or registry name; llm.py is the only place a provider appears.
    """
    from hq import llm

    tools = [
        Tool(t.fn, requires_approval=t.requires_approval)
        for t in get_tools(spec.tools)
    ]
    return Agent(
        llm.registry().resolve(spec.model),
        name=f"hq-{spec.name}",
        instructions=instructions_for(spec),
        deps_type=HQDeps,
        tools=tools,
        capabilities=[durability],
    )
