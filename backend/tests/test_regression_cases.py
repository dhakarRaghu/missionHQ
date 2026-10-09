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

GOOD_POST = ("I was reading how vLLM handles a long prompt last week. It doesn't run the whole"
            " prompt in one step. It cuts it into chunks and mixes them with decode steps, so a"
            " short request doesn't wait behind a 24,000-token one. I think that's the part most"
            " people miss when they only watch average latency. I'd rather read the tail than"
            " the mean, because the tail is where the waiting shows.")


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
        if sql.lstrip().upper().startswith("SELECT"):
            return []  # a read, such as the earlier-row lookup: there is none
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

    monkeypatch.setattr(runner.codex_cli, "available", lambda: None)
    monkeypatch.setattr(runner, "agent_card", lambda spec: "the card")
    monkeypatch.setattr(runner, "deliver_card", lambda spec, card: "/tmp")
    monkeypatch.setattr(runner, "codex_turn_step", turn)
    spec = SimpleNamespace(runtime="codex", name="operator")
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


class _FakeWatchdogDb:
    """engine's db and board, faked with the two guarantees the watchdog leans
    on: a run closes once (`ended_at IS NULL`), and a board move with `expect`
    happens only from that status (`board.apply` holds the task's row lock).
    Every call yields, so ticks run with asyncio.gather interleave."""

    def __init__(self, monkeypatch, stale: list[dict], counted: int = 0,
                 status: str = "running", wf_status: str = "PENDING") -> None:
        self.stale = stale
        self.open_runs = {"r1"}
        self.wf_status = wf_status
        self.no_run_attempt = False     # newest attempt ERROR, no run written
        self.counted = counted          # stopped runs already on record
        self.status = status
        self.moves: list[str] = []
        self.calls: list[str] = []
        monkeypatch.setattr(engine.db, "fetch", self.fetch)
        monkeypatch.setattr(engine.db, "fetchone", self.fetchone)
        monkeypatch.setattr(engine.db, "execute", self.execute)
        monkeypatch.setattr(engine.board, "apply", self.apply)
        monkeypatch.setattr(engine.board, "resolve_ticket", self.nothing)
        monkeypatch.setattr(engine.obs, "emit", self.nothing)
        monkeypatch.setattr(engine, "_release_workflow", self.nothing)
        monkeypatch.setattr(engine.DBOS, "cancel_workflow_async", self.cancel)

    async def nothing(self, *a: Any, **kw: Any) -> None:
        await asyncio.sleep(0)

    async def cancel(self, wf_id: str) -> None:
        self.calls.append("cancel")
        self.wf_status = "CANCELLED"
        await asyncio.sleep(0)

    async def execute(self, sql: str, params: tuple = ()) -> None:
        await asyncio.sleep(0)

    async def fetch(self, sql: str, params: tuple = ()) -> list[dict]:
        await asyncio.sleep(0)
        self.calls.append(sql)
        if sql.lstrip().startswith("UPDATE hq.runs"):
            if "r.id = %s" in sql:
                closed = [params[-1]] if params[-1] in self.open_runs else []
                counts = "stopped before its run closed" in str(params[0])
            else:
                closed = sorted(self.open_runs)
                counts = params[0] == engine.SLEPT_RUN_ERROR
            self.open_runs -= set(closed)
            self.counted += len(closed) if counts else 0
            return [{"id": rid} for rid in closed]
        if "JOIN LATERAL" in sql:
            return ([{"task_id": "t1", "wf_status": "ERROR"}]
                    if self.no_run_attempt and self.status == "running" else [])
        if "w.status IN ('CANCELLED'" in sql:
            return [{**row, "wf_status": self.wf_status} for row in self.stale
                    if self.wf_status == "CANCELLED" and "r1" in self.open_runs]
        if "w.application_version IS DISTINCT FROM" in sql:
            return [dict(row) for row in self.stale
                    if self.wf_status == "PENDING" and "r1" in self.open_runs]
        if "FROM hq.tasks t WHERE t.status = 'running'" in sql:
            return [dict(row) for row in self.stale]
        return []

    async def fetchone(self, sql: str, params: tuple = ()) -> dict:
        await asyncio.sleep(0)
        assert engine.TIMED_OUT_RUNS in sql
        return {"n": self.counted}

    async def apply(self, task_id: str, event: str, *, status: str | None = None,
                    expect: str | None = None, **kw: Any) -> bool:
        await asyncio.sleep(0)
        if expect is not None and self.status != expect:
            return False
        self.moves.append(event)
        self.status = status or self.status
        return True


