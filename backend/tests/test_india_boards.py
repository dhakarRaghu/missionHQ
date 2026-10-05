"""Cutshort, Wellfound and Hirist: rows, the open/stale/closed verdict and the
company flags. Offline: sample JSON in the shape each site served on
2026-10-05, and a mock transport for the posting checks."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime

import httpx

from hq import india_boards as ib
from hq import outreach

NOW = datetime(2026, 10, 5, tzinfo=UTC)


def test_the_site_flag_wins_then_the_age() -> None:
    assert ib.verdict(False, "2026-10-01T00:00:00", NOW)[0] == "closed"
    assert ib.verdict(True, "2026-09-25T00:00:00", NOW)[0] == "open"
    # A Hirist posting from 2025-06-20 still had status 1 on 2026-10-05.
    assert ib.verdict(True, "2025-06-20T00:00:00", NOW)[0] == "stale"
    # Wellfound's "Actively Hiring" keeps a 47-day posting open, not a 100-day one.
    assert ib.verdict(None, "2026-08-20T00:00:00", NOW, active=True)[0] == "open"
    assert ib.verdict(None, "2026-06-20T00:00:00", NOW, active=True)[0] == "stale"
    assert ib.verdict(None, "", NOW)[0] == "unknown"


def test_recruiters_are_told_from_employers() -> None:
    for name in ("Staffnixcom", "ABC Consultancy", "Jobgether", "yohrconsultancy.com",
                 "TalentHub HR Solutions", "HiringBlaze", "Pravi HR Advisory",
                 "DevsUnite (repost: Conga)"):
        assert ib.staffing(name), name
    for name in ("Exotel", "Parsewave", "Avoca AI", "exotel.com", "Shriram", "Chronicle"):
        assert not ib.staffing(name), name


def _cutshort(jobs: list[dict]) -> dict:
    return {"props": {"pageProps": {"dehydratedState": {"queries": [
        {"state": {"data": {"data": {"pageData": {"jobs": jobs}}}}}]}}}}


def test_a_cutshort_row_carries_the_company_and_its_flags() -> None:
    own = {"_id": "a1", "headline": "Frontier AI Engineer", "hiringForClient": False,
           "publicUrl": "https://cutshort.io/job/Frontier-AI-Engineer-Parsewave-papdCRmc",
           "locationsText": "Remote only", "remoteType": "remote_only",
           "salaryRangeText": "₹26L - ₹32L / yr", "expRange": {"min": 0, "max": 5},
           "jobFactSummary": {"postedDate": "2026-09-26T12:55:22.046Z"},
           "companyDetails": {"name": "Parsewave", "type": "Product", "size": "0-20",
                              "stage": "Bootstrapped", "founded": 2024,
                              "links": {"website": "https://parsewave.ai"}}}
    client = {**own, "_id": "a2", "headline": "Java Developer", "hiringForClient": True,
              "companyDetails": {"name": "Acme Staffing", "type": "Services"}}
    rows = ib.cutshort_rows(_cutshort([own, client]), NOW)
    assert rows[0]["company"] == "Parsewave" and rows[0]["posting"] == "open"
    assert rows[0]["experience"] == "0-5 years" and rows[0]["remote_policy"] == "remote"
    assert "Product; 0-20 people; Bootstrapped; founded 2024" in rows[0]["company_facts"]
    assert rows[0]["flags"] == []
    assert rows[1]["flags"] == ["staffing repost: posted for a client", "services firm"]


def test_a_wellfound_row_reads_the_apollo_cache() -> None:
    cache = {
        "Badge:ACTIVELY_HIRING": {"label": "Actively Hiring"},
        "StartupResult:1": {"name": "Avoca AI", "companySize": "SIZE_51_200",
                            "highConcept": "24/7 AI agents",
                            "badges": [{"__ref": "Badge:ACTIVELY_HIRING"}],
                            "highlightedJobListings": [{"__ref": "JobListingSearchResult:9"}]},
        "JobListingSearchResult:9": {"id": "4607436", "slug": "deployment-engineer",
                                     "title": "Deployment Engineer", "remote": True,
                                     "locationNames": ["Bengaluru"],
                                     "acceptedRemoteLocationNames": ["India"],
                                     "liveStartAt": int(datetime(2026, 8, 20, tzinfo=UTC).timestamp()),
                                     "yearsExperienceMin": 2, "compensation": ""},
    }
    [row] = ib.wellfound_rows({"props": {"pageProps": {"apolloState": {"data": cache}}}}, NOW)
    assert row["url"] == "https://wellfound.com/jobs/4607436-deployment-engineer"
    assert row["location"] == "Bengaluru, Remote: India" and row["experience"] == "2+ years"
    assert row["company_facts"] == "51-200 people; 24/7 AI agents; Actively Hiring"
    assert row["posting"] == "open" and "Actively Hiring" in row["posting_note"]


def test_a_hirist_row_takes_the_company_from_the_title() -> None:
    open_row = {"id": 1675108, "title": "Exotel - Integration Engineer I", "status": 1,
                "min": 1, "max": 3, "createdTimeMs": 1790512360577, "hideSal": 1,
                "locations": [{"name": "Bangalore"}],
                "companyData": {"companyName": "EXOTEL TECHCOM PRIVATE LIMITED",
                                "ambitionBoxInfo": {"aggregateRatingOneDecimal": 2.8,
                                                    "reviewsCount": 201}}}
    closed = {**open_row, "id": 1, "status": 0, "title": "Java Developer",
              "companyData": {"companyName": "Yoh Consultancy"}}
    role_first = {**open_row, "id": 2, "title": "Data Engineer - Supply Chain Analytics",
                  "companyData": {"companyName": "HiringBlaze"}}
    rows = ib.hirist_rows([open_row, closed, role_first], NOW)
    assert rows[2]["company"] == "HiringBlaze" and "staffing repost" in rows[2]["flags"]
    assert rows[0]["company"] == "Exotel" and rows[0]["url"] == "https://www.hirist.tech/j/1675108"
    assert "AmbitionBox 2.8 from 201 reviews" in rows[0]["company_facts"]
    assert rows[0]["posting"] == "open" and rows[0]["compensation"] == ""
    assert rows[1]["posting"] == "closed"
    assert "staffing repost" in rows[1]["flags"] and "no company named in the title" in rows[1]["flags"]


def test_the_sites_are_channels() -> None:
    assert outreach.channel_of("", url="https://cutshort.io/job/x") == "cutshort"
    assert outreach.channel_of("", url="https://wellfound.com/jobs/1-x") == "wellfound"
    assert outreach.channel_of("", url="https://www.hirist.tech/j/1") == "hirist"


def _check(url: str, handler) -> dict:
    async def run() -> dict:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await ib.posting_status(client, url, NOW)
    return asyncio.run(run())


def test_a_posting_that_is_gone_or_marked_closed_is_closed() -> None:
    assert _check("https://cutshort.io/job/x", lambda r: httpx.Response(404))["posting"] == "closed"
    page = ('<script id="__NEXT_DATA__" type="application/json">'
            + json.dumps(_cutshort([])).replace('"jobs": []', '"jobValid": false')
            + "</script>")
    out = _check("https://cutshort.io/job/x", lambda r: httpx.Response(200, text=page))
    assert out["posting"] == "closed"


def test_an_old_hirist_posting_is_stale_and_names_its_poster() -> None:
    detail = {"data": {"id": 1500000, "title": "SolarEdge - Engineer", "status": 1,
                       "createdTime": 1750444200000, "applyCount": 12,
                       "creatorDomainName": "solaredge.com", "companyData": {}}}
    out = _check("https://www.hirist.tech/j/engineer-1500000",
                 lambda r: httpx.Response(200, json=detail))
    assert out["posting"] == "stale" and out["applicants"] == 12
    assert out["posted_by_domain"] == "solaredge.com"


def test_the_feed_drops_what_record_job_would_close_and_counts_it() -> None:
    from hq.tools.web_tools import _india_gates

    def row(**kw):
        base = {"title": "Software Engineer", "experience": "1-3 years", "compensation": "",
                "posting": "open", "flags": []}
        return {**base, **kw}

    kept, dropped = _india_gates([
        row(),
        row(posting="stale"),
        row(flags=["staffing repost"]),
        row(flags=["services firm"]),
        row(experience="3-6 years"),
        row(title="Senior Backend Engineer"),
        row(compensation="₹6L - ₹10L / yr"),
        row(compensation="est. 10-12 LPA"),
        row(title="Retail Sales Consultant"),
    ])
    assert len(kept) == 2   # the plain row, and the one whose pay is only an estimate
    assert dropped == {"closed_or_stale": 1, "staffing": 1, "services_firm": 1,
                       "not_engineering": 1, "gated": 2, "stated_pay_under_bar": 1}
    for title in ("Golang Backend Engineer", "Junior Member of Technical Staff - AI/ML",
                  "Forward Deployed Engineer - Python", "SDE-1", "Data Scientist"):
        assert ib.tech_title(title), title
