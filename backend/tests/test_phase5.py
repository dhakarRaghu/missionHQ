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
    assert "fn=_repeat_gated(tool_name, stepped, private=private)" in inspect.getsource(registry)
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


def test_a_posts_batch_goes_on_top_and_keeps_the_rest() -> None:
    from hq.tools import content_tools as ct

    old = "---\ncreated: 2026-09-16\n---\n# Content ideas\n\n## 2026-09-16 — Old\n\n- old idea\n  why: x\n"
    new = ct.with_batch(old, "## 2026-09-23 stray heading\nfirst post\n\n---\n\nsecond post\n",
                        "2026-09-23", "Evening")
    assert new.startswith("---\ncreated: 2026-09-16\n---\n# Content ideas\n\n## 2026-09-23 — Evening")
    assert new.index("first post") < new.index("## 2026-09-16 — Old") < new.index("old idea")
    assert "stray heading" not in new


def test_a_post_is_filed_only_in_his_voice() -> None:
    from hq.tools import content_tools as ct

    good = ("I was reading how vLLM handles a long prompt last week. It doesn't run the whole"
           " prompt in one step. It cuts it into chunks and mixes them with decode steps, so a"
           " short request doesn't wait behind a 24,000-token one. I think that's the part most"
           " people miss when they only watch average latency. I'd rather read the tail than"
           " the mean, because the tail is where the waiting shows.")
    assert ct.post_problems(good) == []
    notes = ("A cost-tracking tool recorded $0.238 for a run the provider billed at $0.522."
             " The tool did not count the cached input tokens, and it did not count the"
             " reasoning tokens either, so the gap grows with every long agent run."
             " why: Langfuse issue 13807, verified by hunter. Sources: quarantine/x-study.md")
    probs = " ".join(ct.post_problems(notes))
    assert "private words" in probs and "file path" in probs and "contraction" in probs
    posts = ct.split_posts("## heading\n" + "\n\n---\n\n".join([good] * 6))
    assert len(posts) == 6 and ct.count_problem(posts, ["s"] * 6) is None
    assert ct.gate(posts) == {n: [] for n in range(1, 7)}
    assert ct.count_problem([good], ["s"])   # one post is not a batch of candidates



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


def test_every_wait_fits_inside_the_cap_that_would_cancel_it() -> None:
    from types import SimpleNamespace

    from hq import learning_pipeline as learning
    from hq import llm, runner
    from hq.config import settings

    one_call = float(llm.registry().model_settings_for("deep").get("timeout") or 0)
    assert one_call >= 900
    # A tool approval, then one full call of the deep model, inside a task.
    assert runner.APPROVAL_TIMEOUT_S + one_call <= engine.TASK_TIMEOUT_S
    # A chat turn fits one full call and an approval wait.
    assert engine.CHAT_TIMEOUT_S >= one_call + runner.APPROVAL_TIMEOUT_S
    # A browser run's approval wait leaves room for the run and its guards.
    wait = runner.runtime_approval_wait_s(SimpleNamespace(runtime="codex"))
    assert wait + settings().codex_timeout_s + 2 * runner.JUDGE_LIMIT_S <= engine.TASK_TIMEOUT_S
    for stage in (learning.LAB_CARD_STAGE, learning.WEEK_REVIEW_STAGE, learning.POST_STAGE):
        assert engine.lane_for({"stage": stage}) == "courses"


def test_a_cron_slot_starts_with_its_skill_in_the_brief() -> None:
    from hq.loader import scan

    sage = scan()["sage"]
    assert {e.skill for e in sage.cron} >= {"daily-note", "consolidate", "daily-posts"}
    assert not any("load_skill" in e.prompt for e in sage.cron)
    brief = asyncio.run(engine._cron_brief_step.__wrapped__("sage", "Write today's daily note.",
                                                            "daily-note"))
    assert brief.startswith("Write today's daily note.") and "## The daily-note skill" in brief


def test_briefs_built_by_code_state_rules_not_history() -> None:
    """A dated incident in a prompt is history the model reads as a rule."""
    import ast
    import re

    from hq import job_pipeline
    from hq import learning_pipeline as learning

    for mod in (learning, job_pipeline):
        tree = ast.parse(inspect.getsource(mod))
        for node in ast.walk(tree):
            if isinstance(node, ast.JoinedStr):
                for part in node.values:
                    if isinstance(part, ast.Constant) and isinstance(part.value, str):
                        for line in part.value.splitlines():
                            if '{"' in line:
                                continue  # an example envelope, where a date is a field
                            assert not re.search(r"\b20\d\d-\d\d-\d\d\b", line), (
                                mod.__name__, node.lineno, line)


def test_an_operator_report_is_redacted_not_dropped(monkeypatch) -> None:
    from hq import privacy
    from hq.config import settings

    monkeypatch.setattr(settings(), "private_employers", ("Acme Corp",))
    privacy._pattern.cache_clear()
    out = privacy.redact("Referral at ACME corp and acme-corp.com; Acmeology stays.")
    assert privacy.employers_named(out) == []
    assert "Acmeology stays" in out and out.count(privacy.REDACTED) == 2
    assert "privacy.redact(" in inspect.getsource(engine._file_external_output)


