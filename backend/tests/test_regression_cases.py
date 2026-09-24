"""Binary regression cases, one per real failure, run against the gates in code.

No model is called. Each case is the incident's input, given to the exact
function that now refuses or routes it, and one assertion. The docstring of
each test is the incident: its date and what happened, nothing more. The
model-backed set (hq.regress, evals/regression/*.yaml) measures what the
agents do with these gates in place; this file measures the gates.
"""

from __future__ import annotations

import asyncio
import inspect
from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError
from pydantic_ai import ModelRetry

from hq import engine, job_pipeline, privacy, runner, safety
from hq import lesson_writer as lw
from hq.config import settings
from hq.tools import content_tools as ct
from hq.tools import job_tools, vault_tools
from hq.tools import learning_tools as lt
from hq.tools.registry import HQDeps

# --- fixtures ---------------------------------------------------------------

NOTE = """---
source_urls:
- https://ex.dev/orca
---
# Orca, study note

Iteration-level scheduling returns a finished request at the end of the
iteration it finished in. Measured on GPT-3 175B, Orca served 36.9x the
throughput of FasterTransformer at the same latency. A KV cache is read once
per token, so the read multiplier is 0.1x of the base input price.
"""

QUOTE = "Orca served 36.9x the throughput of FasterTransformer"


def _concept(cid: str = "c1", claim: str | None = None) -> dict[str, Any]:
    return {
        "id": cid,
        "claim": claim or "A batch rebuilt every iteration never makes a short request wait",
        "lets_him": "predict tail latency under mixed lengths",
        "wrong_belief": "batching always adds wait",
        "predict": "A short and a long request share a batch. When does the short one return?",
        "evidence": "36.9x throughput over FasterTransformer at the same latency",
        "evidence_quote": QUOTE,
        "picture": "a timeline of iterations",
    }


def _plan(concepts: list[dict[str, Any]]) -> dict[str, Any]:
    teaching = [{"heading": f"What {c['id']} changes", "concept": c["id"], "covers": "the idea"}
                for c in concepts]
    return {
        "title": "Why does a short request stop waiting for a long one",
        "subtitle": "What changes when the batch is rebuilt every iteration",
        "eyebrow": "paper",
        "outcome": "Predict when a request returns in a mixed batch",
        "opening": "Your chat endpoint is fast alone and slow under load.",
        "concepts": concepts,
        "sections": teaching + [{"heading": "Sources", "kind": "sources", "covers": "the urls"}],
    }


def _words(n: int, word: str = "word") -> str:
    return " ".join([word] * n)


def _section(html: str, **kw: Any) -> list[str]:
    base: dict[str, Any] = {"earlier": "", "article": True, "kind": "", "apparatus": False,
                            "total_words": 0}
    return lw.section_problems(html, **{**base, **kw})


def _ctx(agent: str = "hunter", **deps: Any) -> SimpleNamespace:
    return SimpleNamespace(deps=HQDeps(agent=agent, run_id=None, task_id=None, **deps))


@pytest.fixture
def employer(monkeypatch) -> str:
    monkeypatch.setattr(settings(), "private_employers", ("Acmecorp",))
    privacy._pattern.cache_clear()
    yield "Acmecorp"
    privacy._pattern.cache_clear()


# --- the plan ---------------------------------------------------------------

def test_a_one_concept_article_plan_with_three_concepts_is_refused() -> None:
    """2026-09-24: the article plan came back with three concepts on two of three tries."""
    three = [_concept("c1"), _concept("c2"), _concept("c3")]
    outline = lw.Outline.model_validate(_plan(three))
    probs = lw.outline_problems(outline, NOTE, article=True)
    assert any("3 concepts" in p and "exactly one" in p for p in probs)


def test_the_article_schema_cannot_carry_a_concept_list() -> None:
    """2026-09-24: a plan with a concepts list was accepted by the schema and refused later."""
    plan = _plan([_concept("c1"), _concept("c2")])
    with pytest.raises(ValidationError):
        lw.ArticleOutline.model_validate(plan)
    one = lw.ArticleOutline.model_validate(
        {k: v for k, v in plan.items() if k != "concepts"} | {"concept": _concept("c9")})
    assert [c.id for c in one.as_outline().concepts] == ["c1"]


