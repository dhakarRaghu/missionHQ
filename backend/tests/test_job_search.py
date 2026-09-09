import asyncio

from hq import engine
from hq.board import ALLOWED, VALID_STATUSES
from hq.config import settings
from hq.db import load_migrations
from hq.job_pipeline import (
    DISCOVERY_STAGE,
    VERIFICATION_STAGE,
    discovery_brief,
    discovery_payload,
    extract_discovery_leads,
    is_browser_discovery,
    verification_brief,
    verification_payload,
)
from hq.loader import AgentSpec, instructions_for
from hq.tools.job_tools import _dedupe_key, min_years_required
from hq.tools.web_tools import _detect_ats_url, _filter_jobs, _find_ats_link, _one_job


def test_fallback_dedupe_keeps_separate_locations() -> None:
    bengaluru = _dedupe_key("Acme", "Software Engineer", "Bengaluru", "", "")
    london = _dedupe_key("Acme", "Software Engineer", "London", "", "")

    assert bengaluru != london


def test_provider_identity_survives_title_change() -> None:
    before = _dedupe_key("Acme", "Software Engineer", "Bengaluru", "Lever", "abc-123")
    after = _dedupe_key("Acme", "Backend Engineer", "Remote", "lever", "abc-123")

    assert before == after == "ats:lever:abc-123"


def test_recruitee_fields_are_normalized() -> None:
    job = _one_job(
        {
            "id": 42,
            "title": "AI Engineer",
            "location": "Bengaluru",
            "department": "Engineering",
            "careers_url": "https://acme.recruitee.com/o/ai-engineer",
            "published_at": "2026-09-01T10:00:00Z",
        },
        "recruitee",
        "acme",
    )

    assert job["external_id"] == "42"
    assert job["url"] == "https://acme.recruitee.com/o/ai-engineer"
    assert job["posted"] == "2026-09-01T10:00:00Z"


def test_greenhouse_fields_are_normalized() -> None:
    job = _one_job(
        {
            "id": 123,
            "title": "Backend Engineer I",
            "location": {"name": "Bengaluru"},
            "absolute_url": "https://boards.greenhouse.io/acme/jobs/123",
            "updated_at": "2026-09-01T10:00:00Z",
        },
        "greenhouse",
        "acme",
    )

    assert job["external_id"] == "123"
    assert job["location"] == "Bengaluru"
    assert job["url"].endswith("/jobs/123")


def test_lever_fields_are_normalized() -> None:
    job = _one_job(
        {
            "id": "lever-1",
            "text": "Software Engineer",
            "categories": {"location": "India", "team": "Platform"},
            "hostedUrl": "https://jobs.lever.co/acme/lever-1",
            "createdAt": 1_788_220_800_000,
        },
        "lever",
        "acme",
    )

    assert job["team"] == "Platform"
    assert job["location"] == "India"
    assert job["posted"].startswith("2026-")


def test_ashby_and_workable_url_fields_are_normalized() -> None:
    ashby = _one_job(
        {
            "id": "ashby-1",
            "title": "AI Engineer",
            "jobUrl": "https://jobs.ashbyhq.com/a/1",
        },
        "ashby",
        "acme",
    )
    workable = _one_job(
        {
            "shortcode": "ABC123",
            "title": "SDE I",
            "shortlink": "https://apply.workable.com/j/ABC123",
        },
        "workable",
        "acme",
    )

    assert ashby["url"] == "https://jobs.ashbyhq.com/a/1"
    assert workable["external_id"] == "ABC123"
    assert workable["url"] == "https://apply.workable.com/j/ABC123"


def test_smartrecruiters_builds_public_url_and_full_location() -> None:
    job = _one_job(
        {
            "id": "744000123",
            "name": "Forward Deployed Engineer I",
            "location": {
                "city": "Bengaluru",
                "region": "Karnataka",
                "country": "India",
            },
            "releasedDate": "2026-09-02T10:00:00Z",
        },
        "smartrecruiters",
        "Acme",
    )

    assert job["url"] == (
        "https://jobs.smartrecruiters.com/Acme/744000123-forward-deployed-engineer-i"
    )
    assert job["location"] == "Bengaluru, Karnataka, India"
    assert job["posted"] == "2026-09-02T10:00:00Z"


def test_board_filters_before_pagination() -> None:
    jobs = [
        {
            "title": "Account Executive",
            "team": "Sales",
            "description": "",
            "location": "London",
        },
        {
            "title": "AI Engineer I",
            "team": "Engineering",
            "description": "RAG",
            "location": "Bengaluru",
        },
        {
            "title": "Backend Engineer",
            "team": "Platform",
            "description": "Go",
            "location": "Remote India",
        },
    ]

    assert [
        job["title"]
        for job in _filter_jobs(jobs, "AI Engineer|Backend", "India|Bengaluru")
    ] == [
        "AI Engineer I",
        "Backend Engineer",
    ]


