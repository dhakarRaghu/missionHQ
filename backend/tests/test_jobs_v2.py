"""Phase 7: the fit score, the gates, the sweep brief and the register gate,
all as code. Nothing here touches the database: db.fetch and emit are
replaced, the way the other job tests do it."""

import asyncio
import inspect
import pathlib
from datetime import date
from types import SimpleNamespace

import pytest
import yaml
from pydantic_ai import ModelRetry

from hq import engine, voice
from hq.config import settings
from hq.db import load_migrations
from hq.job_pipeline import (
    SWEEP_PROMPT,
    discovery_brief,
    discovery_payload,
    exhausted_targets,
    sweep_brief,
    sweep_industry,
)
from hq.loader import scan
from hq.tools import browser_tools, job_tools, web_tools
from hq.tools.job_tools import (
    fit_score,
    intern_title,
    job_lane,
    parse_pay,
    private_employer,
)
from hq.tools.registry import HQDeps

REPO = pathlib.Path(__file__).resolve().parents[2]


def _ctx(agent: str = "hunter") -> SimpleNamespace:
    return SimpleNamespace(deps=HQDeps(agent=agent, run_id=None, task_id=None))


class _Recorder:
    """Stands in for db.fetch and emit, and keeps what they were given."""

    def __init__(self) -> None:
        self.sql: list[tuple[str, tuple]] = []
        self.events: list[tuple[str, dict]] = []

    async def fetch(self, sql: str, params: tuple = ()) -> list[dict]:
        self.sql.append((sql, params))
        return [{"id": "job-1", "seen_count": 1, "status": params[17] if len(params) > 17 else "seen"}]

    async def emit(self, kind: str, **kw) -> int:
        self.events.append((kind, kw.get("payload") or {}))
        return 1


@pytest.fixture
def recorder(monkeypatch) -> _Recorder:
    rec = _Recorder()
    monkeypatch.setattr(job_tools.db, "fetch", rec.fetch)
    monkeypatch.setattr(job_tools, "emit", rec.emit)
    return rec


def _record(**kw) -> str:
    fn = inspect.unwrap(job_tools.record_job)
    args = {"company": "Acme", "url": "https://jobs.example.com/1", "why_fit": "fits"}
    args.update(kw)
    return asyncio.run(fn(_ctx(), **args))


# --- pay ---------------------------------------------------------------------

@pytest.mark.parametrize("text, low, high, estimated", [
    ("₹24-48 LPA", 24, 48, False),
    ("20-30L", 20, 30, False),
    ("25 LPA", 25, 25, False),
    ("est. 18-24 LPA (Levels.fyi, SDE-1 Bengaluru)", 18, 24, True),
    ("₹12 L", 12, 12, False),
    ("18 LPA - 24 LPA", 18, 24, False),
    ("₹18,00,000 - ₹24,00,000 per annum", 18, 24, False),
    ("1.2 Cr", 120, 120, False),
])
def test_pay_is_read_in_lakhs(text, low, high, estimated) -> None:
    assert parse_pay(text) == (low, high, estimated)


@pytest.mark.parametrize("text", ["", "no public signal", "$120,000 - $150,000", "competitive"])
def test_pay_without_an_indian_figure_is_none(text) -> None:
    assert parse_pay(text) is None


# --- lanes and gates ---------------------------------------------------------

def test_titles_fall_into_the_profile_lanes() -> None:
    assert job_lane("Software Engineer I, Backend") == "software"
    assert job_lane("SDE-1") == "software"
    assert job_lane("AI Engineer I") == "applied_ai"
    assert job_lane("Forward Deployed Engineer") == "forward_deployed"
    assert job_lane("Solutions Engineer") == "forward_deployed"
    assert job_lane("Data Analyst") == ""


def test_intern_trainee_and_fresher_titles_are_caught() -> None:
    for role in ("Software Engineer Intern", "SDE Internship", "Graduate Trainee",
                 "Fresher - Backend Developer", "Apprentice Engineer"):
        assert intern_title(role), role
    for role in ("Internal Tools Engineer", "Software Engineer I", "Graduate Software Engineer"):
        assert intern_title(role) is None, role


# --- the score ---------------------------------------------------------------

def test_a_level_one_backend_role_that_pays_is_strong() -> None:
    fit = fit_score("Software Engineer I, Backend", experience_band="0-2 years",
                    compensation="22-30 LPA", location="Bengaluru")
    assert fit.score >= 8
    assert fit.lane == "software"
    assert fit.pay_lakh == 30
    assert fit.parts["pay"]["points"] == 1
    assert fit.parts["years"]["points"] == 2


