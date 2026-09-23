"""Stalls in code, one owner-facing voice, the right injection question."""

from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace

import pytest
from pydantic_ai import ModelRetry

from hq import engine
from hq.tools import registry
from hq.tools.registry import HQDeps


def test_a_third_identical_call_is_refused_and_counted() -> None:
    calls = []

    async def tool(ctx, query: str) -> str:
        calls.append(query)
        return "same answer"

    gated = registry._repeat_gated("probe", tool)
    ctx = SimpleNamespace(deps=HQDeps(agent="hunter", run_id="run-x"))
    try:
        assert asyncio.run(gated(ctx, "q")) == "same answer"
        assert asyncio.run(gated(ctx, "q")) == "same answer"
        assert registry.run_repeats("run-x") == 1
        with pytest.raises(ModelRetry, match="will not change"):
            asyncio.run(gated(ctx, "q"))
        assert asyncio.run(gated(ctx, "other")) == "same answer"  # new args are fine
        assert calls == ["q", "q", "other"]
    finally:
        registry.forget_run("run-x")
    assert registry.run_repeats("run-x") == 0


def test_the_repeat_gate_sits_outside_the_retried_step() -> None:
    """A refusal inside a retried step was retried like a network error."""
    assert "fn=_repeat_gated(tool_name, stepped)" in inspect.getsource(registry)
    assert "note_call" not in inspect.getsource(registry._audited)


def test_the_judge_is_asked_only_when_a_run_repeated_itself() -> None:
    from hq import runner

    src = inspect.getsource(runner._execute)
    gate = src.index("registry.run_repeats(deps.run_id) == 0")
    assert gate < src.index("_ledger_check_step(")
    assert "registry.forget_run(deps.run_id)" in inspect.getsource(runner.execute)


def test_his_phone_hears_from_the_engine_only_when_a_run_did_not_succeed() -> None:
    from hq import engine

    src = inspect.getsource(engine.run_task)
    assert 'task["source"] == "cron" and result != "done"' in src


def test_documentation_about_prompts_is_not_an_injection() -> None:
    from hq.tools import web_tools

    field = web_tools.PageFacts.model_fields["contains_instructions"].description or ""
    assert "addresses the AI agent reading it" in field
    assert "is false" in field


def test_a_deploy_does_not_orphan_a_run_in_flight() -> None:
    """DBOS recovers only workflows of the running code version; a run the
    deploy stopped is cancelled, costed and queued again at boot."""
    from hq import board, engine

    src = inspect.getsource(engine.reap)
    assert "application_version IS DISTINCT FROM" in src and "w.status = 'PENDING'" in src
    assert "CALLS_COSTED" in src and "requeued_after_deploy" in src
    assert "backlog" in board.ALLOWED["blocked"] and "blocked" in board.ALLOWED["running"]


def test_a_post_is_refused_for_private_words_not_for_words_containing_them() -> None:
    from hq.tools.learning_tools import post_problems

    clean = "Token usage matters. This tutorial shows the message path. " * 60
    assert "private notes" not in post_problems(clean, "")
    leaky = clean + " The tutor agent wrote this from a study note."
    assert "tutor" in post_problems(leaky, "") and "study note" in post_problems(leaky, "")


def test_a_refusal_is_not_retried_as_a_network_failure() -> None:
    assert registry._worth_retrying(ModelRetry("fix the args")) is False
    assert registry._worth_retrying(PermissionError("blocked host")) is False
    assert registry._worth_retrying(ConnectionError("reset")) is True


def test_a_model_call_counts_as_a_sign_of_life() -> None:
    """The staged writer calls models with no tool events between them."""
    src = inspect.getsource(engine._cap_overrunning_tasks)
    assert src.count("hq.model_calls") == 2


def test_an_ideas_batch_goes_on_top_and_keeps_the_rest() -> None:
    from hq.tools import content_tools as ct

    old = "---\ncreated: 2026-09-16\n---\n# Content ideas\n\n## 2026-09-16 — Old\n\n- old idea\n  why: x\n"
    new = ct.with_batch(old, "## 2026-09-23 stray heading\nIntro line.\n\n- new idea\n  why: y\n",
                        "2026-09-23", "Morning batch")
    assert new.startswith("---\ncreated: 2026-09-16\n---\n# Content ideas\n\n## 2026-09-23 — Morning batch")
    assert new.index("new idea") < new.index("## 2026-09-16 — Old") < new.index("old idea")
    assert "stray heading" not in new
    assert ct.with_batch(None, "- a\n", "2026-09-23", "").startswith("# Content ideas\n\n## 2026-09-23\n")
    assert ct.batch_problems("no bullets here")
    assert ct.batch_problems("- one\n  why: x\n- two\n") == []
    assert ct.batch_problems("\n".join(f"- {i}" for i in range(9)))


def test_the_digest_carries_the_daily_note(tmp_path, monkeypatch) -> None:
    from datetime import UTC, datetime

    from hq import digest, memory

    def fake_read(rel: str) -> str:
        assert rel == "daily/2026-09-23.md"
        return "---\ncreated: 2026-09-23\n---\n# Wednesday\n\n**Needs you:** pick a phase.\n"

    monkeypatch.setattr(memory, "read", fake_read)
    note = digest._daily_note(datetime(2026, 9, 23, 17, 20, tzinfo=UTC))
    assert note == "Wednesday\n\nNeeds you: pick a phase."
    assert (engine.DIGEST_HOUR, engine.DIGEST_MINUTE) > (22, 30)  # after sage's 22:30 note


def test_one_reindex_a_night_whichever_path_starts_it() -> None:
    src = inspect.getsource(engine._watchdog_tick) + inspect.getsource(engine._reindex_vault_tick)
    assert "memory.reindex_all" not in src
    assert "_nightly_reindex" in inspect.getsource(engine._reindex_vault_tick)
    assert "IS DISTINCT FROM" in inspect.getsource(engine._claim_reindex_step)
