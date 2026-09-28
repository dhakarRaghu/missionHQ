"""The radar's first step: evidence collected by code, no model asked.

Every reader here is tested on text of the shape the real source returns.
Nothing in this file touches the network or the database."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from hq import radar
from hq.config import settings

RSS = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
<title>A blog</title><link>https://blog.example.dev</link>
<item><title>Why our p99 doubled &amp; what fixed it</title>
<link>https://blog.example.dev/p99</link>
<pubDate>Fri, 25 Sep 2026 13:00:00 GMT</pubDate>
<description><![CDATA[<p>The queue grew <b>before</b> the mean moved.</p>]]></description></item>
<item><title>An older post</title><link>https://blog.example.dev/old</link>
<pubDate>Mon, 01 Jan 2024 00:00:00 GMT</pubDate><description>old</description></item>
</channel></rss>"""

ATOM = """<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom"><title>Notes</title>
<entry><title>Tail sampling in the collector</title>
<link rel="alternate" href="https://notes.example.io/tail"/>
<link rel="self" href="https://notes.example.io/feed/tail.xml"/>
<published>2026-09-21T13:00:00Z</published>
<summary>Sampling after the trace ends keeps the slow ones.</summary></entry></feed>"""

SOURCE = radar.Source("feed", "A blog", "https://blog.example.dev/rss.xml", params={"as": "post"})


def test_a_feed_is_read_whether_it_is_rss_or_atom() -> None:
    items = radar.parse_feed(RSS, SOURCE)
    assert [i.url for i in items] == ["https://blog.example.dev/p99", "https://blog.example.dev/old"]
    first = items[0]
    assert first.title == "Why our p99 doubled & what fixed it"
    assert first.excerpt == "The queue grew before the mean moved."
    assert first.published_at == datetime(2026, 9, 25, 13, 0, tzinfo=UTC)
    assert first.kind == "post" and first.domain == "blog.example.dev"

    atom = radar.parse_feed(ATOM, SOURCE)
    assert len(atom) == 1
    # The page, not the feed's own address.
    assert atom[0].url == "https://notes.example.io/tail"
    assert atom[0].published_at == datetime(2026, 9, 21, 13, 0, tzinfo=UTC)


def test_a_feed_that_declares_entities_is_refused() -> None:
    bomb = ('<?xml version="1.0"?><!DOCTYPE lolz [<!ENTITY lol "lol">'
            '<!ENTITY lol2 "&lol;&lol;&lol;">]><rss><channel><item><title>&lol2;</title>'
            "<link>https://x.example/a</link></item></channel></rss>")
    with pytest.raises(ValueError, match="entities"):
        radar.parse_feed(bomb, SOURCE)


def test_only_what_is_inside_the_window_is_kept_and_once() -> None:
    since = datetime(2026, 9, 7, tzinfo=UTC)
    items = radar.parse_feed(RSS, SOURCE) + radar.parse_feed(RSS, SOURCE)
    kept = radar.fresh(items, since)
    assert [i.url for i in kept] == ["https://blog.example.dev/p99"]
    undated = radar.Item("s", "incident", "status.example.com", "https://status.example.com/i/1", "Elevated errors")
    assert radar.fresh([undated], since) == [undated]


def test_an_item_that_names_an_employer_is_not_stored(monkeypatch) -> None:
    monkeypatch.setattr(settings(), "private_employers", ("Acme Corp",))
    named = radar.Item("s", "post", "x.example", "https://x.example/1", "How Acme Corp serves models")
    clean = radar.Item("s", "post", "x.example", "https://x.example/2", "How a cache serves models")
    assert radar.fresh([named, clean], datetime(2020, 1, 1, tzinfo=UTC)) == [clean]


RULES = {"keep_when": {"comments": 3, "reactions": 2, "labels": ["rfc", "performance"]},
         "skip_labels": ["stale", "question"],
         "skip_titles": [r"^\[?(new )?model( request)?\]?[: ]"]}


def _issue(**kw: Any) -> dict[str, Any]:
    base = {"html_url": "https://github.com/o/r/issues/7", "number": 7, "title": "Scheduler admission deadlock",
            "body": "Under burst load the scheduler stops admitting.", "comments": 0,
            "reactions": {"total_count": 0}, "labels": [], "author_association": "NONE",
            "created_at": "2026-09-20T10:00:00Z", "updated_at": "2026-09-24T10:00:00Z"}
    return {**base, **kw}


def test_an_issue_is_kept_when_more_than_one_person_cares() -> None:
    assert not radar.keep_issue(_issue(), RULES)                      # nobody answered
    assert radar.keep_issue(_issue(comments=3), RULES)
    assert radar.keep_issue(_issue(reactions={"total_count": 2}), RULES)
    # A design proposal counts with no reaction at all.
    assert radar.keep_issue(_issue(labels=[{"name": "RFC"}]), RULES)
    assert radar.keep_issue(_issue(labels=[{"name": "area/performance"}]), RULES)