def test_a_stated_low_package_is_a_stretch_however_good_the_title() -> None:
    fit = fit_score("Software Engineer I", experience_band="0-2 years",
                    compensation="₹12 LPA", stack="Go, Kubernetes", location="Bengaluru")
    assert fit.score <= 4
    assert fit.parts["pay"]["points"] == -3
    assert fit.pay_lakh == 12


def test_an_estimated_low_package_is_not_the_stated_penalty() -> None:
    fit = fit_score("Software Engineer I", experience_band="0-2 years",
                    pay_signal="est. 18-24 LPA (Levels.fyi)")
    assert fit.parts["pay"]["points"] == 0
    assert fit.parts["pay"]["estimated"] is True


def test_two_to_three_years_is_a_stretch_point() -> None:
    assert fit_score("SDE", experience_band="2-4 years").parts["years"]["points"] == 1
    assert fit_score("SDE", experience_band="1-3 years").parts["years"]["points"] == 2
    assert fit_score("SDE", experience_band="new grad only").parts["years"]["points"] == 0


def test_geography_outside_india_costs_points_and_work_mode_never_does() -> None:
    assert fit_score("SDE", location="Hybrid").parts["geography"]["points"] == 0
    assert fit_score("SDE", location="Remote - India").parts["geography"]["points"] == 0
    assert fit_score("SDE", location="Remote", remote_policy="anywhere").parts[
        "geography"]["points"] == 0
    assert fit_score("SDE", location="San Francisco, CA").parts["geography"]["points"] == -2
    assert fit_score("SDE", location="Singapore (relocation offered)").parts[
        "geography"]["points"] == -1


def test_the_model_moves_the_score_by_one_at_most_and_only_with_a_reason() -> None:
    base = fit_score("SDE-1", experience_band="0-2 years").score
    assert fit_score("SDE-1", experience_band="0-2 years", adjust=1,
                     adjust_reason="funded payments team").score == base + 1
    assert fit_score("SDE-1", experience_band="0-2 years", adjust=5,
                     adjust_reason="x").score == base + 1
    assert fit_score("SDE-1", experience_band="0-2 years", adjust=1).score == base


# --- record_job --------------------------------------------------------------

def test_record_job_stores_the_computed_score_and_keeps_the_models(recorder) -> None:
    out = _record(role="Software Engineer I, Backend", fit_score=6,
                  experience_band="0-2 years", compensation="22-30 LPA", location="Bengaluru")
    sql, params = recorder.sql[0]
    assert "fit_parts, pay_lakh, lane" in sql
    stored_score, parts, pay, lane = params[12], params[24], params[25], params[26]
    assert stored_score >= 8
    assert parts.obj["model_score"] == 6
    assert pay == 30 and lane == "software"
    assert "you proposed 6" in out


def test_flipkart_sde_two_is_closed_by_the_gate(recorder) -> None:
    out = _record(company="Flipkart", role="SDE II", experience_band="2.5 years",
                  compensation="30 LPA")
    assert recorder.sql[0][1][17] == "closed"
    assert "CLOSED" in out


def test_a_lead_title_is_closed_with_no_years_named(recorder) -> None:
    out = _record(role="Lead AI Engineer", experience_band="")
    assert recorder.sql[0][1][17] == "closed"
    assert "CLOSED" in out


def test_an_internship_is_closed(recorder) -> None:
    out = _record(role="Software Engineer Intern", experience_band="0 years")
    assert recorder.sql[0][1][17] == "closed"
    assert "intern" in out


def test_a_strong_role_needs_its_pay_and_band(recorder) -> None:
    with pytest.raises(ModelRetry, match="compensation or pay_signal"):
        _record(role="Software Engineer I", experience_band="0-2 years", location="Bengaluru")
    with pytest.raises(ModelRetry, match="experience_band"):
        _record(role="AI Engineer I", compensation="30 LPA")
    assert not recorder.sql
    # A weak one is recorded with the fields empty, which is correct.
    _record(role="Data Analyst", location="London")
    assert recorder.sql


def test_the_owners_employer_is_never_recorded(recorder, monkeypatch) -> None:
    monkeypatch.setattr(settings(), "private_employers", ("Acmecorp",))
    out = _record(company="Acmecorp Technologies", role="SDE-1", experience_band="0-2 years",
                  compensation="30 LPA")
    assert out.startswith("not recorded")
    assert "Acmecorp" not in out
    assert not recorder.sql


def test_private_employers_match_a_board_slug(monkeypatch) -> None:
    monkeypatch.setattr(settings(), "private_employers", ("Acme Corp",))
    assert private_employer("acmecorp")
    assert private_employer("ACME CORP Pvt Ltd")
    assert not private_employer("Acme")
    assert not private_employer("")


