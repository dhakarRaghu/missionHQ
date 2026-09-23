"""Stalls in code, one owner-facing voice, the right injection question."""

from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace

import pytest
from pydantic_ai import ModelRetry

from hq.tools import registry
from hq.tools.registry import HQDeps


def test_a_third_identical_call_is_refused_and_counted() -> None:
    calls = []

    async def tool(ctx, query: str) -> str:
        calls.append(query)
        return "same answer"

    audited = registry._audited("probe", tool)
    ctx = SimpleNamespace(deps=HQDeps(agent="hunter", run_id="run-x"))
    try:
        assert asyncio.run(audited(ctx, "q")) == "same answer"
        assert asyncio.run(audited(ctx, "q")) == "same answer"
        assert registry.run_repeats("run-x") == 1
        with pytest.raises(ModelRetry, match="will not change"):
            asyncio.run(audited(ctx, "q"))
        assert asyncio.run(audited(ctx, "other")) == "same answer"  # new args are fine
        assert calls == ["q", "q", "other"]
    finally:
        registry.forget_run("run-x")
    assert registry.run_repeats("run-x") == 0


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
