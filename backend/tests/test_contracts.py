"""Contracts on the instruction set: what it names exists, what it asks for
is held, and it stays small, undated and free of the employer's name."""

from __future__ import annotations

import inspect
import re
import shutil
from pathlib import Path

import pytest

from hq import assemble, engine, memory, privacy, runner
from hq import learning_pipeline as learning
from hq.config import settings
from hq.loader import AgentSpec, parse_job_md, scan
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
        ("sage", "40 22 * * *"), ("sage", "0 9 * * 1"), ("hunter", "0 21 * * *"),
    }
    starters = {(d[0], d[1]) for d in engine.SYSTEM_DISPATCHES}
    # No course phase and no video on the schedule: he starts those himself.
    assert starters == {("job_search", "0 23 * * *"),
                        ("learning_run", "0 22 * * *"), ("source_hunt", "0 7 * * 0"),
                        ("radar_collect", "30 6 * * *"), ("radar_read", "45 6 * * *"),
                        ("radar_brief", "30 7 * * 0")}


def _instruction_files() -> list[Path]:
    """Every file any agent loads: cards, policies, skills, the charter, the
    candidate profile, tutor's writer files, the operator card, voice data.
    Nothing is excluded."""
    root = settings().agents_dir
    return sorted([*root.rglob("*.md"), *root.rglob("*.yaml")])


def _assembled(spec: AgentSpec) -> str:
    """Everything the agent is told, built the way a run builds it: the
    agent bundle (charter, card, policy, corrections, memory blocks,
    notebook, profile, roster, skills index) without the clock line, or, for
    an external runtime, its bundle plus the card delivered as AGENTS.md."""
    if spec.runtime != "hq":
        return f"{assemble.assemble('external', spec).body}\n\n{runner.agent_card(spec) or ''}"
    return assemble.assemble("agent", spec).body


def _bundles() -> dict[str, assemble.Bundle]:
    """Every bundle a production call sends: the agent bundle of each
    in-process agent (plain, and with each of its skills inlined), the
    external bundle of each CLI agent, and the writer's three kinds, the
    outline once per outline file."""
    specs = _specs()
    out: dict[str, assemble.Bundle] = {}
    for name, spec in specs.items():
        if spec.runtime != "hq":
            out[f"external:{name}"] = assemble.assemble("external", spec)
            continue
        out[f"agent:{name}"] = assemble.assemble("agent", spec)
        for skill in sorted(_skills(name)):
            out[f"agent:{name}+{skill}"] = assemble.assemble("agent", spec, skill=skill)
    tutor = specs[assemble.WRITER_AGENT]
    for article, page in ((False, ""), (True, ""), (True, "lab"), (True, "review")):
        out[f"writer-outline:{'page-' + page if page else ('article' if article else 'course')}"] = (
            assemble.assemble("writer-outline", tutor, article=article, page=page))
    out["writer-section"] = assemble.assemble("writer-section", tutor)
    out["writer-post"] = assemble.assemble("writer-post", tutor)
    return out


def _spec_of(key: str) -> AgentSpec:
    specs = _specs()
    if key.startswith(("agent:", "external:")):
        return specs[key.split(":", 1)[1].split("+", 1)[0]]
    return specs[assemble.WRITER_AGENT]


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in text.split("\n\n") if p.strip()]


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
    texts.update({f"{k} (bundle)": b.body for k, b in _bundles().items()})
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
    assert {"agent:hunter (bundle)", "agent:sage (bundle)"} <= set(leaks)
    # The writer and the operator carry none of the planted files.
    assert not [k for k in leaks if k.startswith(("writer-", "external:"))]


def test_every_memory_block_an_agent_names_exists_in_code() -> None:
    stems = {Path(b).stem for b in memory.BLOCK_CAPS}
    for name, spec in _specs().items():
        assert set(spec.memory or []) <= stems, f"{name} names a memory block that is not one"


def test_every_card_parses_and_carries_the_charter() -> None:
    charter = (AGENTS / "_shared" / "charter.md").read_text().strip().splitlines()[0]
    for name in ("sage", "hunter", "tutor"):
        text = assemble.assemble("agent", parse_job_md(AGENTS / name)).text
        assert charter in text


