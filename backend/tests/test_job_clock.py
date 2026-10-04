"""The follow-up clock on what he applied to, the lines sage writes from it,
and the funding feed. No network, no model."""

from __future__ import annotations

import asyncio
from datetime import date

from hq import job_clock, outreach
from hq.api import rest


def test_the_pipeline_lines_name_what_is_due() -> None:
    from hq import continuity

    due = {"follow_ups": [{"company": "Acme", "role": "Backend Engineer",
                           "applied_at": date(2026, 9, 27), "touches": 1}],
           }
    lines = continuity.render_pipeline(due)
    assert lines[0].startswith("- Follow up: Acme — Backend Engineer (applied 2026-09-27, touch 2")
    assert continuity.render_pipeline({"follow_ups": []}) == ["- nothing due"]
    assert "ghosted" in rest.JOB_STATUSES
    assert continuity.render_funnel([{"channel": "yc", "found": 5, "strong": 1,
                                      "applied": 1, "interviewing": 0, "offers": 0}]) == [
        "- yc: found 5, strong 1, applied 1, interviewing 0, offers 0"]


FEED = """<rss><channel>
<item><title><![CDATA[From Simple Energy To Arivihan — Indian Startups Raised Over $233 Mn This Week]]></title>
<link>https://inc42.com/r1</link><pubDate>Sat, 03 Oct 2026 10:00:00 +0530</pubDate></item>
<item><title>Seeds Fincap Raises &#8377;100 Cr To Scale Lending Tech</title>
<link>https://inc42.com/r2</link><pubDate>Thu, 01 Oct 2026 09:00:00 +0530</pubDate></item>
<item><title>Is Apple Pay&#8217;s India Entry Too Late?</title>
<link>https://inc42.com/n1</link><pubDate>Sat, 03 Oct 2026 08:00:00 +0530</pubDate></item>
<item><title>Old Startup Bags Seed Round</title>
<link>https://inc42.com/old</link><pubDate>Mon, 01 Jun 2026 09:00:00 +0530</pubDate></item>
</channel></rss>"""


def test_funding_news_keeps_recent_rounds_and_marks_roundups() -> None:
    from datetime import UTC, datetime

    from hq.tools import signal_tools as st

    items = st.parse_feed(FEED)
    assert len(items) == 4 and items[1]["title"] == "Seeds Fincap Raises ₹100 Cr To Scale Lending Tech"
    found = st.funding_items(items + items, days=14, now=datetime(2026, 10, 4, tzinfo=UTC))
    assert [(f["kind"], f["url"]) for f in found] == [
        ("roundup", "https://inc42.com/r1"), ("round", "https://inc42.com/r2")]


def test_the_clock_ghosts_only_after_the_last_touch(monkeypatch) -> None:
    seen: list[tuple[str, tuple]] = []

    async def fetch(sql, args=()):
        seen.append((sql, args))
        return []

    monkeypatch.setattr(job_clock.db, "fetch", fetch)
    on = date(2026, 10, 4)
    assert asyncio.run(job_clock.apply_clocks(on)) == {"ghosted": 0}
    assert asyncio.run(job_clock.pipeline_due(on)) == {"follow_ups": []}
    ghost_sql, ghost_args = seen[0]
    due_sql, due_args = seen[1]
    assert "touches >= %s" in ghost_sql and ghost_args == (on, outreach.MAX_TOUCHES)
    assert "touches < %s" in due_sql and due_args == (on, outreach.MAX_TOUCHES)
    assert "ghosted" in rest._CLOCK_STOPS and "interviewing" in rest._CLOCK_STOPS