def test_a_41_word_claim_is_refused() -> None:
    """2026-09-24: a claim ran to a paragraph and the section had nothing left to say."""
    long_claim = _words(41, "batch")
    outline = lw.Outline.model_validate(_plan([_concept(claim=long_claim)]))
    probs = lw.outline_problems(outline, NOTE, article=True)
    assert any("claim is 41 words" in p for p in probs)


def test_a_33_word_claim_is_not_refused() -> None:
    """2026-09-24: the claim wall sits past the 20-word target, at 40, not on it."""
    claim = _words(33, "batch")
    outline = lw.Outline.model_validate(_plan([_concept(claim=claim)]))
    probs = lw.outline_problems(outline, NOTE, article=True)
    assert not any("claim is" in p for p in probs)


# --- the parts --------------------------------------------------------------

def test_restatement_over_the_ceiling_on_a_part_is_refused() -> None:
    """2026-09-24: parts that each passed added up to 14% restatement on a 12% page."""
    body = "<p>" + "The scheduler rebuilds the batch every step. " * 30 + "</p>"
    heavy = ('<h2 data-concept="c1">Why?</h2><p class="why">' + "It matters because. " * 20
             + "</p>" + body + '<div class="keypoints"><p>'
             + "Rebuild the batch every step. " * 12 + "</p></div>")
    assert any("the lead and the key points here" in p for p in _section(heavy))


def test_an_apparatus_part_with_key_points_is_refused() -> None:
    """2026-09-24: a lab section carried a key-point box, and the page counted it twice."""
    lab = ('<h2 data-kind="lab">Fifteen minutes today</h2><div class="keypoints"><p>Rebuild'
           ' the batch.</p></div><p>Run the simulator once with two lengths.</p>')
    assert any("apparatus section has no lead and no key-point box" in p
               for p in _section(lab, apparatus=True))


def test_a_page_over_2600_words_routes_the_cut_to_the_parts_most_over_budget() -> None:
    """2026-09-24: the first live article reached 4,047 words and every part was rewritten."""
    w = lw.Writer(SimpleNamespace(), HQDeps(agent="tutor"), SimpleNamespace())
    w.budgets = {1: 300, 2: 300, 3: 300}
    w.parts = ["<p>opening</p>", f"<p>{_words(600)}</p>", f"<p>{_words(290)}</p>",
               f"<p>{_words(420)}</p>"]
    message = (f"the article is 2900 words, which is about 14 minutes; past"
               f" {lt.ARTICLE_MAX_WORDS} it is carrying a second idea or a survey")
    assert w._over_budget(message) == [1, 3]
    assert w._over_budget("the article is not ready yet: c1 has nothing to look at") == []


def test_a_plainness_measure_ignores_a_sources_list() -> None:
    """2026-09-24: the page scored a sources list at 33 words a sentence; the part did not."""
    source_line = ("Orca: A Distributed Serving System for Transformer-Based Generative Models,"
                   " Yu et al, OSDI 2022, read for the iteration-level scheduling figure and"
                   " the throughput table on page nine of the paper as published.")
    html = ('<h2 data-concept="c1">Q</h2><p>The batch is rebuilt every step. A short request'
            ' leaves when it is done. Nothing waits for the longest one.</p>'
            f'<ul class="sources"><li>{source_line}</li></ul>')
    prose = lt.teaching_prose(html)
    assert "Distributed Serving" not in prose and "rebuilt every step" in prose
    assert lt.reading_ease(prose)[0] < lt.reading_ease(lt._page_text(html))[0]