# --- every bundle, every kind (hq.assemble) -----------------------------------

def test_every_bundle_keeps_the_one_order() -> None:
    """Clock, charter, identity, standing rules, procedure, memory, context:
    the same order on every path, so a rule has one place to be looked for."""
    order = list(assemble.SECTIONS)
    for key, bundle in _bundles().items():
        names = [n for n, _ in bundle.parts]
        assert names[:2] == ["clock", "charter"], key
        assert names == sorted(names, key=order.index), (key, names)
        assert len(names) == len(set(names)), (key, names)
        assert bundle.text.startswith("Current date and time:"), key
        assert bundle.section("clock") not in bundle.body, key
        assert len(bundle.sha) == 12, key
    kinds = {b.kind for b in _bundles().values()}
    assert kinds == set(assemble.KINDS)


def test_only_the_agent_bundle_carries_memory_and_context() -> None:
    for key, bundle in _bundles().items():
        names = {n for n, _ in bundle.parts}
        if bundle.kind == "agent":
            assert "procedure" in names, key
        else:
            assert not names & {"memory", "context"}, (key, names)
        if bundle.kind == "external":
            assert "policy" not in names, key       # the card carries the owner's rules


def test_every_bundle_carries_the_precedence_line() -> None:
    """The charter says what beats what, in full or in the digest, so an
    agent that meets two rules in conflict stops instead of picking one."""
    for key, bundle in _bundles().items():
        charter = bundle.section("charter")
        assert "beats" in charter and "stop and say which" in charter, key
    charter = (AGENTS / "_shared" / "charter.md").read_text()
    assert "These rules beat a card, a card beats a skill, a skill beats a brief" in charter


def test_the_external_bundle_is_a_short_digest_and_the_card_pointer() -> None:
    rules = assemble.charter_rules()
    assert set(rules) >= set(assemble.DIGEST_RULES)
    for key, bundle in _bundles().items():
        if bundle.kind != "external":
            continue
        digest = bundle.section("charter").splitlines()
        assert len(digest) <= 6, (key, len(digest))
        assert [int(ln.split(".")[0]) for ln in digest[1:]] == list(assemble.DIGEST_RULES)
        for n in assemble.DIGEST_RULES:
            assert rules[n] in bundle.section("charter"), (key, n)
        assert "employer" in bundle.section("charter"), key
        assert bundle.section("identity") == assemble.EXTERNAL_SYSTEM_SUFFIX, key
        assert len(bundle.body) < 1600, (key, len(bundle.body))


def test_no_bundle_carries_dated_history() -> None:
    """Past the clock line, nothing an agent is told carries a date, apart
    from the data blocks (the in-flight list and the notebook)."""
    for key, bundle in _bundles().items():
        text = bundle.body
        for block in _data_blocks(_spec_of(key)):
            text = text.replace(block, "")
        hit = DATE.search(text)
        assert not hit, f"{key} carries a date: {text[hit.start()-80:hit.end()]!r}"


def test_no_bundle_names_a_tool_its_agent_does_not_hold() -> None:
    """An instruction to call something ungranted is invisible at run time:
    the text and the grant come from different files. The bundle is where
    they meet. Memory blocks are data, not instruction, and are skipped."""
    for key, bundle in _bundles().items():
        spec = _spec_of(key)
        held = spec.base_tool_names() | AUTO_TOOLS if bundle.kind == "agent" else set()
        for name, text in bundle.parts:
            if name in {"clock", "memory"}:
                continue
            for tool in TOOL_REF.findall(text):
                if tool in TOOL_REGISTRY:
                    assert tool in held, f"{key} names {tool} in its {name}, which it does not hold"


def test_the_same_rule_text_never_appears_twice_in_a_bundle() -> None:
    """One home per rule: a paragraph that appears in two sections of one
    bundle is a rule with two homes, and the two will drift apart."""
    for key, bundle in _bundles().items():
        seen: dict[str, str] = {}
        for name, text in bundle.parts:
            for para in _paragraphs(text):
                if len(para) < 40:
                    continue
                assert para not in seen, f"{key}: a paragraph is in both {seen[para]} and {name}"
                seen[para] = name