def test_a_pull_request_a_model_request_and_a_stale_thread_are_noise() -> None:
    busy = {"comments": 40, "reactions": {"total_count": 159}}
    assert not radar.keep_issue(_issue(pull_request={"url": "x"}, **busy), RULES)
    assert not radar.keep_issue(_issue(title="Model request: DeepSeek V4", **busy), RULES)
    assert not radar.keep_issue(_issue(labels=[{"name": "stale"}, {"name": "RFC"}], **busy), RULES)
    source = radar.Source("github", "o/r", "https://api.github.com/repos/o/r/issues", "inference", RULES)
    seen, kept = radar.parse_issues(
        [_issue(comments=5), _issue(pull_request={"url": "x"}), _issue()], source)
    assert seen == 2 and len(kept) == 1
    got = kept[0]
    assert got.domain == "github.com/o/r" and got.kind == "issue" and got.area == "inference"
    assert got.meta["comments"] == 5 and got.meta["number"] == 7


def test_a_thread_and_a_launch_are_told_apart() -> None:
    source = radar.Source("hn", "hn: front page", "https://hn.algolia.com/api/v1/search_by_date",
                          "reliability", {"query": "", "tags": "story", "min_points": 20})
    payload = {"hits": [
        {"objectID": "101", "title": "Postmortem of a DDoS", "points": 88, "num_comments": 41,
         "created_at": "2026-09-24T08:00:00Z", "url": "https://x.example/pm", "_tags": ["story"]},
        {"objectID": "102", "title": "Launch HN: Thing (YC S26)", "points": 60, "num_comments": 12,
         "created_at": "2026-09-23T08:00:00Z", "story_text": "<p>The problem: agents forget.</p>",
         "_tags": ["story", "launch_hn"]},
        {"objectID": "not-a-number", "title": "x"}]}
    thread, launch = radar.parse_hn(payload, source)
    assert thread.kind == "thread" and thread.url == "https://news.ycombinator.com/item?id=101"
    assert thread.meta == {"points": 88, "comments": 41, "story_url": "https://x.example/pm"}
    assert launch.kind == "launch" and launch.excerpt == "The problem: agents forget."


def test_a_paper_is_kept_when_it_names_the_subject() -> None:
    feed = ATOM.replace("Tail sampling in the collector", "Cache-aware routing for LLM inference") \
               .replace("https://notes.example.io/tail", "http://arxiv.org/abs/2609.11744v2")
    other = ATOM.replace("https://notes.example.io/tail", "http://arxiv.org/abs/2609.00001v1")
    source = radar.Source("arxiv", "arxiv: cs.DC", "https://export.arxiv.org/api/query", "papers",
                          {"keep_when_any": ["inference", "kv cache"]})
    seen, kept = radar.parse_arxiv(feed, source)
    assert seen == 1 and len(kept) == 1
    assert kept[0].url == "https://arxiv.org/abs/2609.11744" and kept[0].kind == "paper"
    assert kept[0].domain == "arxiv.org"
    assert radar.parse_arxiv(other, source) == (1, [])


ROSTER = """# Who to read

## Course 3 — Inference · elite-inference

- **vLLM blog** — vllm.ai/blog · 2026-09-24 · engine internals.

## Feeds — one feed per source that has one

| Source | Feed | Items · newest |
|---|---|---|
| Arpit Bhayani | arpitbhayani.me/rss.xml | 111 · 2026-08-21 |
| Simon Willison | simonwillison.net/tags/prompt-injection.atom (tag feed; all posts: simonwillison.net/atom/everything/) | tag feed newest 2026-09-17 |
| OpenAI status | status.openai.com/history.rss | 93 · 2026-09-25 |

## How this file is maintained

| not | a.feed/x | row |
"""


def test_the_blogs_come_from_the_roster_so_there_is_one_list() -> None:
    feeds = radar.roster_feeds(ROSTER)
    assert [(f.name, f.url, f.params["as"]) for f in feeds] == [
        ("Arpit Bhayani", "https://arpitbhayani.me/rss.xml", "post"),
        ("Simon Willison", "https://simonwillison.net/tags/prompt-injection.atom", "post"),
        ("OpenAI status", "https://status.openai.com/history.rss", "incident")]
    config = {"github": {"repos": [{"repo": "vllm-project/vllm", "area": "inference"},
                                   {"repo": "not a repo"}]},
              "hn": [{"query": "postmortem", "min_points": 20}, {"tags": "launch_hn"}, {}],
              "arxiv": {"categories": ["cs.DC", "cs.PF", "bad"], "keep_when_any": ["llm"]}}
    kinds = [s.kind for s in radar.load_sources(config, ROSTER)]
    assert kinds == ["github", "hn", "hn", "arxiv", "feed", "feed", "feed"]