def test_a_run_the_host_slept_through_is_closed_as_a_counted_stop(monkeypatch) -> None:
    """2026-10-08: a video's sleep-abandoned runs had no error, so no limit ever counted them."""
    fake = _FakeWatchdogDb(monkeypatch, [{"id": "t1"}])
    asyncio.run(engine._cap_overrunning_tasks(slept=True))
    assert fake.counted == 1 and fake.moves == ["stopped_by_sleep", "requeued_after_sleep"]
    assert f"LIKE '{engine.SLEPT_RUN_ERROR}%%'" in engine.TIMED_OUT_RUNS
    # A run closed with no error, by an older build or a tick that missed the
    # sleep, is counted by the stopped_by_sleep event that follows it.
    assert "x.error IS NULL AND x.outcome = 'abandoned'" in engine.TIMED_OUT_RUNS
    assert "e.event_type = 'stopped_by_sleep' AND e.ts >= x.ended_at" in engine.TIMED_OUT_RUNS
    # A silent run with the host awake keeps whatever error it had.
    fake = _FakeWatchdogDb(monkeypatch, [{"id": "t1"}])
    asyncio.run(engine._cap_overrunning_tasks(slept=False))
    assert fake.counted == 0 and fake.moves == ["timed_out"]


@pytest.mark.parametrize("before,requeued", [
    (0, True), (engine.TIMEOUT_REQUEUES - 1, True), (engine.TIMEOUT_REQUEUES, False), (5, False)])
def test_a_sleep_requeue_stops_at_the_timeout_limit(monkeypatch, before: int,
                                                    requeued: bool) -> None:
    """2026-10-08: a video was requeued after every sleep, five runs in a row, with no limit."""
    fake = _FakeWatchdogDb(monkeypatch, [{"id": "t1"}], counted=before)
    asyncio.run(engine._cap_overrunning_tasks(slept=True))
    assert fake.moves[0] == "stopped_by_sleep"
    assert ("requeued_after_sleep" in fake.moves) is requeued


@pytest.mark.parametrize("before,requeued", [
    (engine.TIMEOUT_REQUEUES - 1, True), (engine.TIMEOUT_REQUEUES, False)])
def test_a_stopped_workflow_counts_sleeps_toward_the_same_limit(monkeypatch, before: int,
                                                                requeued: bool) -> None:
    """2026-10-08: sleep stops and workflow stops each had their own count, or none."""
    row = {"task_id": "t1", "task_status": "running", "run_id": "r1", "wf_id": "task-t1"}
    fake = _FakeWatchdogDb(monkeypatch, [row], counted=before, wf_status="CANCELLED")
    asyncio.run(engine._close_timed_out_runs())
    assert fake.moves[0] == "workflow_stopped"
    assert ("requeued_after_stop" in fake.moves) is requeued


