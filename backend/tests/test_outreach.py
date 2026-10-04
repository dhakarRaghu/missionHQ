"""The job pipeline past "found": where a role came from and one row per role.
Pure rules; no database, no model."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from hq import job_retention, outreach
from hq.tools import job_tools


@pytest.mark.parametrize("source, provider, url, channel", [
    ("LinkedIn Jobs", "", "https://www.linkedin.com/jobs/view/1", "linkedin"),
    ("yc", "", "https://www.ycombinator.com/companies/x/jobs/1", "yc"),
    ("Y", "", "https://www.ycombinator.com/companies/x/jobs", "yc"),
    ("HN", "", "https://news.ycombinator.com/item?id=1", "hn"),
    ("himalayas", "", "https://himalayas.app/jobs/1", "himalayas"),
    ("Board sweep 2026-10-02: ashby/cardboard read", "", "https://jobs.ashbyhq.com/x", "ats"),
    ("lever/meesho", "", "https://jobs.lever.co/meesho/1", "ats"),
    ("", "greenhouse", "https://boards.greenhouse.io/x/jobs/1", "ats"),
    ("", "", "https://careers.example.com/1", "company_site"),
    ("", "", "", "other"),
])
def test_every_free_text_source_becomes_one_channel(source, provider, url, channel) -> None:
    assert outreach.channel_of(source, provider, url) == channel


def test_one_role_read_with_and_without_a_location_is_one_row() -> None:
    """Clera, Flexibits and CareerJumpship were each stored twice on 2026-10-04."""
    old = "fallback:clera (getclera.com)|backend engineer|worldwide (remote, per feed)"
    assert outreach.same_posting(old, "Clera", "Backend  Engineer", "")
    assert outreach.same_posting(old, "Clera (getclera.com)", "backend engineer",
                                 "Worldwide (remote, per feed)")
    # Two cities are two postings, as before.
    blr = outreach.fallback_key("Acme", "Software Engineer", "Bengaluru")
    assert not outreach.same_posting(blr, "Acme", "Software Engineer", "London")
    assert not outreach.same_posting(blr, "Acme Labs", "Software Engineer", "Bengaluru")
    assert not outreach.same_posting("ats:ashby:123", "Acme", "Software Engineer", "")
    assert outreach.company_key("Cardboard (YC W26)") == "cardboard"


def test_the_old_key_forms_are_looked_up() -> None:
    assert job_tools.legacy_prefixes("Clera (getclera.com)", "Backend Engineer") == [
        "fallback:clera (getclera.com)|", "fallback:clera|"]
    assert job_tools.legacy_prefixes("Acme", "x") == ["fallback:acme|"]
    assert job_tools._like("fallback:a_b%|") == "fallback:a\\_b\\%|%"


def test_a_role_removed_under_the_old_key_stays_out(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(job_retention, "_dir", lambda: tmp_path)
    now = datetime(2026, 10, 4, tzinfo=UTC)
    job_retention._write([{"dedupe_key": "fallback:flexibits|android software engineer|remote",
                           "company": "Flexibits", "role": "Android Software Engineer",
                           "status": "closed"}], now)
    hit = job_retention.removed_matching(
        lambda k: outreach.same_posting(k, "Flexibits", "Android Software Engineer", ""), now)
    assert hit and hit["company"] == "Flexibits"
    assert job_retention.removed_matching(
        lambda k: outreach.same_posting(k, "Flexibits", "iOS Engineer", ""), now) is None


def test_a_row_with_no_location_takes_the_first_city_then_a_second_city_is_new(monkeypatch) -> None:
    import asyncio

    ledger = {"fallback:acme|software engineer|"}

    async def fetch(sql, args=()):
        if sql.startswith("UPDATE"):
            new, old, _ = args
            if old in ledger and new not in ledger:
                ledger.discard(old)
                ledger.add(new)
                return [{"dedupe_key": new}]
            return []
        return [{"dedupe_key": k} for k in sorted(ledger)]

    monkeypatch.setattr(job_tools.db, "fetch", fetch)
    blr = outreach.fallback_key("Acme", "Software Engineer", "Bengaluru")
    ldn = outreach.fallback_key("Acme", "Software Engineer", "London")
    assert asyncio.run(job_tools._resolve_key(blr, "Acme", "Software Engineer", "Bengaluru")) == blr
    assert ledger == {blr}
    assert asyncio.run(job_tools._resolve_key(ldn, "Acme", "Software Engineer", "London")) == ldn
    # Seen again with no location, it is the Bengaluru row.
    bare = outreach.fallback_key("Acme", "Software Engineer", "")
    assert asyncio.run(job_tools._resolve_key(bare, "Acme", "Software Engineer", "")) == blr
