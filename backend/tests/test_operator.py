"""Operator: one contract, delivered to Codex, read by its guard, enforced
on its output."""

from __future__ import annotations

import asyncio
import inspect
import re
import shutil
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from hq import engine, job_pipeline, llm, loader, runner
from hq import learning_pipeline as learning
from hq.config import settings
from hq.runtimes import codex_cli
from hq.tools.registry import HQDeps

OPERATOR_DIR = settings().agents_dir / "operator"
CARD = OPERATOR_DIR / "AGENTS.md"


@pytest.fixture
def operator_dir(tmp_path, monkeypatch) -> Path:
    """A copy of agents/operator in a scratch agents dir, so tests can add a
    policy.md or drop the card without touching the real folder."""
    agents = tmp_path / "agents"
    shutil.copytree(OPERATOR_DIR, agents / "operator")
    monkeypatch.setattr(settings(), "agents_dir", agents)
    return agents / "operator"


@pytest.fixture
def workdir(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "data" / "operator"
    monkeypatch.setattr(settings(), "operator_workdir", path)
    return path


@pytest.fixture
def codex_turns(monkeypatch) -> list[dict[str, Any]]:
    """codex_cli.run_turn replaced: records the prompt, the --cd directory and
    the AGENTS.md Codex would find there at the moment it starts."""
    turns: list[dict[str, Any]] = []

    async def run_turn(prompt: str, *, session_id: str | None = None,
                       workdir: str | None = None) -> codex_cli.CodexResult:
        card = Path(workdir) / "AGENTS.md" if workdir else None
        turns.append({"prompt": prompt, "workdir": workdir,
                      "card": card.read_text() if card and card.exists() else None})
        return codex_cli.CodexResult(text="Read https://example.com/jobs: two roles listed.",
                                     input_tokens=10, output_tokens=5,
                                     session_id="s", is_error=False)

    async def record(**kw: Any) -> None:
        return None

    monkeypatch.setattr(codex_cli, "available", lambda: None)
    monkeypatch.setattr(codex_cli, "run_turn", run_turn)
    monkeypatch.setattr(llm, "record_call", record)
    return turns


def _run_external(spec: loader.AgentSpec, prompt: str) -> runner.RunOutcome:
    deps = HQDeps(agent=spec.name)
    return asyncio.run(runner.execute_external(spec, prompt=prompt, deps=deps))


# --- the card reaches Codex ---------------------------------------------------

def test_codex_starts_in_its_own_directory_with_the_card(workdir, codex_turns) -> None:
    spec = loader.parse_job_md(OPERATOR_DIR)
    prompt = engine._anchored_prompt("operator", spec, "Read one page", "Open https://x.test")
    outcome = _run_external(spec, prompt)

    assert outcome.outcome == "done"
    [turn] = codex_turns
    assert turn["workdir"] == str(workdir)
    assert Path(turn["workdir"]) != settings().vault_dir
    # The contract is in the file Codex reads, word for word.
    assert turn["card"] == CARD.read_text().strip() + "\n"
    assert "## Contract" in turn["card"] and "One working tab" in turn["card"]


def test_the_prompt_points_at_the_card_instead_of_repeating_it(workdir, codex_turns) -> None:
    spec = loader.parse_job_md(OPERATOR_DIR)
    _run_external(spec, "[operator — reads]\nTask: Read one page")
    prompt = codex_turns[0]["prompt"]

    suffix = runner.EXTERNAL_SYSTEM_SUFFIX
    # The task arrives with the clock its contract refers to, then the card pointer.
    assert prompt.startswith(f"{suffix}\n\nCurrent date and time:")
    assert prompt.endswith("[operator — reads]\nTask: Read one page")
    assert len(suffix.splitlines()) == 4
    assert "AGENTS.md" in suffix
    # The rules live once, in the card: none of them is restated here.
    for gone in ("USE EVERYTHING", "READ ONLY", "tab", "credential", "sign in"):
        assert gone not in suffix
    assert len(suffix) < 400


def test_codex_is_launched_read_only_in_that_directory(tmp_path, monkeypatch) -> None:
    """The argv, not just the parameter: --cd is the card's directory and the
    sandbox stays read-only."""
    seen: list[tuple[str, ...]] = []

    class Proc:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return b"", b""

    async def spawn(*argv: str, **kw: Any) -> Proc:
        seen.append(argv)
        return Proc()

    monkeypatch.setattr(settings(), "codex_runtime_enabled", True)
    monkeypatch.setattr(codex_cli, "resolve_cli", lambda: "/usr/local/bin/codex")
    monkeypatch.setattr(codex_cli, "browser_auth_override", list)
    monkeypatch.setattr(codex_cli.asyncio, "create_subprocess_exec", spawn)
    asyncio.run(codex_cli.run_turn("hello", workdir=str(tmp_path)))

    argv = list(seen[0])
    assert argv[argv.index("--cd") + 1] == str(tmp_path)
    assert argv[argv.index("--sandbox") + 1] == "read-only"


def test_an_external_agent_without_a_card_does_not_run(operator_dir, workdir, codex_turns) -> None:
    (operator_dir / "AGENTS.md").unlink()
    spec = loader.parse_job_md(operator_dir)
    outcome = _run_external(spec, "Task: read")

    assert outcome.outcome == "blocked"
    assert "AGENTS.md is missing" in (outcome.error or "")
    assert codex_turns == []


# --- the guard reads the same text ---------------------------------------------

def _contract_section() -> str:
    text = CARD.read_text()
    start = text.index("## Contract")
    return text[start:text.index("\n## ", start + 1)].strip()


def test_the_browse_guard_is_given_the_cards_contract(monkeypatch) -> None:
    spec = loader.parse_job_md(OPERATOR_DIR)
    policy = runner._current_policy(spec)
    assert policy == _contract_section()
    assert "## Output" not in policy and "## Goal" not in policy

    asked: list[str] = []

    class Judge:
        async def run(self, text: str) -> Any:
            asked.append(text)
            return SimpleNamespace(output=SimpleNamespace(
                allow=True, read_only=True, bounded=True, reason="named pages"))

    monkeypatch.setattr(runner, "_browse_guard_agent", lambda: Judge())
    verdict = asyncio.run(runner._browse_guard_step("operator", policy, "Task: read"))
    assert verdict["allow"] is True
    assert _contract_section() in asked[0]


def test_the_browse_guard_states_the_real_risk() -> None:
    """The sandbox binds shell commands, not the browser: the guard must not
    be told the agent cannot click."""
    text = runner.BROWSE_GUARD_INSTRUCTIONS
    assert "It cannot" not in text and "sandbox is\nread-only" not in text
    assert "computer-use" in text and "only its shell" in text
    assert "contract" in text and "click" in text


@pytest.mark.parametrize(("task", "why"), [
    ("Find two people at a company on LinkedIn.", "names no page"),
    ("Read https://www.linkedin.com/messaging/thread/1 and report.", "send, post"),
    ("Open linkedin.com/mynetwork/invitation-manager/ and list them.", "send, post"),
    ("Read chrome://settings and report.", "not a public web address"),
    ("Read http://127.0.0.1:8000/admin and report.", "not a public web address"),
    ("Read up to 20 pages of https://example.com/blog.", "ceiling is 8"),
    ("Read " + " ".join(f"https://example.com/p{i}" for i in range(9)), "names 9 pages"),
    ("Read " + " ".join(f"https://www.linkedin.com/in/p{i}" for i in range(4)), "LinkedIn or X"),
])
def test_code_decides_what_text_can_settle_before_the_judge(task: str, why: str) -> None:
    problem = runner.browse_bounds_problem(task)
    assert problem is not None and why in problem


def test_the_real_briefs_pass_the_bounds_check() -> None:
    discovery = job_pipeline.discovery_brief(job_pipeline.discovery_payload(
        query="SDE-1", locations="India", max_roles=5))
    referral = job_pipeline.referral_brief(job_pipeline.referral_payload(
        job_id="1", company="Initech", role="SWE"))
    assert runner.browse_bounds_problem(discovery) is None
    assert runner.browse_bounds_problem(referral) is None
    assert runner.browse_bounds_problem(
        "Open https://www.linkedin.com/company/initech/people/ and name two engineers.") is None


def test_an_unbounded_task_never_reaches_the_judge() -> None:
    src = inspect.getsource(runner.await_runtime_approval)
    assert src.index("browse_bounds_problem(summary)") < src.index("_browse_guard_step(")


def test_the_guard_policy_is_truncated_to_its_limit(monkeypatch) -> None:
    asked: list[str] = []

    class Judge:
        async def run(self, text: str) -> Any:
            asked.append(text)
            return SimpleNamespace(output=SimpleNamespace(
                allow=False, read_only=True, bounded=False, reason="open-ended"))

    monkeypatch.setattr(runner, "_browse_guard_agent", lambda: Judge())
    asyncio.run(runner._browse_guard_step("operator", "x" * 10_000, "Task: read"))
    assert "x" * runner.GUARD_POLICY_CHARS in asked[0]
    assert "x" * (runner.GUARD_POLICY_CHARS + 1) not in asked[0]


def test_a_rule_saved_from_the_console_reaches_agent_and_guard(
    operator_dir, workdir, codex_turns,
) -> None:
    """PUT /agents/operator/policy still works: it writes policy.md, and that
    rule is appended to the card both the agent and the guard read."""
    from hq.api import agents_admin

    asyncio.run(agents_admin.update_agent_policy(
        "operator", agents_admin.PolicyBody(policy="- Never open Instagram.")))
    assert (operator_dir / "policy.md").exists()

    spec = loader.parse_job_md(operator_dir)
    policy = runner._current_policy(spec)
    assert policy.startswith(_contract_section())
    assert policy.endswith("## Owner's standing rules\n\n- Never open Instagram.")

    _run_external(spec, "Task: read")
    card = codex_turns[0]["card"]
    assert card.startswith(CARD.read_text().strip())
    assert "- Never open Instagram." in card


# --- one contract, one number set -------------------------------------------------

def test_the_card_is_the_only_operator_rule_text() -> None:
    assert not (OPERATOR_DIR / "policy.md").exists()
    spec = loader.parse_job_md(OPERATOR_DIR)
    assert "AGENTS.md" in spec.system_prompt
    assert len(spec.system_prompt.splitlines()) <= 3


def test_the_card_has_one_tab_rule_and_one_page_budget() -> None:
    text = " ".join(CARD.read_text().split())
    low = text.lower()

    assert "one working tab" in low
    assert "new tab" not in low and "every page" not in low
    # One page budget: the only counted page loads are "eight a run", and the
    # only social cap is three.
    assert re.findall(r"(\w+) page loads? a run", low) == ["eight"]
    assert re.findall(r"at most (\w+) of them on linkedin or x", low) == ["three"]
    assert re.findall(r"never more than (\w+)", low) == ["three"]
    for stale in ("three pages", "four", "ten seconds", "stop at eight", "not eight"):
        assert stale not in low
    # No dates and no history in a card the agent reads every run.
    assert not re.search(r"\b20\d\d-\d\d-\d\d\b", text)


def test_no_operator_brief_asks_for_a_new_tab() -> None:
    briefs = [
        job_pipeline.discovery_brief(job_pipeline.discovery_payload(
            query="", locations="", max_roles=5)),
        job_pipeline.referral_brief(job_pipeline.referral_payload(
            job_id="j", company="Acme", role="Engineer")),
        learning.feed_brief(learning.feed_payload(topics="agents")),
    ]
    for brief in briefs:
        assert "new tab" not in brief.lower()
        assert "one tab" in brief.lower()


# --- a reply with no source is not "done" -------------------------------------

@pytest.fixture
def events(monkeypatch) -> list[tuple[str, dict]]:
    seen: list[tuple[str, dict]] = []

    async def emit(kind: str, **kw: Any) -> None:
        seen.append((kind, kw.get("payload") or {}))

    monkeypatch.setattr(engine.runner, "emit_step", emit)
    return seen


def _done(text: str) -> runner.RunOutcome:
    return runner.RunOutcome(output=text, outcome="done", input_tokens=1,
                             output_tokens=1, cost_usd=0.0)


def _file(text: str, payload: object = None) -> runner.RunOutcome:
    spec = loader.parse_job_md(OPERATOR_DIR)
    return asyncio.run(engine._file_external_output(
        spec, "task-0000", "run-0000", _done(text), payload=payload))


def test_a_plain_reply_with_no_url_is_no_artifact(events) -> None:
    out = _file("I looked around and the page seemed empty.", payload={})
    assert out.outcome == "no_artifact"
    assert out.error == engine.UNSOURCED_REASON
    assert engine.exit_status(out.outcome, out.error) == "no_artifact"
    # run_task emits run.no_artifact once, with this reason; filing does not.
    assert events == []


@pytest.mark.parametrize("payload", [
    job_pipeline.discovery_payload(query="", locations="", max_roles=5),
    job_pipeline.referral_payload(job_id="j", company="Acme", role="Engineer"),
    learning.feed_payload(topics="agents"),
])
def test_an_envelope_task_with_no_url_stays_done(events, payload) -> None:
    """An empty envelope is a real answer, and the next stage must still run."""
    out = _file('Nothing new.\n```json\n{"missionhq_job_leads":[]}\n```', payload)
    assert out.outcome == "done"
    assert [kind for kind, _ in events] == ["external.unfiled"]


def test_a_sourced_reply_is_filed_to_quarantine(events, monkeypatch) -> None:
    written: list[str] = []

    async def write(rel: str, content: str, *, actor: str) -> None:
        written.append(rel)

    monkeypatch.setattr(engine.memory, "write", write)
    out = _file("The people page https://www.linkedin.com/company/acme/people/ lists two.")
    assert out.outcome == "done"
    assert written and written[0].startswith("quarantine/")
    assert "Filed to quarantine/" in out.output