def test_a_lab_command_not_in_his_lab_is_refused_on_the_part() -> None:
    """2026-09-23: the lab card carried a command with flags nobody had run."""
    source = "**E1** Run: `python phase02/sim.py --turns 4`\n"
    part = ('<h2 data-kind="lab">Lab</h2><ul class="exercises"><li><b>E1</b> Run: '
            '<code>python phase02/sim.py --turns 12 --inject-overflow 5</code></li></ul>')
    assert any("not in his lab" in p
               for p in _section(part, article=False, apparatus=True, source=source))


def test_a_lab_command_copied_exactly_passes() -> None:
    """2026-09-23: the fidelity rule must let his own command through unchanged."""
    source = "**E1** Run: `python phase02/sim.py --turns 4`\n"
    part = ('<h2 data-kind="lab">Lab</h2><ul class="exercises"><li><b>E1</b> Run: '
            '<code>python phase02/sim.py --turns 4</code></li></ul>')
    assert lt.lab_fidelity_problems(part, source) == []


def test_a_verification_date_in_a_teaching_sentence_is_caught_on_its_part() -> None:
    """2026-09-23: 'verified on 2026-09-23' sat in a teaching sentence and failed the page."""
    html = ('<h2 data-concept="c1">Q</h2><p>The read multiplier is 0.1x of the base input'
            ' price, verified on 2026-09-23 against the pricing page today.</p>')
    assert any("carries a date" in p for p in _section(html))


def test_a_checked_on_date_in_the_sources_is_not_a_teaching_sentence() -> None:
    """2026-09-23: the date belongs in the sources, so the sources part must keep it."""
    html = ('<h2 data-kind="sources">Sources</h2><ul class="sources"><li>The pricing page,'
            ' checked on 2026-09-23 for the cache read multiplier figure.</li></ul>')
    assert not any("carries a date" in p for p in _section(html, apparatus=True))


def test_a_quantity_like_2048_is_not_a_year() -> None:
    """2026-09-24: Phase 2B was refused for naming a year on its 2048-token default."""
    assert lt._YEAR_RE.search("The context window defaults to 2048 tokens per request.") is None
    assert lt._YEAR_RE.search("The 2000 ms timeout is the client's.") is None
    assert lt._YEAR_RE.search("In 2019 the paper measured 36.9x.") is not None


# --- posts ------------------------------------------------------------------

GOOD_POST = ("I broke my own cost meter last week. It said a run cost $0.24 and the bill said"
             " $0.52. I don't think the meter was wrong. It was counting one provider's shape"
             " and my agents talk to two. I'd rather see a wrong number I can explain than a"
             " right one I can't. So I'm printing the raw usage object from every call this"
             " week and reading it myself.")


def test_a_post_in_his_register_passes() -> None:
    """2026-09-24: the register gate must let his own kind of post through."""
    assert ct.post_problems(GOOD_POST) == []


@pytest.mark.parametrize(("tail", "named"), [
    pytest.param(" why: the meter counted one shape.", "note label", id="why"),
    pytest.param(" Sources: the provider's bill.", "note label", id="sources"),
    pytest.param(" The note is in quarantine/2026-09-20-cost-study.md", "file path", id="path"),
    pytest.param(" hunter found the second provider.", "private words", id="agent-name"),
    pytest.param(" The thread is at https://x.com/me/status/1", "a link", id="link"),
    pytest.param(" I checked the board twice.", "claims work an agent did", id="i-checked"),
    pytest.param(" I'm going to fix the meter tonight.", "promises a future action",
                 id="promise"),
])
def test_a_post_carrying_what_a_post_never_carries_is_refused(tail: str, named: str) -> None:
    """2026-09-24: the retired scout's posts became notes with why/Sources lines and paths."""
    assert any(named in p for p in ct.post_problems(GOOD_POST + tail))


# --- the vault --------------------------------------------------------------

def test_a_study_note_path_cannot_be_written_through_vault_write() -> None:
    """2026-09-24: hunter rewrote a filed 13k-character study note through vault_write."""
    ctx = _ctx("hunter", vault_write_scopes=["quarantine/**"])
    with pytest.raises(ModelRetry, match="file_study_note"):
        asyncio.run(inspect.unwrap(vault_tools.vault_write)(
            ctx, "quarantine/2026-09-24-orca-study.md", "# Orca\n"))


