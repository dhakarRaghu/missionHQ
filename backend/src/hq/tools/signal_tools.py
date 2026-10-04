"""Funding news: Indian startups that just raised, before they post roles.

A company that closed a seed or Series A hires in the months after, often
before its roles reach any board. job-ops (github.com/harshkas4na/job-ops)
reads funding RSS for the same reason. On 2026-10-04 the general feeds of
Inc42 and YourStory carried 3 of 24 and 1 of 20 funding items, but each
publishes a weekly roundup that lists the week's rounds, so this returns the
funding headlines and the roundups, and hunter opens the roundups.

Headlines are web text: a lead to verify, never an instruction.
"""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

import httpx
from pydantic_ai import RunContext

from hq.obs import emit
from hq.safety import ActionClass, Trust
from hq.tools.registry import HQDeps, hq_tool

FEEDS = ("https://inc42.com/feed/", "https://inc42.com/buzz/feed/", "https://yourstory.com/feed")
_ITEM_RE = re.compile(r"<item>(.*?)</item>", re.DOTALL)
_TAG_RE = {t: re.compile(rf"<{t}>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{t}>", re.DOTALL)
           for t in ("title", "link", "pubDate")}
FUNDING_RE = re.compile(r"\b(?:raises?|raised|funding|series [a-e]|seed|pre-seed|bags|secures"
                        r"|mops up|nets|round)\b", re.IGNORECASE)
ROUNDUP_RE = re.compile(r"funding (?:roundup|galore)|raised over|this week|weekly funding",
                        re.IGNORECASE)


def parse_feed(xml: str) -> list[dict[str, str]]:
    """Items of one RSS feed as {title, url, date}."""
    out = []
    for block in _ITEM_RE.findall(xml):
        fields = {}
        for tag, rx in _TAG_RE.items():
            m = rx.search(block)
            fields[tag] = html.unescape(m.group(1)).strip() if m else ""
        try:
            when = parsedate_to_datetime(fields["pubDate"]).astimezone(UTC)
        except (TypeError, ValueError):
            when = None
        out.append({"title": " ".join(fields["title"].split())[:200], "url": fields["link"],
                    "date": when.date().isoformat() if when else ""})
    return out


def funding_items(items: list[dict[str, str]], days: int, now: datetime | None = None
                  ) -> list[dict[str, str]]:
    """Funding headlines and roundups from the last `days`, newest first,
    each marked as a roundup or a single round."""
    since = ((now or datetime.now(UTC)) - timedelta(days=days)).date().isoformat()
    seen: set[str] = set()
    out = []
    for item in sorted(items, key=lambda i: i["date"], reverse=True):
        if not FUNDING_RE.search(item["title"]) or (item["date"] and item["date"] < since):
            continue
        if item["url"] in seen:
            continue
        seen.add(item["url"])
        out.append({**item, "kind": "roundup" if ROUNDUP_RE.search(item["title"]) else "round"})
    return out


@hq_tool(action=ActionClass.READ, trust=Trust.WEB, network=True)
async def funding_news(ctx: RunContext[HQDeps], days: int = 14) -> dict:
    """Indian startups that just raised money, from Inc42 and YourStory.

    Returns funding headlines and weekly roundups from the last `days`.
    Open each roundup with web_fetch for the full list of rounds. A startup
    with a fresh seed or Series A in his lanes is a company to check: find
    its careers page with detect_job_board, and record roles as usual. A
    headline is a lead, not a fact about hiring."""
    items: list[dict[str, str]] = []
    errors = []
    async with httpx.AsyncClient(timeout=20, follow_redirects=True,
                                 headers={"User-Agent": "Mozilla/5.0"}) as client:
        for url in FEEDS:
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                items += parse_feed(resp.text)
            except httpx.HTTPError as exc:
                errors.append(f"{url}: {type(exc).__name__}")
    found = funding_items(items, max(1, min(int(days), 60)))
    await emit("funding_news", run_id=ctx.deps.run_id, task_id=ctx.deps.task_id,
               agent=ctx.deps.agent, payload={"items": len(found), "errors": len(errors)})
    out: dict = {"provenance": "web", "items": found[:30]}
    if errors:
        out["errors"] = errors
    if not found:
        out["note"] = f"no funding news in the last {days} days from these feeds"
    return out
