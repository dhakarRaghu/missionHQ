from hq.db import load_migrations
from hq.loader import AgentSpec, instructions_for
from hq.tools.job_tools import _dedupe_key
from hq.tools.web_tools import _filter_jobs, _one_job


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