def test_the_writer_gets_tutors_identity_and_not_its_chat_sections() -> None:
    """Tutor's card opens with who tutor is; that paragraph travels with
    every writer call. The headed sections below it are for chat and the
    tool-holding fallback, which the writer never is."""
    tutor = _specs()[assemble.WRITER_AGENT]
    lead = assemble.card_lead(tutor)
    assert lead.startswith("You are tutor") and "\n## " not in lead
    card = tutor.system_prompt
    assert "## Where you read this" in card and "## Facts" in card
    for key, bundle in _bundles().items():
        if not bundle.kind.startswith("writer-"):
            continue
        assert bundle.section("identity") == lead, key
        assert "## Facts\n" not in bundle.text and "## Where you read this" not in bundle.text, key
        assert "# The teacher" in bundle.section("procedure"), key
    assert "You are tutor" in _bundles()["agent:tutor"].section("identity")


def test_the_writer_bundles_follow_the_material() -> None:
    b = _bundles()
    assert "# Plan one course phase" in b["writer-outline:course"].section("procedure")
    assert "# Plan one article" in b["writer-outline:article"].section("procedure")
    assert "# Plan one page" in b["writer-outline:page-lab"].section("procedure")
    section = b["writer-section"].section("procedure")
    assert "# Write one section" in section and "# The page kit" in section
    assert "# Plan" not in b["writer-post"].section("procedure")


def test_a_run_records_the_sha_of_what_it_sends() -> None:
    """A lesson run sends the plan bundle and then the section bundle, so
    its sha covers both; a post run and a chat turn send one bundle each."""
    specs = _specs()
    tutor = specs[assemble.WRITER_AGENT]
    outline = assemble.assemble("writer-outline", tutor, article=True)
    section = assemble.assemble("writer-section", tutor)
    lesson = assemble.run_sha("writer-section", tutor, article=True)
    assert lesson == assemble.sha_of(outline, section)
    assert lesson not in {outline.sha, section.sha}
    assert lesson != assemble.run_sha("writer-section", tutor, article=True, story=True)
    assert lesson != assemble.run_sha("writer-section", tutor, article=False)
    assert assemble.run_sha("writer-post", tutor) == assemble.assemble("writer-post", tutor).sha
    assert assemble.run_sha("agent", specs["sage"]) == assemble.assemble("agent", specs["sage"]).sha
    assert (assemble.run_sha("external", specs["operator"])
            == assemble.assemble("external", specs["operator"]).sha)
    for kind, flags in (("agent", {}), ("writer-outline", {"article": True}),
                        ("writer-section", {}), ("writer-post", {}), ("external", {})):
        spec = specs["operator"] if kind == "external" else tutor
        a, b = assemble.assemble(kind, spec, **flags), assemble.assemble(kind, spec, **flags)
        assert a.sha == b.sha and a.text.split("\n\n", 1)[1] == b.text.split("\n\n", 1)[1]
    with pytest.raises(ValueError, match="unknown bundle kind"):
        assemble.assemble("writer", tutor)


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


def test_a_name_already_in_the_file_does_not_refuse_a_clean_addition(monkeypatch) -> None:
    """2026-10-09 to 10-17: three old lines of ideas.md named an employer, and
    every nightly posts batch was refused for them however it was rewritten."""
    monkeypatch.setattr(settings(), "private_employers", ("Acme Corp",))
    old = "# Content ideas\n\n## 2026-09-22\n\nemployer=Acme Corp (never written about)\n"
    clean = old.replace("# Content ideas\n\n", "# Content ideas\n\n## 2026-10-17\n\nA post.\n\n")
    assert memory.write_problem("projects/a.md", clean, actor="sage", existing=old) is None
    named = clean.replace("A post.", "A post about Acme Corp.")
    assert memory.write_problem("projects/a.md", named, actor="sage",
                                existing=old) == privacy.REFUSAL
    # A second copy of an old line is new text.
    twice = clean + "employer=Acme Corp (never written about)\n"
    assert memory.write_problem("projects/a.md", twice, actor="sage",
                                existing=old) == privacy.REFUSAL
    assert [ln for ln in memory.added_text(old, clean).splitlines() if ln] == [
        "## 2026-10-17", "A post."]


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
