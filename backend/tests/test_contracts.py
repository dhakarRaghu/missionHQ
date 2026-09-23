"""Contracts on the instruction set: what it names exists, what it asks for
is held, and it stays small, undated and free of the employer's name."""

from __future__ import annotations

import inspect
import re
import shutil
from pathlib import Path

import pytest

from hq import engine, memory, privacy, runner
from hq import learning_pipeline as learning
from hq.config import settings
from hq.loader import AgentSpec, instructions_for, parse_job_md, scan
from hq.tools.registry import TOOL_REGISTRY

AGENTS = settings().agents_dir
SKILL_REF = re.compile(r"`([a-z][a-z-]+)` skill|Load the ([a-z][a-z-]+) skill")
TOOL_REF = re.compile(r"`([a-z_]+)`")
DATE = re.compile(r"\b20\d\d-\d\d-\d\d\b")
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
    """Every file any agent loads: cards, policies, skills, the charter, the
    candidate profile, tutor's writer files, the operator card, voice data.
    Nothing is excluded."""
    root = settings().agents_dir
    return sorted([*root.rglob("*.md"), *root.rglob("*.yaml")])


def _assembled(spec: AgentSpec) -> str:
    """Everything the agent is told, built the way a run builds it: the
    loader's instructions (charter, policy, card, profile, memory blocks,
    notebook, roster, skills index) without the clock line, or, for an
    external runtime, the suffix plus the card delivered as AGENTS.md."""
    if spec.runtime != "hq":
        return f"{runner.EXTERNAL_SYSTEM_SUFFIX}\n\n{runner.agent_card(spec) or ''}"
    return instructions_for(spec).split("\n\n", 1)[1]


def _data_blocks(spec: AgentSpec) -> list[str]:
    """Injected text that is data, not rules, and may carry dates: the
    in-flight list in memory/active_projects.md and the agent's own notebook.
    Exempt from the date check only; never from the employer check."""
    blocks = []
    projects = settings().vault_dir / "memory" / "active_projects.md"
    if projects.exists() and (spec.memory is None or "active_projects" in spec.memory):
        blocks.append(projects.read_text())
    notebook = memory.load_working_memory(spec.name) if spec.keeps_notebook() else None
    if notebook:
        blocks.append(notebook)
    return blocks


def test_cards_and_skills_stay_small() -> None:
    for path in _instruction_files():
        if path.suffix != ".md":
            continue
        lines = len(path.read_text().splitlines())
        limit = 200 if path.name in {"job.md", "AGENTS.md", "charter.md"} else 500
        assert lines <= limit, f"{path} is {lines} lines (limit {limit})"


def test_instructions_carry_no_dated_history() -> None:
    # voice.yaml is measured data read by code (it cites the note it was
    # measured from); the prompts are the markdown files.
    for path in (p for p in _instruction_files() if p.suffix == ".md"):
        body = path.read_text().split("\n---\n", 1)[-1]
        assert not DATE.search(body), f"{path} carries a date"


def test_what_each_agent_is_told_carries_no_dated_history() -> None:
    """The full assembled prompt, not just the files: memory blocks, the
    policy, the profile and the roster all land in it."""
    for name, spec in _specs().items():
        text = _assembled(spec)
        for block in _data_blocks(spec):
            text = text.replace(block, "")
        hit = DATE.search(text)
        assert not hit, f"{name}'s instructions carry a date: {text[hit.start()-80:hit.end()]!r}"


def _employer_leaks(texts: dict[str, str]) -> list[str]:
    return [where for where, text in texts.items() if privacy.employers_named(text)]


def _everything_loaded() -> dict[str, str]:
    texts = {str(p): p.read_text(errors="replace") for p in _instruction_files()}
    texts.update({f"{n} (assembled)": _assembled(s) for n, s in _specs().items()})
    for block in memory.BLOCK_CAPS:
        path = settings().vault_dir / block
        if path.exists():
            texts[block] = path.read_text()
    return texts


def test_nothing_an_agent_loads_names_his_employer() -> None:
    """Checked against the names in .env (PRIVATE_EMPLOYERS) when it is set.
    Every file, every assembled prompt, every memory block."""
    assert _employer_leaks(_everything_loaded()) == []


