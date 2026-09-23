"""Contracts on the instruction set: what it names exists, what it asks for
is held, and it stays small, undated and free of the employer's name."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from hq import engine, memory
from hq import learning_pipeline as learning
from hq.config import settings
from hq.loader import parse_job_md, scan
from hq.tools.registry import TOOL_REGISTRY

AGENTS = settings().agents_dir
SKILL_REF = re.compile(r"`([a-z][a-z-]+)` skill|Load the ([a-z][a-z-]+) skill")
TOOL_REF = re.compile(r"`([a-z_]+)`")
AUTO_TOOLS = {"load_skill", "check_policy_rule", "list_policy", "propose_policy"}


def _specs():
    return scan(strict=True)


def _skills(agent: str) -> set[str]:
    return {p.parent.name for p in (AGENTS / agent / "skills").glob("*/SKILL.md")}


def test_every_skill_a_cron_names_exists_for_that_agent() -> None:
    for name, spec in _specs().items():
        for entry in spec.cron:
            for m in SKILL_REF.finditer(entry.prompt):
                skill = m.group(1) or m.group(2)
                assert skill in _skills(name), f"{name} cron names missing skill {skill}"


def test_every_skill_a_brief_names_exists_for_the_agent_it_goes_to() -> None:
    hunter_briefs = [
        learning.study_brief(learning.study_payload(learning.scan_payload(), []), []),
        learning.course_study_brief(learning.course_payload({"slug": "s", "title": "T"})),
        learning.scan_brief(learning.scan_payload()),
    ]
    for brief in hunter_briefs:
        for m in SKILL_REF.finditer(brief):
            skill = m.group(1) or m.group(2)
            assert skill in _skills("hunter"), f"a hunter brief names missing skill {skill}"


def test_every_tool_a_card_or_skill_names_is_held() -> None:
    for name, spec in _specs().items():
        if spec.runtime != "hq":
            continue
        held = spec.base_tool_names() | AUTO_TOOLS
        texts = [spec.system_prompt] + [
            p.read_text() for p in (AGENTS / name / "skills").glob("*/SKILL.md")]
        for text in texts:
            for tool in TOOL_REF.findall(text):
                if tool in TOOL_REGISTRY:
                    assert tool in held, f"{name} is told to use {tool} but does not hold it"


def test_only_sage_reaches_his_phone() -> None:
    holders = {n for n, s in _specs().items() if "notify_owner" in s.base_tool_names()}
    assert holders == {"sage"}


def test_the_schedule_is_the_intended_one() -> None:
    crons = {(n, e.schedule) for n, s in _specs().items() for e in s.cron}
    assert crons == {
        ("sage", "30 22 * * *"), ("sage", "0 20 * * 0"), ("sage", "30 23 * * *"),
        ("sage", "0 9 * * 3"), ("sage", "0 9 * * 1"), ("hunter", "0 21 * * *"),
    }
    starters = {(d[0], d[1]) for d in engine.SYSTEM_DISPATCHES}
    assert starters == {("course_study", "30 18 * * *"), ("job_search", "15 21 * * *"),
                        ("learning_run", "0 22 * * *"), ("source_hunt", "0 7 * * 0")}


def _instruction_files() -> list[Path]:
    # policy.md is owner-approved rules stamped by code with their approval
    # date; the stamp is metadata, not history in a prompt.
    return [p for p in AGENTS.rglob("*.md")
            if "candidate_data" not in p.parts and p.name != "policy.md"]


def test_cards_and_skills_stay_small() -> None:
    for path in _instruction_files():
        lines = len(path.read_text().splitlines())
        limit = 200 if path.name in {"job.md", "AGENTS.md", "charter.md"} else 500
        assert lines <= limit, f"{path} is {lines} lines (limit {limit})"


def test_instructions_carry_no_dated_history() -> None:
    for path in _instruction_files():
        body = path.read_text().split("\n---\n", 1)[-1]
        assert not re.search(r"\b20\d\d-\d\d-\d\d\b", body), f"{path} carries a date"


@pytest.mark.parametrize("block", sorted(memory.BLOCK_CAPS))
def test_no_memory_block_names_his_employer(block: str) -> None:
    path = settings().vault_dir / block
    if not path.exists():
        return
    text = path.read_text()
    for name in settings().private_employers:
        assert name.lower() not in text.lower(), f"{block} names the employer"


def test_no_instruction_names_his_employer() -> None:
    for path in _instruction_files() + list(AGENTS.rglob("*.yaml")):
        text = path.read_text().lower()
        for name in settings().private_employers:
            assert name.lower() not in text, f"{path} names the employer"


def test_every_card_parses_and_carries_the_charter() -> None:
    from hq.loader import instructions_for

    charter = (AGENTS / "_shared" / "charter.md").read_text().strip().splitlines()[0]
    for name in ("sage", "hunter", "tutor"):
        text = instructions_for(parse_job_md(AGENTS / name))
        assert charter in text