def test_concurrent_ticks_after_a_wake_stop_and_requeue_a_task_once(monkeypatch) -> None:
    """2026-10-09: three watchdog ticks blocked and requeued one video in the same millisecond."""
    async def three_ticks() -> None:
        await asyncio.gather(*(engine._cap_overrunning_tasks(slept=True) for _ in range(3)))

    fake = _FakeWatchdogDb(monkeypatch, [{"id": "t1"}], counted=engine.TIMEOUT_REQUEUES - 1)
    asyncio.run(three_ticks())
    assert fake.moves == ["stopped_by_sleep", "requeued_after_sleep"]
    # The last stop the budget allows: every tick saw the same count, none requeues.
    fake = _FakeWatchdogDb(monkeypatch, [{"id": "t1"}], counted=engine.TIMEOUT_REQUEUES)
    asyncio.run(three_ticks())
    assert fake.moves == ["stopped_by_sleep"]
    # A tick that missed the sleep, racing one that saw it: one of them moves the task.
    fake = _FakeWatchdogDb(monkeypatch, [{"id": "t1"}])

    async def mixed() -> None:
        await asyncio.gather(engine._cap_overrunning_tasks(slept=False),
                             engine._cap_overrunning_tasks(slept=True))

    asyncio.run(mixed())
    assert fake.moves in (["timed_out"], ["stopped_by_sleep", "requeued_after_sleep"])


def test_concurrent_ticks_close_a_stopped_workflow_once(monkeypatch) -> None:
    """2026-10-09: ticks running together each counted the same stop and each requeued."""
    row = {"task_id": "t1", "task_status": "running", "run_id": "r1", "wf_id": "task-t1"}

    async def two_ticks() -> None:
        await asyncio.gather(engine._close_timed_out_runs(), engine._close_timed_out_runs())

    fake = _FakeWatchdogDb(monkeypatch, [row], counted=engine.TIMEOUT_REQUEUES,
                           wf_status="CANCELLED")
    asyncio.run(two_ticks())
    assert fake.counted == engine.TIMEOUT_REQUEUES + 1
    assert fake.moves == ["workflow_stopped"]


def test_a_deploy_stops_and_requeues_a_run_once(monkeypatch) -> None:
    """2026-09-23: a deploy requeues runs in flight; a tick alongside the boot must not do it twice."""
    row = {"task_id": "t1", "task_status": "running", "run_id": "r1", "wf_id": "task-t1"}
    fake = _FakeWatchdogDb(monkeypatch, [row])

    async def boot_and_tick() -> None:
        await asyncio.gather(engine.reap(), engine.reap(), engine._close_timed_out_runs())

    asyncio.run(boot_and_tick())
    assert fake.moves == ["stopped_by_deploy", "requeued_after_deploy"]
    # The run is closed before its workflow is cancelled, so no tick sees an
    # open run on a cancelled workflow; and a deploy stop is not a counted one.
    claim = next(i for i, c in enumerate(fake.calls) if "'stopped by a deploy'" in c)
    assert claim < fake.calls.index("cancel")
    assert fake.counted == 0 and "stopped by a deploy" not in engine.TIMED_OUT_RUNS


def _fake_requeue(monkeypatch, runs: int, ended: set[str]) -> list[str]:
    """requeue against a task with `runs` runs and these ended workflows; the
    workflow ids it enqueues are recorded."""
    started: list[str] = []

    async def fetchone(sql: str, params: tuple = ()) -> dict:
        await asyncio.sleep(0)
        return {"n": runs}

    async def fetch(sql: str, params: tuple = ()) -> list[dict]:
        await asyncio.sleep(0)
        assert list(params[1]) == list(engine.ENDED_WORKFLOW)
        return [{"workflow_uuid": w} for w in sorted(ended)]

    async def enqueue(task_id: str, *, attempt: int = 0, lane: str = "tasks") -> None:
        started.append(engine._attempt_wf_id(task_id, attempt))

    async def lane(task_id: str) -> str:
        return "courses"

    monkeypatch.setattr(engine.db, "fetchone", fetchone)
    monkeypatch.setattr(engine.db, "fetch", fetch)
    monkeypatch.setattr(engine, "_enqueue", enqueue)
    monkeypatch.setattr(engine, "_lane_of", lane)
    return started