def test_the_employer_check_sees_every_loaded_file(tmp_path, monkeypatch) -> None:
    """With made-up names configured, a name planted in the candidate
    profile, a skill, a policy or a memory block is caught, both in the file
    and in the prompt the loader builds from it."""
    agents = tmp_path / "agents"
    shutil.copytree(AGENTS, agents)
    vault = tmp_path / "vault"
    (vault / "memory").mkdir(parents=True)
    monkeypatch.setattr(settings(), "agents_dir", agents)
    monkeypatch.setattr(settings(), "vault_dir", vault)
    monkeypatch.setattr(settings(), "private_employers", ("Acme Corp", "Globex"))
    assert _employer_leaks(_everything_loaded()) == []

    plants = {
        agents / "hunter" / "candidate_data" / "candidate-profile.md": "Intern at Acme Corp.",
        agents / "hunter" / "skills" / "job-research" / "SKILL.md": "Try acme-corp alumni.",
        agents / "sage" / "policy.md": "- Never mention globex.",
        vault / "memory" / "user.md": "# User\n- Works at GLOBEX.",
    }
    for path, line in plants.items():
        path.write_text(path.read_text() + "\n" + line if path.exists() else line)
    leaks = _employer_leaks(_everything_loaded())
    for path in plants:
        rel = str(path) if path.is_relative_to(agents) else str(path.relative_to(vault))
        assert rel in leaks, f"{rel} was not caught"
    assert {"hunter (assembled)", "sage (assembled)"} <= set(leaks)


def test_every_memory_block_an_agent_names_exists_in_code() -> None:
    stems = {Path(b).stem for b in memory.BLOCK_CAPS}
    for name, spec in _specs().items():
        assert set(spec.memory or []) <= stems, f"{name} names a memory block that is not one"


def test_every_card_parses_and_carries_the_charter() -> None:
    from hq.loader import instructions_for

    charter = (AGENTS / "_shared" / "charter.md").read_text().strip().splitlines()[0]
    for name in ("sage", "hunter", "tutor"):
        text = instructions_for(parse_job_md(AGENTS / name))
        assert charter in text


# --- the employer gate (hq.privacy) -----------------------------------------

def test_the_gate_matches_whole_words_and_never_repeats_a_name(monkeypatch) -> None:
    monkeypatch.setattr(settings(), "private_employers", ("Acme Corp", "Globex"))
    assert privacy.employers_named("I was at ACME corp.") == ["Acme Corp"]
    assert privacy.employers_named("https://globex.com/jobs and acmecorp") == [
        "Acme Corp", "Globex"]
    assert privacy.employers_named("phase06_globex/app.yaml") == ["Globex"]
    assert privacy.employers_named("Globexian lore") == []
    assert privacy.problem({"q": ["fine", {"k": "globex careers"}]}) == privacy.REFUSAL
    assert "globex" not in privacy.REFUSAL.lower() and "acme" not in privacy.REFUSAL.lower()
    monkeypatch.setattr(settings(), "private_employers", ())
    assert privacy.problem("globex") is None


def test_every_tool_that_writes_searches_or_hands_off_is_gated() -> None:
    from hq.safety import ActionClass, Trust

    for name, tool in TOOL_REGISTRY.items():
        leaves = tool.action != ActionClass.READ or tool.trust not in (Trust.VAULT, Trust.USER)
        assert tool.private == leaves, name
    for name in ("vault_write", "record_job", "web_search", "web_fetch", "fetch_source",
                 "browser_read", "job_board", "create_subtask", "request_operator",
                 "publish_post", "write_lesson", "write_lesson_part", "record_fact"):
        assert TOOL_REGISTRY[name].private, name


def test_a_search_naming_the_employer_is_refused_before_the_network(monkeypatch) -> None:
    import asyncio
    from types import SimpleNamespace

    from pydantic_ai import ModelRetry

    from hq.tools.registry import HQDeps

    monkeypatch.setattr(settings(), "private_employers", ("Acme Corp",))
    ctx = SimpleNamespace(deps=HQDeps(agent="hunter"))
    for tool, kwargs in (("web_search", {"query": "acme corp engineering blog"}),
                         ("web_fetch", {"url": "https://acme-corp.com/careers"}),
                         ("record_job", {"company": "Initech", "role": "SDE-1",
                                         "url": "https://x.example/1",
                                         "why_fit": "like his Acme Corp work"}),
                         ("vault_write", {"path": "quarantine/x.md",
                                          "content": "at Acme Corp"})):
        with pytest.raises(ModelRetry, match="never named"):
            asyncio.run(TOOL_REGISTRY[tool].fn(ctx, **kwargs))