# --- the artifact assertion -------------------------------------------------

def test_a_consolidation_with_requires_none_is_not_empty_handed() -> None:
    """2026-09-24: a correct no-change consolidation was blocked as empty-handed."""
    brief = "Consolidate memory: append what changed to memory/agents/librarian.md."
    assert engine.artifact_expected(brief, {"requires": "none"}) is False


def test_a_posts_run_without_file_posts_is_empty_handed() -> None:
    """2026-09-24: sage said the posts were filed and no file_posts call was on record."""
    brief = "Write today's posts."
    assert engine.artifact_expected(brief, {"requires": "file_posts"}) is True
    assert "file_posts" in engine.ARTIFACT_TOOLS


def test_a_pipeline_stage_is_judged_by_its_stage_not_its_briefs_wording() -> None:
    """2026-09-24: a reading scan whose brief said 'writeup' returned four leads and was blocked."""
    brief = "What makes an incident writeup worth reading. Write the note to quarantine/x.md."
    assert engine.expects_artifact(brief) is True
    assert engine.artifact_expected(
        brief, {"workflow": "learning_journey", "stage": "reading_scan"}) is False


# --- the job pipeline -------------------------------------------------------

def test_a_lead_at_a_private_employer_is_dropped(employer: str) -> None:
    """2026-09-24: a discovery envelope carried a role at his own employer into hunter's brief."""
    envelope = (
        '{"missionhq_job_leads": ['
        f'{{"company": "{employer}", "role": "SDE", "posting_url": "https://x.example/1"}},'
        '{"company": "Globex", "role": "SDE", "posting_url": "https://x.example/2"}]}'
    )
    leads = job_pipeline.extract_discovery_leads(envelope)
    assert [lead["company"] for lead in leads] == ["Globex"]


def test_a_five_year_floor_is_at_or_over_the_ceiling() -> None:
    """2026-09-10: the sweep recorded roles asking 5+ years as open."""
    assert job_tools.min_years_required("5-8 years") == 5.0
    assert job_tools.min_years_required("5+ yrs") >= settings().job_max_min_years


def test_a_lead_title_is_senior_and_an_entry_mts_title_is_not() -> None:
    """2026-09-10 and 2026-09-12: three of four recorded roles were manager or lead; MTS 1 was closed."""
    assert job_tools.senior_title("Lead AI Engineer") == "lead"
    assert job_tools.senior_title("SDE II") is not None
    assert job_tools.senior_title("Member of Technical Staff 1") is None


def test_an_intern_title_is_junior_and_internal_tools_is_not() -> None:
    """2026-09-12: an internship was scored as a move for someone already employed."""
    assert job_tools.intern_title("Software Engineer Intern") == "intern"
    assert job_tools.intern_title("Internal Tools Engineer") is None


def test_record_job_closes_a_role_with_a_five_year_floor(monkeypatch) -> None:
    """2026-09-10: the sweep filed a 5+ years role as open and he was asked about it."""
    written: list[tuple] = []

    async def fetch(sql: str, params: tuple = ()) -> list[dict]:
        written.append(params)
        return [{"id": "job-1", "seen_count": 1, "status": params[17]}]

    async def fetchone(sql: str, params: tuple = ()) -> dict | None:
        return None

    async def emit(kind: str, **kw: Any) -> int:
        return 1

    monkeypatch.setattr(job_tools.db, "fetch", fetch)
    monkeypatch.setattr(job_tools.db, "fetchone", fetchone)
    monkeypatch.setattr(job_tools, "emit", emit)
    asyncio.run(inspect.unwrap(job_tools.record_job)(
        _ctx(), "Globex", "Backend Engineer", "https://globex.example/jobs/1",
        why_fit="Go backend, but the floor is five years", experience_band="5-8 years"))
    status, note = written[-1][17], written[-1][18]
    assert status == "closed" and "5+ years" in note