def test_an_offline_machine_defers_the_task_instead_of_failing_it() -> None:
    src = inspect.getsource(engine.run_task) if hasattr(engine, "run_task") else ""
    src = src or inspect.getsource(engine)
    assert "_defer_if_offline_step(task_id, run_id)" in src
    assert "APIConnectionError" in engine._UNREACHABLE
    # the reconciler honours not_before, so a deferred task waits its turn
    assert "not_before <= now()" in inspect.getsource(engine._orphaned_backlog_step)


def test_a_browser_run_has_its_own_lane() -> None:
    assert engine.lane_for({"workflow": "job_search", "stage": "browser_discovery"},
                           "operator") == "browser"
    assert engine.lane_for({"stage": "hunter_verification"}, "hunter") == "tasks"
    src = inspect.getsource(engine.bootstrap_post_launch)
    assert '"browser", worker_concurrency=1' in src


def test_a_pipeline_stage_is_judged_by_its_own_contract_not_its_wording() -> None:
    brief = "What makes an incident writeup worth reading. Write the note to quarantine/x.md."
    assert engine.expects_artifact(brief)
    assert engine.artifact_expected(brief, {"workflow": "learning_journey",
                                            "stage": "reading_scan"}) is False
    assert engine.artifact_expected(brief, {}) is True
    assert engine.artifact_expected(brief, None) is True


def test_a_browser_that_could_not_be_driven_is_tried_again_later() -> None:
    from hq import board, runner

    assert "retry_later" in runner.RunOutcome.__dataclass_fields__
    assert "retry_later=True" in inspect.getsource(runner)
    src = inspect.getsource(engine)
    assert '_defer_step(task_id, "deferred_browser", BROWSER_RETRIES)' in src
    # blocked -> backlog is a legal move, so the deferral can land
    assert "backlog" in board.ALLOWED["blocked"]


def test_a_study_note_cannot_be_written_as_a_tool_argument() -> None:
    from types import SimpleNamespace

    from pydantic_ai import ModelRetry as Retry

    from hq.tools import vault_tools

    ctx = SimpleNamespace(deps=HQDeps(agent="hunter", run_id=None, task_id=None,
                                      vault_write_scopes=["quarantine/**"]))
    with pytest.raises(Retry, match="file_study_note"):
        asyncio.run(inspect.unwrap(vault_tools.vault_write)(
            ctx, "quarantine/2026-09-24-x-study.md", "# x\n"))


def test_a_stopped_task_asked_for_again_runs_again() -> None:
    src = inspect.getsource(engine.dispatch)
    assert 'status in ("blocked", "failed")' in src and '"retried"' in src


def test_the_deadman_claim_is_one_statement() -> None:
    src = inspect.getsource(engine._deadman_due)
    assert "RETURNING key" in src and "SELECT value" not in src


def test_a_cron_slot_can_name_the_tool_its_run_must_call() -> None:
    from hq.loader import scan

    posts = next(e for e in scan()["sage"].cron if e.skill == "daily-posts")
    assert posts.requires == "file_posts"
    assert engine.artifact_expected("Write today's posts.", {"requires": "file_posts"}) is True
    assert "file_posts" in engine.ARTIFACT_TOOLS


def test_a_post_may_not_claim_an_agents_work_as_his() -> None:
    from hq.tools import content_tools as ct

    post = ("I checked the company's careers page before applying and the role wasn't there."
            " I don't think half the listings are real. I'd rather verify than write an"
            " application to a ghost. It's one minute of work, and it keeps saving me hours.")
    assert any("claims work an agent did" in p for p in ct.post_problems(post))
    fixed = post.replace("I checked", "My job sweep checked")
    assert not any("claims work" in p for p in ct.post_problems(fixed))


def test_a_correct_no_change_run_is_not_empty_handed() -> None:
    from hq.loader import scan

    entries = {e.skill: e.requires for e in scan()["sage"].cron}
    assert entries["consolidate"] == "none" and entries["job-shortlist"] == "file_shortlist"
    assert engine.artifact_expected("Consolidate today's notes into memory. Write one"
                                    " proposal note to memory/proposals/x.md",
                                    {"requires": "none"}) is False


def test_a_post_may_not_promise_a_future_action() -> None:
    from hq.tools import content_tools as ct

    post = ("I'm going to rewrite my cost meter tonight. I don't think it counts cached"
            " tokens right. I'd rather fix it than trust it. It's been wrong for a week"
            " and nobody noticed, which is the part that bothers me the most right now.")
    assert any("promises a future action" in p for p in ct.post_problems(post))


def test_a_long_source_is_not_cut_to_forty_thousand() -> None:
    from hq.tools import web_tools

    html = "<p>" + "word " * 60_000 + "</p>"
    assert len(web_tools._strip_html(html, web_tools.SOURCE_MAX_CHARS)) > web_tools.MAX_CHARS
    assert len(web_tools._strip_html(html)) == web_tools.MAX_CHARS


def test_backfilled_ticks_do_nothing_and_a_sleep_requeues_silent_runs() -> None:
    from datetime import UTC, datetime, timedelta

    assert asyncio.run(engine._backfilled(datetime.now(UTC) - timedelta(minutes=10))) is True
    assert asyncio.run(engine._backfilled(datetime.now(UTC) - timedelta(seconds=20))) is False
    src = inspect.getsource(engine._cap_overrunning_tasks)
    assert '"requeued_after_sleep", status="backlog"' in src
    assert "_backfilled(scheduled)" in inspect.getsource(engine._drain_outbox_tick)