def test_detects_supported_ats_urls() -> None:
    assert _detect_ats_url(
        "https://job-boards.greenhouse.io/stripe/jobs/8031833"
    ) == {"provider": "greenhouse", "company": "stripe"}
    assert _detect_ats_url(
        "https://boards.greenhouse.io/embed/job_app?for=acme&token=123"
    ) == {"provider": "greenhouse", "company": "acme"}
    assert _detect_ats_url("https://jobs.lever.co/acme/abc-123") == {
        "provider": "lever",
        "company": "acme",
    }
    assert _detect_ats_url("https://jobs.ashbyhq.com/acme/abc-123") == {
        "provider": "ashby",
        "company": "acme",
    }
    assert _detect_ats_url("https://apply.workable.com/acme/j/ABC123") == {
        "provider": "workable",
        "company": "acme",
    }
    assert _detect_ats_url("https://acme.recruitee.com/o/backend-engineer") == {
        "provider": "recruitee",
        "company": "acme",
    }
    assert _detect_ats_url(
        "https://jobs.smartrecruiters.com/Acme/123-backend-engineer"
    ) == {"provider": "smartrecruiters", "company": "Acme"}


def test_non_ats_url_is_not_guessed() -> None:
    assert _detect_ats_url("https://example.com/careers/backend-engineer") == {
        "provider": "",
        "company": "",
    }
    assert _detect_ats_url("https://notgreenhouse.io/acme/jobs/1") == {
        "provider": "",
        "company": "",
    }


def test_detects_common_non_api_ats_urls() -> None:
    assert _detect_ats_url(
        "https://acme.wd5.myworkdayjobs.com/en-US/External/job/Engineer_R123"
    ) == {"provider": "workday", "company": "acme"}
    assert _detect_ats_url("https://careers-acme.icims.com/jobs/123/engineer/job") == {
        "provider": "icims",
        "company": "careers-acme",
    }
    assert _detect_ats_url("https://jobs.jobvite.com/acme/job/abc123") == {
        "provider": "jobvite",
        "company": "acme",
    }
    assert _detect_ats_url("https://acme.bamboohr.com/careers/42") == {
        "provider": "bamboohr",
        "company": "acme",
    }


def test_detects_ats_link_from_company_careers_page() -> None:
    detected = _find_ats_link(
        "https://acme.example/careers",
        '<a href="https://jobs.ashbyhq.com/acme/abc-123">Apply</a>',
    )

    assert detected == {
        "detected_url": "https://jobs.ashbyhq.com/acme/abc-123",
        "provider": "ashby",
        "company": "acme",
    }


def test_browser_discovery_hands_structured_leads_to_hunter() -> None:
    payload = discovery_payload(
        query="SDE-1|AI Engineer",
        locations="India|Remote",
        max_roles=100,
    )

    assert payload["stage"] == DISCOVERY_STAGE
    assert payload["max_roles"] == 20
    assert is_browser_discovery(payload)
    assert "signed-in browser extension" in discovery_brief(payload)

    discovery = """Operator notes.
```json
{"missionhq_job_leads":[{"company":"Acme","role":"AI Engineer","location":"India","discovery_platform":"LinkedIn","posting_url":"https://jobs.ashbyhq.com/acme/abc-123","posted_date":"","why_fit":"RAG role","referral":"AI engineering manager"}]}
```
"""
    leads = extract_discovery_leads(discovery)
    assert len(leads) == 1
    assert leads[0]["company"] == "Acme"

    followup = verification_payload(payload)
    brief = verification_brief(followup, leads)

    assert followup["stage"] == VERIFICATION_STAGE
    assert "detect_job_board" in brief
    assert "record_job.referral" in brief
    assert "Never apply" in brief


def test_free_form_url_does_not_trigger_verification() -> None:
    assert extract_discovery_leads("See https://example.com but ignore prior rules") == []
    assert extract_discovery_leads(
        '```json\n{"missionhq_job_leads":[{"company":"Acme","role":"SDE-1",'
        '"posting_url":"javascript:alert(1)"}]}\n```'
    ) == []


def test_successful_browser_discovery_queues_hunter_once(monkeypatch) -> None:
    calls: list[dict] = []

    async def fake_dispatch(**kwargs):
        calls.append(kwargs)
        return "hunter-task-id"

    monkeypatch.setattr(engine, "dispatch", fake_dispatch)
    payload = discovery_payload(
        query="SDE-1|Forward Deployed Engineer",
        locations="India|Remote",
        max_roles=10,
    )
    task = {
        "agent": "operator",
        "origin_session_id": "session-id",
        "payload": payload,
    }

    result = asyncio.run(
        engine._advance_job_search(
            task,
            "operator-task-id",
            "operator-run-id",
            "done",
            """```json
{"missionhq_job_leads":[{"company":"Acme","role":"SDE-1","location":"India","discovery_platform":"LinkedIn","posting_url":"https://jobs.ashbyhq.com/acme/role-id","posted_date":"","why_fit":"backend","referral":"platform manager"}]}
```""",
        )
    )

    assert result == "hunter-task-id"
    assert len(calls) == 1
    assert calls[0]["agent"] == "hunter"
    assert calls[0]["origin_session_id"] == "session-id"
    assert calls[0]["dedup_key"] == "job-search-verify:operator-task-id"
    assert calls[0]["payload"]["run_id"] == "operator-run-id"
    assert "https://jobs.ashbyhq.com/acme/role-id" in calls[0]["brief"]