def test_job_board_and_discovery_refuse_the_owners_employer(monkeypatch) -> None:
    monkeypatch.setattr(settings(), "private_employers", ("Acmecorp",))

    async def no_network(*a, **kw):
        raise AssertionError("the board must not be fetched")

    monkeypatch.setattr(web_tools.httpx.AsyncClient, "get", no_network)
    board = inspect.unwrap(web_tools.job_board)
    out = asyncio.run(board(_ctx(), provider="lever", company="acmecorp"))
    assert "never researched" in out["error"]
    assert "acmecorp" not in str(out).lower()
    assert "private_employer(company[\"name\"])" in inspect.getsource(web_tools.discover_companies)


def test_the_discovery_brief_names_no_employer_in_source() -> None:
    src = inspect.getsource(discovery_brief)
    for name in settings().private_employers:
        assert name not in src
    assert "_employer_skip_line()" in src


def test_the_discovery_brief_takes_the_skip_line_from_settings(monkeypatch) -> None:
    monkeypatch.setattr(settings(), "private_employers", ("Acmecorp", "Globex"))
    brief = discovery_brief(discovery_payload(query="SDE-1", locations="India", max_roles=5))
    assert "Skip Acmecorp and Globex too" in brief


# --- browser_read and ATS hosts ----------------------------------------------

def test_browser_read_refuses_ats_hosts(monkeypatch) -> None:
    monkeypatch.setattr(settings(), "browser_enabled", True)
    events: list = []

    async def emit(kind, **kw):
        events.append(kind)

    async def no_launch():
        raise AssertionError("the browser must not open for an ATS page")

    monkeypatch.setattr(browser_tools, "emit", emit)
    monkeypatch.setattr(browser_tools, "_launch_chrome", no_launch)
    read = inspect.unwrap(browser_tools.browser_read)
    for url in ("https://jobs.ashbyhq.com/bolna/123", "https://boards.greenhouse.io/x/jobs/1",
                "https://jobs.lever.co/cred/abc", "https://apply.workable.com/x/j/1",
                "https://acme.recruitee.com/o/sde", "https://jobs.smartrecruiters.com/X/1"):
        out = asyncio.run(read(_ctx(), url))
        assert "job_board" in out["error"], url
    assert events == ["browser.refused"] * 6
    assert browser_tools.ats_domain("https://example.com/careers") is None


# --- back-off and the sweep brief --------------------------------------------

def _event(kind: str, run: str, **payload) -> dict:
    return {"kind": kind, "run_id": run, "payload": payload}


def test_three_empty_runs_in_a_row_put_a_target_on_back_off() -> None:
    events = [
        _event("job_board", "r1", provider="lever", company="quiet", jobs=0),
        _event("job_board", "r2", provider="lever", company="quiet", jobs=0),
        _event("job_board", "r3", provider="lever", company="quiet", jobs=0),
        # Paged twice in one run: one run, and it found something.
        _event("job_board", "r1", provider="ashby", company="busy", jobs=0),
        _event("job_board", "r1", provider="ashby", company="busy", jobs=4),
        _event("job_board", "r2", provider="ashby", company="busy", jobs=0),
        _event("job_board", "r3", provider="ashby", company="busy", jobs=0),
        # Found something, then two empty: not yet.
        _event("job_board", "r1", provider="greenhouse", company="recent", jobs=2),
        _event("job_board", "r2", provider="greenhouse", company="recent", jobs=0),
        _event("job_board", "r3", provider="greenhouse", company="recent", jobs=0),
        _event("discover_companies", "r1", region="India", industry="Fintech", found=0),
        _event("discover_companies", "r2", region="India", industry="Fintech", found=0),
        _event("discover_companies", "r3", region="India", industry="Fintech", found=0),
        _event("job.recorded", "r3", company="x"),
    ]
    assert exhausted_targets(events) == [
        "discover_companies India / Fintech", "lever board quiet"]


def test_a_backed_off_industry_is_passed_over_for_the_next() -> None:
    monday = date(2026, 9, 21)
    assert sweep_industry(monday) == "Fintech"
    assert sweep_industry(monday, ["discover_companies India / Fintech"]) == "B2B"


def test_the_sweep_brief_is_a_short_contract_with_the_state_filled_in() -> None:
    known = [f"Company{i}" for i in range(14)]
    skips = ["lever board quiet", "ashby board empty", "discover_companies India / B2B"]
    brief = sweep_brief(today=date(2026, 9, 22), known_companies=known, exhausted=skips)
    assert len(brief.split()) <= 150
    assert 'industry="Developer Tools"' in brief  # Tuesday is B2B, backed off
    assert "Company0" in brief and "and 4 more" in brief
    assert "lever board quiet" in brief and "Skip this week" in brief
    assert "max_roles 8" in brief
    assert "record_job" in brief and "job_board" in brief and "discover_companies" in brief
    assert "intern" in brief and "closed itself" in brief