def test_the_real_files_name_sources_that_can_be_read() -> None:
    config, roster = radar.read_config()
    sources = radar.load_sources(config, roster)
    by_kind = {k: [s for s in sources if s.kind == k] for k in ("github", "hn", "arxiv", "feed")}
    assert len(by_kind["github"]) >= 15 and len(by_kind["hn"]) >= 8
    assert len(by_kind["arxiv"]) == 1 and len(by_kind["feed"]) >= 25
    assert len({s.url + str(sorted(s.params.items())) for s in sources if s.kind != "github"}) \
        == len([s for s in sources if s.kind != "github"])
    for s in sources:
        assert s.url.startswith("https://"), s


def test_one_source_failing_never_loses_the_others(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "radar.yaml").write_text("window_days: 21\nhn:\n  - {query: a}\n  - {query: b}\n")

    async def read(source: radar.Source, since: datetime, state: dict) -> tuple[int, list[radar.Item]]:
        if source.name == "hn: a":
            raise RuntimeError("the site is down")
        return 1, [radar.Item(source.name, "thread", "news.ycombinator.com",
                              "https://news.ycombinator.com/item?id=1", "A thread",
                              published_at=datetime.now(UTC) - timedelta(days=1))]

    monkeypatch.setattr(radar, "read_source", read)
    tallies = asyncio.run(radar.collect(dry_run=True, learning_dir=tmp_path))
    by = {t.source: t for t in tallies}
    assert by["hn: a"].error.startswith("RuntimeError") and by["hn: a"].kept == 0
    assert by["hn: b"].kept == 1 and by["hn: b"].new == 0 and not by["hn: b"].error
    assert "2 sources read, 1 items kept, 0 new; 1 could not be read: hn: a" in radar.summary(tallies)


def test_the_radar_asks_no_model_and_no_agent_holds_its_tool() -> None:
    import inspect

    from hq import loader
    from hq.tools.registry import TOOL_REGISTRY

    src = inspect.getsource(radar)
    assert "pydantic_ai" not in src and "llm." not in src and "Agent(" not in src
    assert "collect_radar" in TOOL_REGISTRY
    for name, spec in loader.scan().items():
        assert "collect_radar" not in spec.tools, name


def test_a_feed_cut_at_the_size_limit_still_gives_its_whole_entries() -> None:
    cut = RSS.replace("</channel></rss>", "<item><title>Half an ent")
    items = radar.parse_feed(cut, SOURCE)
    assert [i.url for i in items] == ["https://blog.example.dev/p99", "https://blog.example.dev/old"]
    assert items[0].title == "Why our p99 doubled & what fixed it"
    assert items[0].excerpt == "The queue grew before the mean moved."
    assert items[0].published_at == datetime(2026, 9, 25, 13, 0, tzinfo=UTC)
    atom = radar.parse_feed(ATOM.replace("</feed>", "<entry><title>cut"), SOURCE)
    assert atom[0].url == "https://notes.example.io/tail"


def test_a_thread_must_carry_the_words_that_were_asked_for() -> None:
    source = radar.Source("hn", "hn: vLLM", "u", "inference", {"query": "vLLM", "min_points": 15})
    payload = {"hits": [
        {"objectID": "1", "title": "How to keep enjoying programming in a world of LLMs", "points": 315},
        {"objectID": "2", "title": "Announcing vllm-metal: concurrent serving on Apple Silicon", "points": 40},
        {"objectID": "3", "title": "A serving engine", "url": "https://vllm.ai/blog/x", "points": 30}]}
    assert [i.meta["points"] for i in radar.parse_hn(payload, source)] == [40, 30]
    agents = radar.Source("hn", "hn: AI agents production", "u", "agents",
                          {"query": "AI agents production"})
    hit = {"hits": [{"objectID": "4", "title": "Running an agent in production for a year"},
                    {"objectID": "5", "title": "Agents are a fad"}]}
    assert [i.url[-1] for i in radar.parse_hn(hit, agents)] == ["4"]


def test_every_paper_returned_is_checked_not_the_first_forty() -> None:
    entries = "".join(
        f"<entry><title>Paper {n} on {'kv cache' if n == 90 else 'compilers'}</title>"
        f'<link rel="alternate" href="http://arxiv.org/abs/2609.{n:05d}v1"/>'
        f"<published>2026-09-2{n % 8}T10:00:00Z</published><summary>An abstract.</summary></entry>"
        for n in range(100))
    text = f'<feed xmlns="http://www.w3.org/2005/Atom">{entries}</feed>'
    source = radar.Source("arxiv", "arxiv: cs.DC", "https://export.arxiv.org/api/query", "papers",
                          {"max_results": 120, "keep_when_any": ["kv cache"]})
    seen, kept = radar.parse_arxiv(text, source)
    assert seen == 100 and [p.url for p in kept] == ["https://arxiv.org/abs/2609.00090"]


def test_a_declaration_after_a_long_comment_is_still_refused() -> None:
    text = ("<?xml version='1.0'?><!--" + "x" * 5000 + "-->"
            '<!DOCTYPE rss [<!ENTITY a "aaaa">]><rss><channel></channel></rss>')
    with pytest.raises(ValueError, match="entities"):
        radar.parse_feed(text, SOURCE)