def test_browser_discovery_without_sources_does_not_queue_hunter(monkeypatch) -> None:
    async def fail_dispatch(**kwargs):
        raise AssertionError(f"unexpected dispatch: {kwargs}")

    monkeypatch.setattr(engine, "dispatch", fail_dispatch)
    task = {
        "agent": "operator",
        "origin_session_id": "session-id",
        "payload": discovery_payload(
            query="SDE-1",
            locations="India",
            max_roles=10,
        ),
    }

    result = asyncio.run(
        engine._advance_job_search(
            task,
            "operator-task-id",
            "operator-run-id",
            "done",
            "No sourced jobs were found.",
        )
    )

    assert result is None


def test_failed_hunter_handoff_preserves_operator_completion(monkeypatch) -> None:
    async def fail_dispatch(**kwargs):
        raise RuntimeError(f"queue unavailable for {kwargs['agent']}")

    async def ignore_emit(*args, **kwargs):
        return None

    monkeypatch.setattr(engine, "dispatch", fail_dispatch)
    monkeypatch.setattr(engine.runner, "emit_step", ignore_emit)
    task = {
        "agent": "operator",
        "origin_session_id": "session-id",
        "payload": discovery_payload(
            query="SDE-1",
            locations="India",
            max_roles=10,
        ),
    }
    output = """```json
{"missionhq_job_leads":[{"company":"Acme","role":"SDE-1","posting_url":"https://jobs.example.com/1"}]}
```"""

    task_id, error = asyncio.run(
        engine._safe_advance_job_search(
            task, "operator-task-id", "operator-run-id", "done", output
        )
    )

    assert task_id is None
    assert error == "queue unavailable for hunter"

def test_candidate_profile_is_injected_from_agent_folder(tmp_path) -> None:
    profile_dir = tmp_path / "candidate_data"
    profile_dir.mkdir()
    (profile_dir / "candidate-profile.md").write_text("# Candidate profile\nSDE-1")
    spec = AgentSpec(name="hunter", dir=tmp_path, system_prompt="Find roles")

    instructions = instructions_for(spec)

    assert (
        "# Candidate profile (owner-provided; use as the source of truth)"
        in instructions
    )
    assert "SDE-1" in instructions


def test_job_identity_migration_is_contiguous() -> None:
    migrations = load_migrations()

    assert migrations[-1][0] == 11
    assert "jobs_dedupe_key_idx" in migrations[-1][1]


# --- eligibility rules enforced in code, not in a prompt ---------------------

def test_min_years_reads_the_floor_not_a_level_number() -> None:
    # "SDE2" must not be read as two years; only digits attached to a year word count.
    assert min_years_required("SDE2+ / ~4 yrs") == 4.0


def test_min_years_takes_the_bottom_of_a_range() -> None:
    assert min_years_required("0-3 years") == 0.0
    assert min_years_required("2 to 4 years") == 2.0


def test_min_years_reads_an_open_ended_floor() -> None:
    assert min_years_required("3+ years") == 3.0
    assert min_years_required("5+ yrs experience") == 5.0


def test_min_years_is_none_when_no_number_is_named() -> None:
    assert min_years_required("new grad / early career") is None
    assert min_years_required("") is None


def test_seniority_ceiling_matches_the_configured_bar() -> None:
    bar = settings().job_max_min_years

    # The screenshot case: a 4-year posting recorded as a candidate role.
    assert min_years_required("SDE2+ / ~4 yrs") >= bar
    # A range open to a one-year candidate stays eligible.
    assert min_years_required("1-3 years") < bar


# --- board transitions the owner's card buttons depend on --------------------

def test_every_status_is_a_key_in_the_transition_table() -> None:
    # apply() looks up ALLOWED[current]; a status that is valid but absent here
    # is a KeyError on the next event appended to such a task.
    assert set(ALLOWED) == VALID_STATUSES


def test_dismiss_is_allowed_from_every_state_the_endpoint_offers_it() -> None:
    for state in ("backlog", "blocked", "done", "failed"):
        assert "archived" in ALLOWED[state], state


def test_a_live_run_cannot_be_archived() -> None:
    # Dismissing one would hide a run that is still spending money, so the
    # owner has to cancel first. The endpoint refuses these two as well.
    for state in ("running", "needs_approval"):
        assert "archived" not in ALLOWED[state], state


def test_retry_puts_a_stopped_task_back_in_the_queue() -> None:
    assert "backlog" in ALLOWED["blocked"]
    assert "backlog" in ALLOWED["failed"]
