"""job_feed: free public job feeds, read as leads in job_board's shape."""

from __future__ import annotations

import asyncio
import inspect
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from hq.config import settings
from hq.loader import scan
from hq.tools import web_tools
from hq.tools.registry import web_read_tools


def _ctx() -> SimpleNamespace:
    return SimpleNamespace(deps=SimpleNamespace(run_id=None, task_id=None, agent="hunter"))


def _ago(days: int) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat()


class _Resp:
    status_code = 200

    def __init__(self, body: object) -> None:
        self._body = body

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._body


def _serve(monkeypatch, pages: dict[str, object]) -> None:
    async def get(self, url, *a, **kw):
        for prefix, body in pages.items():
            if url.startswith(prefix):
                return _Resp(body)
        raise AssertionError(f"unexpected fetch {url}")

    async def emit(*a, **kw) -> None:
        return None

    monkeypatch.setattr(web_tools.httpx.AsyncClient, "get", get)
    monkeypatch.setattr(web_tools, "emit", emit)


def test_an_hn_comment_header_becomes_company_role_and_location() -> None:
    row = web_tools._hn_row({
        "id": 7,
        "created_at": "2026-09-01T15:01:54.000Z",
        "text": "Acme | Backend Engineer | Bengaluru, India | REMOTE | ₹40L"
                "<p>We build &amp; ship payments.",
    })
    assert row["company"] == "Acme"
    assert row["title"] == "Backend Engineer"
    assert "Bengaluru" in row["location"]
    assert row["remote_policy"] == "remote"
    assert row["url"] == "https://news.ycombinator.com/item?id=7"
    assert "payments" in row["description"]


def test_an_hn_header_that_puts_the_site_second_still_names_the_role() -> None:
    row = web_tools._hn_row({"id": 8, "text": "CyberAtlas | https://cyberatlas.ai | Software"
                             " Engineer | REMOTE Worldwide<p>x"})
    assert row["title"] == "Software Engineer"
    assert row["location"] == "REMOTE Worldwide"


def test_recent_sorts_newest_first_and_keeps_undated_rows_last() -> None:
    jobs = [
        {"title": "old", "posted": _ago(60)},
        {"title": "undated", "posted": ""},
        {"title": "new", "posted": _ago(1)},
        {"title": "mid", "posted": _ago(10)},
    ]
    assert [j["title"] for j in web_tools._recent(jobs, 30)] == ["new", "mid", "undated"]
    assert [j["title"] for j in web_tools._recent(jobs, 0)] == ["new", "mid", "old", "undated"]
    cut = [{"title": "cut", "posted": web_tools._job_date("2020-05-20T08:44:45.357+00:00")}]
    assert web_tools._recent(cut, 30) == []


def test_hn_feed_reads_the_latest_hiring_thread_and_filters(monkeypatch) -> None:
    _serve(monkeypatch, {
        "https://hn.algolia.com/api/v1/search_by_date": {"hits": [
            {"objectID": "2", "title": "Ask HN: Who wants to be hired? (September 2026)"},
            {"objectID": "1", "title": "Ask HN: Who is hiring? (September 2026)"},
        ]},
        "https://hn.algolia.com/api/v1/items/1": {"children": [
            {"id": 10, "created_at": _ago(3), "text": "Acme | Backend Engineer | India | Remote<p>x"},
            {"id": 11, "created_at": _ago(3), "text": "Blip | Senior SRE | Berlin<p>x"},
            {"id": 12, "created_at": _ago(3), "text": ""},
        ]},
    })
    feed = inspect.unwrap(web_tools.job_feed)
    out = asyncio.run(feed(_ctx(), source="hn_hiring", query="backend", location="India"))
    assert out["thread"] == "Ask HN: Who is hiring? (September 2026)"
    assert out["total"] == 2
    assert [j["company"] for j in out["jobs"]] == ["Acme"]


def test_a_remote_board_row_keeps_pay_and_worldwide_location(monkeypatch) -> None:
    _serve(monkeypatch, {"https://himalayas.app/jobs/api/search": {"jobs": [{
        "title": "Backend Engineer", "companyName": "Zed", "locationRestrictions": [],
        "pubDate": int((datetime.now(UTC) - timedelta(days=2)).timestamp()),
        "minSalary": 50000, "maxSalary": 70000, "currency": "USD",
        "guid": "https://himalayas.app/companies/zed/jobs/backend-1",
    }]}})
    feed = inspect.unwrap(web_tools.job_feed)
    out = asyncio.run(feed(_ctx(), source="himalayas", query="backend",
                           location="India|Worldwide"))
    job = out["jobs"][0]
    assert job["location"] == "Worldwide"
    assert job["compensation"].startswith("50000-70000 USD")


def test_feed_drops_the_owners_employer_and_refuses_unknown_sources(monkeypatch) -> None:
    monkeypatch.setattr(settings(), "private_employers", ("Acmecorp",))
    _serve(monkeypatch, {"https://remotive.com/api/remote-jobs": {"jobs": [
        {"id": 1, "title": "Backend Engineer", "company_name": "Acmecorp",
         "candidate_required_location": "Worldwide", "publication_date": _ago(1)},
    ]}})
    feed = inspect.unwrap(web_tools.job_feed)
    out = asyncio.run(feed(_ctx(), source="remotive", query="backend"))
    assert "acmecorp" not in str(out).lower()
    assert "unknown source" in asyncio.run(feed(_ctx(), source="naukri"))["error"]


def test_job_feed_is_a_web_read_tool_hunter_holds() -> None:
    assert "job_feed" in web_read_tools()
    assert "job_feed" in scan()["hunter"].base_tool_names()


def test_a_board_says_when_only_the_date_filter_emptied_it(monkeypatch) -> None:
    _serve(monkeypatch, {"https://api.ashbyhq.com/": {"jobs": [
        {"id": "a", "title": "Backend Engineer", "location": "Bengaluru",
         "publishedAt": _ago(90), "jobUrl": "https://jobs.ashbyhq.com/x/a"},
    ]}})
    board = inspect.unwrap(web_tools.job_board)
    old = asyncio.run(board(_ctx(), provider="ashby", company="x", since_days=30))
    assert "none was posted in the last 30 days" in old["error"]
    every = asyncio.run(board(_ctx(), provider="ashby", company="x"))
    assert every["jobs"][0]["posted"].startswith(_ago(90)[:10])