def test_the_vault_refuses_the_name_from_every_writer_but_the_owner(monkeypatch) -> None:
    monkeypatch.setattr(settings(), "private_employers", ("Acme Corp",))
    text = "# Note\nHe works at Acme Corp.\n"
    assert memory.write_problem("projects/a.md", text, actor="sage",
                                existing=None) == privacy.REFUSAL
    assert memory.write_problem("quarantine/acme-corp.md", "# x\n", actor="operator",
                                existing=None) == privacy.REFUSAL
    assert memory.write_problem("projects/a.md", text, actor="owner", existing=None) is None


def test_only_the_owner_writes_the_shared_memory_blocks() -> None:
    assert memory.OWNER_ONLY == frozenset(memory.BLOCK_CAPS)
    assert "memory/rules.md" not in memory.BLOCK_CAPS
    for block in memory.BLOCK_CAPS:
        refused = memory.write_problem(block, "# x\n", actor="sage", existing=None)
        assert refused and memory.PROPOSALS_DIR in refused
        assert memory.write_problem(block, "# x\n", actor="owner", existing=None) is None
    assert memory.write_problem("memory/proposals/2026-01-05.md", "# p\n", actor="sage",
                                existing=None) is None


def test_consolidation_can_leave_out_every_web_note(tmp_path, monkeypatch) -> None:
    from hq.tools.vault_tools import _list_notes

    monkeypatch.setattr(settings(), "vault_dir", tmp_path)
    notes = {
        "quarantine/lead.md": "---\nprovenance: web\n---\n# lead\n",
        "projects/web.md": "---\nprovenance: web\n---\n# read from a page\n",
        "projects/own.md": "---\nprovenance: agent\n---\n# his notes\n",
        "daily/note.md": "# today\n",
    }
    for rel, text in notes.items():
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / rel).write_text(text)
    assert {r["path"] for r in _list_notes("", 1)} == set(notes)
    assert {r["path"] for r in _list_notes("", 1, True)} == {"projects/own.md", "daily/note.md"}
    skill = (AGENTS / "sage" / "skills" / "consolidate" / "SKILL.md").read_text()
    assert "trusted_only=true" in skill and "memory/proposals/" in skill


def test_an_agent_that_reads_the_web_keeps_no_notebook() -> None:
    specs = _specs()
    for name, spec in specs.items():
        if spec.reads_web():
            assert not spec.keeps_notebook(), name
            assert spec.working_memory_path() not in spec.vault_write_scopes(), name
            assert "Your working memory" not in _assembled(spec), name
    assert specs["hunter"].vault_write_scopes() == ["quarantine/**"]
    assert specs["sage"].keeps_notebook()


def test_a_web_reader_may_not_write_its_notebook_either(tmp_path) -> None:
    spec = AgentSpec(name="reader", tools=["web_fetch", "vault_write:memory/agents/reader.md"],
                     dir=tmp_path)
    with pytest.raises(ValueError, match="quarantine"):
        spec.validate_trifecta()


def test_a_referral_row_never_carries_the_employer(monkeypatch) -> None:
    import json

    from hq.job_pipeline import (
        extract_referral_people,
        referral_brief,
        referral_payload,
    )

    monkeypatch.setattr(settings(), "private_employers", ("Acme Corp",))
    person = {"name": "Ada", "headline": "SWE", "profile_url": "https://www.linkedin.com/in/ada",
              "degree": "2nd", "shared_ground": "both ex-Acme Corp", "why_them": "owns the team"}
    rows = extract_referral_people("```json\n" + json.dumps(
        {"missionhq_referral_people": [person]}) + "\n```")
    assert rows[0]["name"] == "Ada" and rows[0]["shared_ground"] == ""
    assert rows[0]["why_them"] == "owns the team"
    brief = referral_brief(referral_payload(job_id="1", company="Initech", role="SWE"))
    assert "employer he can open with" not in brief


def test_policy_md_gets_the_rule_and_nothing_else() -> None:
    from hq.tools import policy_tools

    assert policy_tools.format_rule_line("  Always do X in full.  ") == "- Always do X in full."
    src = inspect.getsource(policy_tools.propose_policy)
    assert '"reason": reason_text(reason)' in src