@pytest.mark.parametrize("runs,ended,expected", [
    # 2026-09-28: marked running, workflow died before its run: attempt 0 is spent.
    (0, {"task-t1"}, "task-t1-retry-1"),
    # Two attempts in a row died before their runs.
    (1, {"task-t1", "task-t1-retry-1"}, "task-t1-retry-2"),
    # The ordinary retry after a run, and a first attempt still to start.
    (1, {"task-t1"}, "task-t1-retry-1"),
    (0, set(), "task-t1"),
])
def test_a_retry_never_reuses_a_workflow_that_ended(monkeypatch, runs: int, ended: set[str],
                                                    expected: str) -> None:
    """2026-09-28: a week review sat in backlog 11 days; every tick re-enqueued its ERROR workflow."""
    started = _fake_requeue(monkeypatch, runs, ended)
    asyncio.run(engine.requeue("t1"))
    assert started == [expected]


def test_concurrent_retries_of_one_task_start_one_attempt(monkeypatch) -> None:
    """2026-09-28: the backlog sweep, a boot and a Retry can all requeue one task at once."""
    started = _fake_requeue(monkeypatch, 0, {"task-t1"})

    async def five() -> None:
        await asyncio.gather(*(engine.requeue("t1") for _ in range(5)))

    asyncio.run(five())
    # One id for all of them; DBOS keys a workflow on its id, so it starts once.
    assert set(started) == {"task-t1-retry-1"}


def test_the_backlog_sweeps_pick_ids_through_requeue() -> None:
    """2026-09-28: the sweeps enqueued attempt 0 for a task with no runs, whatever had ended."""
    assert "await requeue(" in inspect.getsource(engine._reconcile_backlog)
    assert "_enqueue(" not in inspect.getsource(engine._reconcile_backlog)
    assert "_enqueue(" not in inspect.getsource(engine.reap)


@pytest.mark.parametrize("before,requeued", [
    (engine.TIMEOUT_REQUEUES, True), (engine.TIMEOUT_REQUEUES + 1, False)])
def test_a_workflow_that_died_before_its_run_is_stopped_and_counted(monkeypatch, before: int,
                                                                   requeued: bool) -> None:
    """2026-09-27: a week review was marked running, its workflow failed, and no run was written."""
    # `before` already includes the failed attempt: TIMED_OUT_RUNS counts it.
    assert "AND NOT EXISTS (SELECT 1 FROM hq.runs z WHERE z.wf_id = w.workflow_uuid)" \
        in engine.TIMED_OUT_RUNS
    fake = _FakeWatchdogDb(monkeypatch, [], counted=before)
    fake.no_run_attempt = True
    asyncio.run(engine._close_timed_out_runs())
    assert fake.moves[0] == "workflow_stopped"
    assert ("requeued_after_stop" in fake.moves) is requeued


def test_concurrent_ticks_stop_a_runless_failed_attempt_once(monkeypatch) -> None:
    """2026-10-09: watchdog ticks run together after a wake; each saw the same failed attempt."""
    fake = _FakeWatchdogDb(monkeypatch, [], counted=1)
    fake.no_run_attempt = True

    async def three_ticks() -> None:
        await asyncio.gather(*(engine._close_timed_out_runs() for _ in range(3)))

    asyncio.run(three_ticks())
    assert fake.moves == ["workflow_stopped", "requeued_after_stop"]


def test_the_dbos_thread_pool_is_capped() -> None:
    """2026-10-08: unset, DBOS's pool (also asyncio.to_thread's) grew to the 2048-thread limit."""
    from dbos._dbos_config import translate_dbos_config_to_config_file

    from hq import dbos_app

    assert dbos_app._config["max_executor_threads"] == 32
    # DBOS rebuilds runtimeConfig from the top-level key; a nested one is dropped.
    translated = translate_dbos_config_to_config_file(dbos_app._config)
    assert translated["runtimeConfig"]["max_executor_threads"] == 32