def test_a_rediscovery_with_no_years_keeps_the_stated_band() -> None:
    """2026-09-24: a role closed on '5-10 years' was re-read from a feed and rescored 10."""
    assert job_tools.strongest_band("", "5-10 years stated in posting") == (
        "5-10 years stated in posting")
    assert job_tools.strongest_band("no floor visible", "5-10 years") == "5-10 years"
    assert job_tools.strongest_band("2-4 years", "5-10 years") == "2-4 years"


# --- the engine -------------------------------------------------------------

def test_a_blocked_or_failed_task_asked_for_again_is_retried() -> None:
    """2026-09-24: a study that failed was handed back night after night under one dedup key."""
    src = inspect.getsource(engine.dispatch)
    assert 'status in ("blocked", "failed")' in src
    assert '"retried"' in src and 'status="backlog"' in src


def test_the_deadman_claim_is_one_statement() -> None:
    """2026-09-24 05:14: ~30 backfilled watchdog ticks each passed a read-then-write guard."""
    src = inspect.getsource(engine._deadman_due)
    assert src.count("await db.") == 1
    assert "ON CONFLICT" in src and "RETURNING" in src


def test_the_notification_budget_counts_outbox_rows() -> None:
    """2026-09-24: thirty alarm events in one second counted as thirty sends."""
    src = inspect.getsource(safety.notifications_sent_today)
    assert "hq.outbox" in src and "hq.events" not in src


def test_a_browser_that_could_not_be_driven_is_deferred_not_blocked(monkeypatch) -> None:
    """2026-09-24: the CLI answered with no browser attached and the run was filed as done."""
    async def turn(prompt: str, **kw: Any) -> dict[str, Any]:
        return {"text": "The browser extension is not connected, so I read nothing.",
                "input_tokens": 10, "output_tokens": 5, "cost_usd": 0.01, "is_error": False}

    monkeypatch.setattr(runner.claude_cli, "available", lambda: None)
    monkeypatch.setattr(runner, "agent_card", lambda spec: "the card")
    monkeypatch.setattr(runner, "claude_turn_step", turn)
    spec = SimpleNamespace(runtime="claude", name="operator")
    out = asyncio.run(runner._execute_external(
        spec, prompt="read the board", deps=HQDeps(agent="operator", run_id="r1", task_id="t1")))
    assert out.outcome == "blocked" and out.retry_later is True
    assert "deferred_browser" in inspect.getsource(engine.run_task)


def test_a_task_whose_model_calls_all_failed_to_connect_is_deferred(monkeypatch) -> None:
    """2026-09-24: the Mac was off the network and the task failed instead of waiting."""
    rows: list[dict[str, Any]] = []

    async def fetch(sql: str, params: tuple = ()) -> list[dict]:
        return rows

    monkeypatch.setattr(engine.db, "fetch", fetch)
    rows[:] = [{"error_class": "ConnectError"}, {"error_class": "APIConnectionError"},
               {"error_class": "ConnectTimeout"}]
    assert asyncio.run(engine._unreachable_step("run-1")) is True
    rows[:] = [{"error_class": "ConnectError"}, {"error_class": "ConnectError"},
               {"error_class": "RateLimitError"}]
    assert asyncio.run(engine._unreachable_step("run-1")) is False
    rows[:] = [{"error_class": "ConnectError"}, {"error_class": "ConnectError"}]
    assert asyncio.run(engine._unreachable_step("run-1")) is False


def test_a_backfilled_watchdog_tick_does_nothing() -> None:
    """2026-09-25: the host woke and fifteen backfilled watchdog ticks blocked one task at once."""
    from datetime import UTC, datetime, timedelta

    now = datetime.now(UTC)
    assert asyncio.run(engine._backfilled(now - timedelta(minutes=10))) is True
    assert asyncio.run(engine._backfilled((now - timedelta(minutes=10)).replace(tzinfo=None)))
    assert asyncio.run(engine._backfilled(now - timedelta(seconds=20))) is False
    assert "_backfilled(scheduled)" in inspect.getsource(engine._watchdog_tick)