def test_the_hunter_cron_is_the_bare_sweep_prompt() -> None:
    hunter = scan()["hunter"]
    assert [c.prompt for c in hunter.cron] == [SWEEP_PROMPT]


def test_a_sweep_cron_is_dispatched_with_the_code_built_brief(monkeypatch) -> None:
    async def built() -> str:
        return "BUILT BRIEF"

    from hq.tools import job_tools as jt

    monkeypatch.setattr(jt, "build_sweep_brief", built)
    step = inspect.unwrap(engine._cron_brief_step)
    assert asyncio.run(step("hunter", SWEEP_PROMPT)) == "BUILT BRIEF"
    assert asyncio.run(step("sage", "Write the note.")) == "Write the note."
    src = inspect.getsource(engine)
    assert src.count("await _cron_brief_step(") == 2


# --- sage and the shortlist --------------------------------------------------

def test_sage_reads_the_job_ledger_and_writes_a_weekly_shortlist() -> None:
    sage = scan()["sage"]
    assert "list_jobs" in sage.base_tool_names()
    sage.validate_trifecta()
    last = sage.cron[-1]
    assert last.schedule == "0 9 * * 1"
    assert last.skill == "job-shortlist"  # code puts the skill in the brief
    # The daily note keeps its place at the head of the list.
    assert sage.cron[0].schedule == "30 22 * * *"
    skill = (REPO / "agents" / "sage" / "skills" / "job-shortlist" / "SKILL.md").read_text()
    assert len(skill.split()) <= 350
    assert "list_jobs" in skill and "projects/jobs/shortlist-" in skill
    assert not (REPO / "agents" / "sage" / "skills" / "job-search").exists()
    assert "job-search skill" not in (REPO / "agents" / "sage" / "job.md").read_text()


def test_fit_migration_adds_the_three_columns() -> None:
    sql = dict(load_migrations())[34]
    for column in ("fit_parts jsonb", "pay_lakh numeric", "lane text"):
        assert column in sql


# --- the register gate -------------------------------------------------------

REAL_REGISTER = """I broke production three times last month.

Every time it was the retry path. I'd written it to be safe and it wasn't.

I think most teams test the happy path and trust the rest. I don't anymore.
Now the retry gets its own test before the feature does.

Happy to help if you're fighting the same thing.
"""

ESSAY_REGISTER = """In this post we examine retries.

It is important to test failure paths. Teams do not always do this, and they
cannot rely on the happy path. We are going to look at three reasons.

The lesson is simple: test the retry.
"""


def test_the_voice_file_carries_the_measured_gate() -> None:
    data = yaml.safe_load((REPO / "agents" / "_shared" / "voice.yaml").read_text())
    gate = data["gate"]
    assert gate["min_apostrophes"] == 2
    assert gate["max_written_out_forms"] == 1
    assert gate["min_i_think_family"] == 1
    assert gate["max_em_dashes"] == 0
    assert {"emoji", "hashtags", "bullets"} <= set(gate["forbid"])


def test_a_real_register_sample_passes() -> None:
    assert voice.register_problems(REAL_REGISTER) == []
    # His own openers from the voice file pass the same gate as a post.
    assert voice.register_problems("---\ntitle: x\n---\n# Draft\n\n" + REAL_REGISTER) == []


def test_a_draft_with_no_contractions_fails() -> None:
    problems = voice.register_problems(ESSAY_REGISTER)
    joined = " ".join(problems)
    assert "contraction" in joined
    assert "written-out" in joined
    assert "I think" in joined
    assert "The lesson is" in joined


def test_furniture_and_dashes_fail() -> None:
    bad = REAL_REGISTER + "\n- a bullet\n#buildinpublic — thoughts?\n"
    joined = " ".join(voice.register_problems(bad))
    assert "bullet" in joined and "hashtag" in joined and "em dash" in joined
    assert "engagement" in joined


def test_vault_write_runs_the_gate_on_content_drafts(monkeypatch) -> None:
    from hq.tools import vault_tools

    write = inspect.unwrap(vault_tools.vault_write)
    ctx = SimpleNamespace(deps=HQDeps(agent="scout", vault_write_scopes=["projects/content/**"]))
    with pytest.raises(ModelRetry, match="not in his register"):
        asyncio.run(write(ctx, "projects/content/drafts/2026-09-23-retries.md", ESSAY_REGISTER))
    # Outside drafts the gate does not apply: ideas.md is a list by design.
    assert not voice.is_draft_path("projects/content/ideas.md")
