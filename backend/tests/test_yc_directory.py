"""YC as a job source: the directory's search index for hiring companies,
and each company's page for its postings and founders.

discover_companies used to read page 1 of api.ycombinator.com/v0.1: the same
20 companies for India every night, with no hiring field. YC is faked here
with an httpx MockTransport; nothing reaches the network."""

from __future__ import annotations

import asyncio
import html
import inspect
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from urllib.parse import parse_qs

import httpx
import pytest

from hq import yc_directory as yc
from hq.tools import web_tools
from hq.tools.registry import HQDeps

NOW = datetime(2026, 10, 3, tzinfo=UTC)


def _company(slug: str, name: str, jobs: list[dict[str, Any]],
             founders: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {"company": {"name": name, "slug": slug, "one_liner": f"{name} builds things",
                        "team_size": 12, "batch": "W25",
                        "founders": founders if founders is not None else [
                            {"full_name": "Asha Rao", "title": "CEO", "is_active": True,
                             "linkedin_url": "https://linkedin.com/in/asha", "twitter_url": None,
                             "has_email": True},
                            {"full_name": "Old Founder", "title": "CTO", "is_active": False}]},
            "jobPostings": jobs}


def _job(id_: int, title: str, *, role: str = "eng", age: str = "3 days",
         place: str = "Bengaluru, KA, IN", pay: str = "₹25L - ₹40L", equity: str = "",
         exp: str = "1+ years") -> dict[str, Any]:
    return {"id": id_, "title": title, "role": role, "prettyRole": "Engineering",
            "roleSpecificType": "Backend", "location": place, "salaryRange": pay,
            "equityRange": equity, "minExperience": exp, "createdAt": age,
            "url": f"/companies/x/jobs/{id_}", "skills": ["Go", "Postgres"],
            "visa": "", "companyBatchName": "W25"}


HITS = [
    {"name": "Acme AI", "slug": "acme-ai", "launched_at": 300, "isHiring": True,
     "one_liner": "agents", "all_locations": "Bengaluru", "batch": "Winter 2025",
     "industries": ["B2B"], "team_size": 12, "regions": ["India"]},
    {"name": "Bay Remote", "slug": "bay-remote", "launched_at": 400, "isHiring": True,
     "one_liner": "us only", "all_locations": "San Francisco", "batch": "Fall 2025",
     "industries": ["B2B"], "team_size": 5, "regions": ["Remote", "America / Canada"]},
    {"name": "Older Co", "slug": "older-co", "launched_at": 100, "isHiring": True,
     "one_liner": "old", "all_locations": "Gurugram", "batch": "Winter 2018",
     "industries": ["Fintech"], "team_size": 300, "regions": ["India"]},
]
PAGES = {
    "acme-ai": _company("acme-ai", "Acme AI", [
        _job(1, "Backend Engineer", equity="0.1% - 0.5%"),
        _job(2, "Growth Marketer", role="marketing"),
        _job(3, "AI Engineer", age="over 2 years")]),
    "bay-remote": _company("bay-remote", "Bay Remote", [
        _job(5, "Backend Engineer, US", place="San Francisco, CA, US / Remote (US)")]),
    "older-co": _company("older-co", "Older Co", [
        _job(4, "Software Engineer", place="Gurugram, HR, IN", age="about 1 month")]),
}

# YC's India jobs page: a US company's India role, filed by YC under India
# though its location says "Remote (US)" (LiteLLM, 2026-10-05).
INDIA_PAGE = [{**_job(9, "Forward Deployed Engineer - India", place="Remote (US)",
                     age="about 2 months"),
               "companyName": "LiteLLM", "companyBatchName": "W23", "lastActive": "about 1 month"}]


class FakeYC:
    """The directory page, the search index and the company pages."""

    def __init__(self, hits: list[dict[str, Any]] | None = None, refuse: bool = False) -> None:
        self.hits = HITS if hits is None else hits
        self.refuse = refuse
        self.queries: list[list[list[str]]] = []
        self.pages_read: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if url == yc.DIRECTORY_URL:
            return httpx.Response(200, text='<script>window.AlgoliaOpts = {"app":"APP1","key":"k3y"};</script>')
        if "algolia.net" in url:
            if self.refuse:
                return httpx.Response(403, json={"message": "invalid key"})
            params = parse_qs(json.loads(request.content)["params"])
            facets = json.loads(params["facetFilters"][0])
            self.queries.append(facets)
            want = {f.split(":", 1)[1] for f in facets[0]}
            hits = [h for h in self.hits if want & set(h.get("regions") or [])]
            return httpx.Response(200, json={"hits": hits, "nbPages": 1})
        if url == yc.INDIA_JOBS_URL:
            blob = html.escape(json.dumps({"props": {"jobPostings": INDIA_PAGE}}), quote=True)
            return httpx.Response(200, text=f'<div data-page="{blob}"></div>')
        slug = url.rsplit("/", 1)[-1]
        self.pages_read.append(slug)
        if slug in PAGES:
            blob = html.escape(json.dumps({"props": PAGES[slug]}), quote=True)
            return httpx.Response(200, text=f'<div data-page="{blob}"></div>')
        return httpx.Response(404, text="")


@pytest.fixture
def fake(monkeypatch) -> FakeYC:
    yc_fake = FakeYC()
    real = httpx.AsyncClient

    def client(*a: Any, **kw: Any) -> httpx.AsyncClient:
        kw["transport"] = httpx.MockTransport(yc_fake)
        return real(*a, **kw)
    monkeypatch.setattr(web_tools.httpx, "AsyncClient", client)
    monkeypatch.setattr(yc, "_key", None)
    monkeypatch.setattr(yc, "_pages", {})

    async def no_emit(*a: Any, **kw: Any) -> None:
        return None
    monkeypatch.setattr(web_tools, "emit", no_emit)
    monkeypatch.setattr(web_tools, "private_employer", lambda name: False)
    return yc_fake


def _ctx() -> SimpleNamespace:
    return SimpleNamespace(deps=HQDeps(agent="hunter", run_id=None, task_id=None))


# --- pure helpers --------------------------------------------------------------

def test_batch_names_regions_and_ages() -> None:
    assert yc.batch_name("W25") == "Winter 2025" and yc.batch_name("x26") == "Spring 2026"
    assert yc.batch_name("Summer 2026") == "Summer 2026"
    assert yc.regions_for("") == ["India", "Remote"]
    assert yc.regions_for("India|Bengaluru") == ["India"]
    assert yc.regions_for("Worldwide|Anywhere") == ["Remote"]
    assert yc.posted_from_age("3 days", NOW) == "2026-09-30T00:00:00"
    assert yc.posted_from_age("about 1 month", NOW).startswith("2026-09-03")
    assert yc.posted_from_age("over 2 years", NOW).startswith("2024-10")
    assert yc.posted_from_age("an hour", NOW).startswith("2026-10-02T23")
    assert yc.posted_from_age("", NOW) == "" and yc.posted_from_age("soon", NOW) == ""


@pytest.mark.parametrize("place, ok", [
    ("Bengaluru, KA, IN", True), ("Bengaluru", True), ("Bengaluru / San Francisco", True), ("Gurugram, HR, IN / Remote (IN)", True), ("Remote", True),
    ("Remote (US; IN)", True), ("Remote (Global)", True), ("IN / Remote (IN)", True),
    ("San Francisco, CA, US / Remote (US)", False), ("Remote (Spain)", False),
    ("Paris, IDF, FR", False), ("London, UK", False),
])
def test_only_roles_someone_in_india_can_take_are_open(place: str, ok: bool) -> None:
    assert yc.open_to_india(place) is ok


@pytest.mark.parametrize("salary, lpa, low_high, estimated", [
    ("₹800K - ₹1.2M INR", "₹8-12 LPA (YC: ₹800K - ₹1.2M INR)", (8.0, 12.0), False),
    ("₹2M - ₹3.5M INR", "₹20-35 LPA (YC: ₹2M - ₹3.5M INR)", (20.0, 35.0), False),
    ("₹10 - ₹15 INR", "₹10-15 LPA (YC: ₹10 - ₹15 INR)", (10.0, 15.0), False),
    ("₹2,500,000 - ₹4,000,000", "₹25-40 LPA (YC: ₹2,500,000 - ₹4,000,000)", (25.0, 40.0), False),
])
def test_rupee_salaries_reach_the_ledger_in_lakhs(salary, lpa, low_high, estimated) -> None:
    from hq.tools.job_tools import parse_pay

    assert yc.rupee_lakhs(salary) == lpa
    low, high, est = parse_pay(lpa)
    assert (low, high) == low_high and est is estimated


def test_yc_rupee_forms_need_the_conversion() -> None:
    from hq.tools.job_tools import parse_pay

    for raw in ("₹800K - ₹1.2M INR", "₹2M - ₹3.5M INR", "₹10 - ₹15 INR"):
        assert parse_pay(raw) is None
    assert yc.rupee_lakhs("₹25L - ₹40L") == "₹25-40 LPA (YC: ₹25L - ₹40L)"


def test_a_stated_low_band_without_a_unit_is_penalised_as_stated() -> None:
    """Clinikally's DevSecOps role, "₹5 - ₹6 INR", scored 7 on 2026-10-03
    while it was marked approx."""
    from hq.tools.job_tools import fit_score

    fit = fit_score("DevSecOps Engineer", experience_band="1+ years",
                    compensation=yc.rupee_lakhs("₹5 - ₹6 INR"), location="Gurugram, HR, IN")
    assert fit[0] <= 4


def test_the_us_visa_field_is_kept_only_for_us_seats() -> None:
    us = _job(7, "Engineer", place="San Francisco, CA, US / Remote (US)")
    india = _job(8, "Engineer", place="Gurugram, HR, IN")
    us["visa"] = india["visa"] = "US citizen/visa only"
    rows = yc.job_rows(_company("z", "Z", [us, india]), NOW)
    assert [r["visa"] for r in rows] == ["US citizen/visa only", ""]


def test_foreign_pay_is_left_alone() -> None:
    assert yc.rupee_lakhs("$50K - $150K") == "$50K - $150K"
    assert yc.rupee_lakhs("€50K - €70K EUR") == "€50K - €70K EUR"
    assert yc.rupee_lakhs("") == ""


def test_a_posting_carries_pay_experience_and_india_but_no_people() -> None:
    rows = yc.job_rows(PAGES["acme-ai"], NOW) + yc.job_rows(PAGES["older-co"], NOW)
    backend = rows[0]
    assert backend["compensation"] == "₹25-40 LPA (YC: ₹25L - ₹40L) + 0.1% - 0.5% equity"
    assert backend["experience"] == "1+ years" and backend["role_family"] == "eng"
    assert backend["url"] == "https://www.ycombinator.com/companies/x/jobs/1"
    assert backend["location"] == "Bengaluru, KA, IN (India)"
    assert rows[-1]["location"] == "Gurugram, HR, IN (India)"
    # Roles only: on 2026-10-04 he asked for no referral finding, so a row
    # carries no founders and no contact.
    assert "people" not in backend and "Asha Rao" not in json.dumps(rows)


# --- job_feed source "yc" --------------------------------------------------------

def test_the_yc_feed_returns_recent_engineering_roles_for_india(fake) -> None:
    feed = inspect.unwrap(web_tools.job_feed)
    out = asyncio.run(feed(_ctx(), source="yc", location="India|Bengaluru|Bangalore",
                           since_days=60))
    titles = [j["title"] for j in out["jobs"]]
    # newest first; the last is a US company's role from YC's India jobs page
    assert titles == ["Backend Engineer", "Software Engineer", "Forward Deployed Engineer - India"]
    assert "Growth Marketer" not in titles                         # no query: engineering only
    assert "AI Engineer" not in titles                             # over 2 years old
    assert out["thread"] == "2 hiring YC companies read"
    assert fake.queries[0] == [["regions:India"], ["isHiring:true"]]


def test_a_query_widens_past_engineering_and_pages_are_read_once(fake) -> None:
    feed = inspect.unwrap(web_tools.job_feed)
    out = asyncio.run(feed(_ctx(), source="yc", query="marketer", since_days=0))
    assert [j["title"] for j in out["jobs"]] == ["Growth Marketer"]
    asyncio.run(feed(_ctx(), source="yc", query="engineer", since_days=0))
    assert sorted(fake.pages_read) == ["acme-ai", "bay-remote", "older-co"]   # once each


def test_india_is_read_first_and_a_us_only_remote_role_is_dropped(fake) -> None:
    feed = inspect.unwrap(web_tools.job_feed)
    out = asyncio.run(feed(_ctx(), source="yc", since_days=0))
    assert fake.queries == [[["regions:India"], ["isHiring:true"]],
                            [["regions:Remote"], ["isHiring:true"]]]
    assert set(fake.pages_read[:2]) == {"acme-ai", "older-co"} and fake.pages_read[2] == "bay-remote"
    assert "Backend Engineer, US" not in [j["title"] for j in out["jobs"]]
    assert all(j["open_to_india"] for j in out["jobs"])


def test_a_refused_search_key_is_an_error_and_read_again_next_time(fake) -> None:
    fake.refuse = True
    feed = inspect.unwrap(web_tools.job_feed)
    out = asyncio.run(feed(_ctx(), source="yc"))
    assert "could not read the yc feed" in out["error"] and yc._key is None


# --- discover_companies -------------------------------------------------------------

def test_discover_companies_lists_hiring_companies_newest_first_by_page(fake, monkeypatch) -> None:
    monkeypatch.setattr(web_tools, "MAX_COMPANIES", 1)
    discover = inspect.unwrap(web_tools.discover_companies)
    first = asyncio.run(discover(_ctx(), region="India", industry="B2B", batch="W25",
                                 resolve_boards=False))
    assert [c["name"] for c in first["companies"]] == ["Acme AI"]
    assert first["total"] == 2 and first["more"] is True and first["companies"][0]["hiring"]
    assert fake.queries[0] == [["regions:India"], ["isHiring:true"], ["industries:B2B"],
                               ["batch:Winter 2025"]]
    second = asyncio.run(discover(_ctx(), region="India", resolve_boards=False, page=1))
    assert [c["name"] for c in second["companies"]] == ["Older Co"] and second["more"] is False
    past = asyncio.run(discover(_ctx(), region="India", resolve_boards=False, page=5))
    assert "past the 2 companies" in past["error"]


def test_his_employers_are_never_listed(fake, monkeypatch) -> None:
    monkeypatch.setattr(web_tools, "private_employer", lambda name: name == "Acme AI")
    discover = inspect.unwrap(web_tools.discover_companies)
    out = asyncio.run(discover(_ctx(), region="India", resolve_boards=False))
    assert [c["name"] for c in out["companies"]] == ["Older Co"]
    feed = inspect.unwrap(web_tools.job_feed)
    jobs = asyncio.run(feed(_ctx(), source="yc", since_days=0))["jobs"]
    assert {j["company"] for j in jobs} == {"Older Co", "LiteLLM"}
    assert "acme-ai" not in fake.pages_read                         # never even opened


def test_a_us_company_on_ycs_india_page_is_found(fake) -> None:
    feed = inspect.unwrap(web_tools.job_feed)
    out = asyncio.run(feed(_ctx(), source="yc", since_days=0))
    [row] = [j for j in out["jobs"] if j["company"] == "LiteLLM"]
    assert row["open_to_india"] and "India, per YC's India jobs page" in row["location"]
    assert row["hiring_manager_active"] == "about 1 month"
    assert "india" not in fake.pages_read      # not mistaken for a company page
