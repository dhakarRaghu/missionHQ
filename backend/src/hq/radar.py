"""The idea radar, step one: collect what people report as hard.

He asked where project ideas come from when nobody hands him one, and drew
the line for what is worth two weeks: not something a coding assistant
finishes in a session, but a problem that makes him measure, read unfamiliar
code and decide. Asked for "project ideas", a model returns the same generic
list to everyone. So nothing here asks a model anything. Code collects the
places where people write down what is hard for them:

- issues and design proposals in the projects he studies,
- threads people argued about,
- papers in the systems categories,
- posts from the roster's feeds, and incident titles from status feeds.

Each thing found is one row in `hq.radar_items`, keyed by its url. A later
step reads the rows, and an idea reaches him only when quotes from two or
more sites stand behind it.

What is collected is text written by strangers. It is stored bounded, it is
never an instruction, and a row that names an employer of his is not stored.
"""

from __future__ import annotations

import asyncio
import html as html_lib
import logging
import re
import xml.etree.ElementTree as ET
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, urlparse

import httpx
import yaml

from hq import db, privacy
from hq.config import settings
from hq.obs import emit
from hq.tools import web_tools

log = logging.getLogger(__name__)

RADAR_FILE = "radar.yaml"
ROSTER_FILE = "sources.md"
EXCERPT_CHARS = 4_000
TITLE_CHARS = 300
FEED_ITEMS = 40              # newest entries taken from one feed
ARXIV_PAUSE_S = 3.0          # arXiv's terms: one request every three seconds
GITHUB_FLOOR = 5             # requests left at which the trackers stop for the day
PARALLEL = 6
UA = {"User-Agent": "MissionHQ/1.0 (personal reading; one request a day per source)"}
KINDS = ("issue", "thread", "launch", "paper", "post", "incident")


@dataclass(frozen=True)
class Source:
    kind: str                # github | hn | arxiv | feed
    name: str
    url: str
    area: str = ""
    params: Mapping[str, Any] = field(default_factory=dict)


@dataclass
class Item:
    source: str
    kind: str
    domain: str
    url: str
    title: str
    excerpt: str = ""
    published_at: datetime | None = None
    area: str = ""
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class Tally:
    source: str
    found: int = 0           # what the source returned
    kept: int = 0            # what passed the source's own filter
    new: int = 0             # rows this collection added
    error: str = ""


# --- text ------------------------------------------------------------------------

_TAG_RE = re.compile(r"(?s)<(script|style)\b.*?</\1>|<[^>]+>")


def plain(text: str, limit: int = EXCERPT_CHARS) -> str:
    """Markup and entities out, whitespace settled, bounded."""
    text = html_lib.unescape(_TAG_RE.sub(" ", text or ""))
    return " ".join(text.split())[:limit]


def when(text: str) -> datetime | None:
    """A feed's date, whichever of the two common forms it uses."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        found = datetime.fromisoformat(text)
    except ValueError:
        try:
            found = parsedate_to_datetime(text)
        except (TypeError, ValueError):
            return None
    return found if found.tzinfo else found.replace(tzinfo=UTC)


def domain_of(url: str) -> str:
    host = (urlparse(url).hostname or "").lower()
    return host.removeprefix("www.")


# --- the sources -------------------------------------------------------------------

_FEED_ROW_RE = re.compile(r"^\|\s*([^|]+?)\s*\|\s*([^|\s]+)[^|]*\|")


def roster_feeds(roster: str) -> list[Source]:
    """The feeds the roster lists, read from its Feeds table so there is one
    list of blogs and not two."""
    out: list[Source] = []
    inside = False
    for line in roster.splitlines():
        if line.startswith("## "):
            inside = line.lower().startswith("## feeds")
            continue
        match = _FEED_ROW_RE.match(line) if inside else None
        if not match:
            continue
        name, feed = match.group(1), match.group(2)
        if name.lower() in {"source", "---"} or set(name) <= {"-", " "} or "." not in feed:
            continue
        url = feed if feed.startswith("http") else f"https://{feed}"
        kind = "incident" if "status" in name.lower() else "post"
        out.append(Source("feed", name, url, params={"as": kind}))
    return out


def load_sources(config: Mapping[str, Any], roster: str = "") -> list[Source]:
    out: list[Source] = []
    hub = config.get("github") or {}
    for entry in hub.get("repos") or []:
        repo = str(entry.get("repo") or "").strip()
        if re.fullmatch(r"[\w.-]+/[\w.-]+", repo):
            out.append(Source("github", repo, f"https://api.github.com/repos/{repo}/issues",
                              str(entry.get("area") or ""), hub))
    for entry in config.get("hn") or []:
        query, tags = str(entry.get("query") or ""), str(entry.get("tags") or "story")
        if query or tags != "story":
            out.append(Source("hn", f"hn: {query or tags}", "https://hn.algolia.com/api/v1/search_by_date",
                              str(entry.get("area") or ""),
                              {"query": query, "tags": tags,
                               "min_points": int(entry.get("min_points") or 0)}))
    papers = config.get("arxiv") or {}
    cats = [c for c in papers.get("categories") or [] if re.fullmatch(r"[a-z-]+\.[A-Z]{2}", str(c))]
    if cats:
        out.append(Source("arxiv", "arxiv: " + " ".join(cats), "https://export.arxiv.org/api/query",
                          "papers", {"categories": cats,
                                     "max_results": int(papers.get("max_results") or 100),
                                     "keep_when_any": papers.get("keep_when_any") or []}))
    return out + roster_feeds(roster)


def read_config(learning_dir: Path | None = None) -> tuple[dict[str, Any], str]:
    folder = learning_dir or settings().learning_dir
    try:
        config = yaml.safe_load((folder / RADAR_FILE).read_text()) or {}
    except OSError:
        config = {}
    try:
        roster = (folder / ROSTER_FILE).read_text()
    except OSError:
        roster = ""
    return (config if isinstance(config, dict) else {}), roster


# --- reading one source -------------------------------------------------------------

def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].lower()


def parse_feed(text: str, source: Source, limit: int = FEED_ITEMS) -> list[Item]:
    """The newest `limit` entries of an RSS or Atom feed. A feed that declares
    entities is refused: the parser would expand them, and no feed he reads
    needs them. The whole text is searched, because a declaration can follow
    a comment of any length."""
    lowered = text.lower()
    at = lowered.find("<!doctype")
    if "<!entity" in lowered or at >= 0 and "[" in lowered[at:at + 400]:
        raise ValueError("the feed declares entities; refused")
    try:
        root = ET.fromstring(text.lstrip("\ufeff \n\r\t"))
    except ET.ParseError:
        # A feed cut at the size limit is no longer a document, and its whole
        # entries are still there to be read: one such feed was 2.9 MB.
        return _loose_feed(text, source, limit)
    items: list[Item] = []
    for node in root.iter():
        if _local(node.tag) not in {"item", "entry"}:
            continue
        got: dict[str, str] = {}
        for child in node:
            name = _local(child.tag)
            if name == "link":
                href = child.attrib.get("href") or (child.text or "")
                if href and (child.attrib.get("rel", "alternate") == "alternate" or "link" not in got):
                    got["link"] = href.strip()
            elif name in {"title", "pubdate", "published", "updated", "date", "description",
                          "summary", "content", "encoded", "guid", "id"}:
                got.setdefault(name, "".join(child.itertext()))
        url = got.get("link") or got.get("guid") or got.get("id") or ""
        title = plain(got.get("title", ""), TITLE_CHARS)
        if not url.startswith("http") or not title:
            continue
        body = got.get("encoded") or got.get("content") or got.get("description") or got.get("summary") or ""
        items.append(Item(
            source=source.name, kind=str(source.params.get("as") or "post"),
            domain=domain_of(url) or domain_of(source.url), url=url, title=title,
            excerpt=plain(body), area=source.area,
            published_at=when(got.get("pubdate") or got.get("published") or got.get("date")
                              or got.get("updated") or "")))
        if len(items) >= limit:
            break
    return items


_BLOCK_RE = re.compile(r"(?is)<(item|entry)\b[^>]*>(.*?)</\1>")
_CDATA_RE = re.compile(r"(?s)<!\[CDATA\[(.*?)\]\]>")


def _loose(block: str, *names: str) -> str:
    for name in names:
        found = re.search(rf"(?is)<(?:\w+:)?{name}\b[^>]*>(.*?)</(?:\w+:)?{name}>", block)
        if found:
            return _CDATA_RE.sub(lambda m: m.group(1), found.group(1)).strip()
    return ""


def _loose_feed(text: str, source: Source, limit: int = FEED_ITEMS) -> list[Item]:
    """Whole entries of a feed that does not parse, read one at a time."""
    items: list[Item] = []
    for _tag, block in _BLOCK_RE.findall(text):
        href = re.search(r"""(?is)<link\b[^>]*\bhref=["']([^"']+)""", block)
        url = (href.group(1) if href else _loose(block, "link", "guid", "id")).strip()
        title = plain(_loose(block, "title"), TITLE_CHARS)
        if not url.startswith("http") or not title:
            continue
        items.append(Item(
            source=source.name, kind=str(source.params.get("as") or "post"),
            domain=domain_of(url) or domain_of(source.url), url=url, title=title,
            excerpt=plain(_loose(block, "encoded", "content", "description", "summary")),
            area=source.area,
            published_at=when(_loose(block, "pubDate", "published", "date", "updated"))))
        if len(items) >= limit:
            break
    return items


def keep_issue(issue: Mapping[str, Any], rules: Mapping[str, Any]) -> bool:
    """Whether an issue shows more than one person cares, by the rules in
    radar.yaml. A pull request, a request for a model and a stale thread are
    noise whatever their counts."""
    if issue.get("pull_request"):
        return False
    labels = {str(x.get("name") or "").lower() for x in issue.get("labels") or []
              if isinstance(x, Mapping)}
    if labels & {str(x).lower() for x in rules.get("skip_labels") or []}:
        return False
    title = str(issue.get("title") or "")
    for pattern in rules.get("skip_titles") or []:
        try:
            if re.search(str(pattern), title, re.IGNORECASE):
                return False
        except re.error:
            continue
    want = rules.get("keep_when") or {}
    wanted = {str(x).lower() for x in want.get("labels") or []}
    if any(w == label or w in label for label in labels for w in wanted):
        return True
    reactions = int((issue.get("reactions") or {}).get("total_count") or 0)
    return (int(issue.get("comments") or 0) >= int(want.get("comments") or 3)
            or reactions >= int(want.get("reactions") or 2))


def parse_issues(rows: Sequence[Mapping[str, Any]], source: Source) -> tuple[int, list[Item]]:
    """(issues seen, issues kept). Pull requests come back from the same
    endpoint: of 100 rows on one day, 86 were pull requests."""
    seen = [r for r in rows if isinstance(r, Mapping) and not r.get("pull_request")]
    items: list[Item] = []
    for issue in seen:
        if not keep_issue(issue, source.params):
            continue
        url = str(issue.get("html_url") or "")
        if not url.startswith("https://github.com/"):
            continue
        items.append(Item(
            source=source.name, kind="issue", domain=f"github.com/{source.name}".lower(),
            url=url, title=plain(str(issue.get("title") or ""), TITLE_CHARS),
            excerpt=plain(str(issue.get("body") or "")), area=source.area,
            published_at=when(str(issue.get("created_at") or "")),
            meta={"number": issue.get("number"), "comments": issue.get("comments") or 0,
                  "reactions": (issue.get("reactions") or {}).get("total_count") or 0,
                  "labels": sorted(str(x.get("name")) for x in issue.get("labels") or []
                                   if isinstance(x, Mapping)),
                  "by": str(issue.get("author_association") or "").lower(),
                  "updated_at": str(issue.get("updated_at") or "")}))
    return len(seen), items


def parse_hn(payload: Mapping[str, Any], source: Source) -> list[Item]:
    """Threads that carry the words asked for. The search forgives spelling:
    asked for "vLLM" it returned fifty threads about any LLM."""
    words = [w for w in re.findall(r"[a-z0-9]+", str(source.params.get("query") or "").lower())
             if len(w) >= 4]
    items: list[Item] = []
    for hit in payload.get("hits") or []:
        ident = str(hit.get("objectID") or "")
        title = plain(str(hit.get("title") or ""), TITLE_CHARS)
        if not ident.isdigit() or not title:
            continue
        said = set(re.findall(r"[a-z0-9]+", " ".join(
            str(hit.get(k) or "") for k in ("title", "story_text", "url")).lower()))
        if any(w not in said and w + "s" not in said and w.rstrip("s") not in said for w in words):
            continue
        launch = "launch_hn" in (hit.get("_tags") or []) or "show_hn" in (hit.get("_tags") or [])
        items.append(Item(
            source=source.name, kind="launch" if launch else "thread",
            domain="news.ycombinator.com", url=f"https://news.ycombinator.com/item?id={ident}",
            title=title, excerpt=plain(str(hit.get("story_text") or "")), area=source.area,
            published_at=when(str(hit.get("created_at") or "")),
            meta={"points": hit.get("points") or 0, "comments": hit.get("num_comments") or 0,
                  "story_url": str(hit.get("url") or "")}))
    return items


def parse_arxiv(text: str, source: Source) -> tuple[int, list[Item]]:
    """(papers returned, papers kept). A paper is kept when its title or
    abstract names one of the subjects in radar.yaml."""
    # Every paper returned is checked: the subject filter comes after this.
    papers = parse_feed(text, Source("feed", source.name, source.url, source.area, {"as": "paper"}),
                        limit=max(FEED_ITEMS, int(source.params.get("max_results") or 0)))
    wanted = [str(k).lower() for k in source.params.get("keep_when_any") or []]
    kept = []
    for paper in papers:
        body = f"{paper.title} {paper.excerpt}".lower()
        if not wanted or any(k in body for k in wanted):
            paper.domain = "arxiv.org"
            paper.url = re.sub(r"^http://", "https://", re.sub(r"v\d+$", "", paper.url))
            kept.append(paper)
    return len(papers), kept


async def _get(url: str, headers: Mapping[str, str] | None = None) -> httpx.Response:
    """One GET to a public address, never redirected to another host."""
    await web_tools.check_url(url)
    async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
        resp = await client.get(url, headers={**UA, **(headers or {})})
    resp.raise_for_status()
    if len(resp.content) > web_tools.MAX_BYTES:
        raise ValueError(f"{len(resp.content)} bytes; refused past {web_tools.MAX_BYTES}")
    return resp


async def read_source(source: Source, since: datetime, state: dict[str, Any]) -> tuple[int, list[Item]]:
    """(what the source returned, what is kept). `state` carries the GitHub
    allowance between trackers, so the last of them is not refused."""
    if source.kind == "feed":
        text, _final = await web_tools._fetch_text(source.url)
        items = parse_feed(text, source)
        return len(items), items
    if source.kind == "github":
        if state.get("github_left", 60) <= GITHUB_FLOOR:
            raise RuntimeError("the day's GitHub allowance is used; collected tomorrow")
        token = settings().github_token.strip()
        resp = await _get(
            f"{source.url}?state=open&sort=updated&direction=desc&per_page=100"
            f"&since={quote(since.strftime('%Y-%m-%dT%H:%M:%SZ'))}",
            {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
             **({"Authorization": f"Bearer {token}"} if token else {})})
        left = resp.headers.get("x-ratelimit-remaining", "")
        if left.isdigit():
            state["github_left"] = int(left)
        return parse_issues(resp.json(), source)
    if source.kind == "hn":
        floor = int(source.params.get("min_points") or 0)
        query = quote(str(source.params.get("query") or ""))
        resp = await _get(
            f"{source.url}?query={query}&tags={quote(str(source.params.get('tags') or 'story'))}"
            f"&hitsPerPage=50&numericFilters={quote(f'created_at_i>{int(since.timestamp())},points>{floor}')}")
        items = parse_hn(resp.json(), source)
        return len(items), items
    if source.kind == "arxiv":
        cats = "+OR+".join(f"cat:{c}" for c in source.params.get("categories") or [])
        await asyncio.sleep(ARXIV_PAUSE_S)
        url = (f"{source.url}?search_query={cats}&sortBy=submittedDate&sortOrder=descending"
               f"&max_results={int(source.params.get('max_results') or 100)}")
        try:
            resp = await _get(url)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code not in {406, 429, 500, 502, 503}:
                raise
            await asyncio.sleep(ARXIV_PAUSE_S * 3)
            resp = await _get(url)
        return parse_arxiv(resp.text, source)
    raise ValueError(f"unknown kind of source: {source.kind}")


# --- one collection -----------------------------------------------------------------

def fresh(items: Iterable[Item], since: datetime) -> list[Item]:
    """Inside the window, one per url, and never naming an employer of his.
    An item with no date is kept: a status feed and a few blogs carry none."""
    out: dict[str, Item] = {}
    for item in items:
        if item.published_at and item.published_at < since:
            continue
        if item.kind not in KINDS or privacy.employers_named(f"{item.title} {item.excerpt}"):
            continue
        out.setdefault(item.url, item)
    return list(out.values())


async def store(items: Sequence[Item]) -> int:
    """Rows added. An item already there keeps its row; its counts are
    brought up to date, because a thread that keeps growing is the signal."""
    added = 0
    for item in items:
        row = await db.fetchone(
            "INSERT INTO hq.radar_items (source, kind, area, domain, url, title, excerpt,"
            " published_at, meta) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
            " ON CONFLICT (url) DO UPDATE SET meta = EXCLUDED.meta"
            " RETURNING (xmax = 0) AS added",
            (item.source, item.kind, item.area, item.domain, item.url, item.title,
             item.excerpt, item.published_at, db.jsonb(item.meta)))
        added += 1 if row and row["added"] else 0
    return added


async def collect(*, dry_run: bool = False, only: str = "",
                  learning_dir: Path | None = None) -> list[Tally]:
    """Read every source once and store what is new. One source failing is
    its own line in the result and never the reason the others are lost."""
    config, roster = read_config(learning_dir)
    sources = [s for s in load_sources(config, roster) if not only or s.kind == only]
    since = datetime.now(UTC) - timedelta(days=int(config.get("window_days") or 21))
    state: dict[str, Any] = {}
    gate = asyncio.Semaphore(PARALLEL)

    async def one(source: Source) -> Tally:
        tally = Tally(source.name)
        try:
            async with gate:
                tally.found, items = await read_source(source, since, state)
            kept = fresh(items, since)
            tally.kept = len(kept)
            tally.new = 0 if dry_run else await store(kept)
        except Exception as exc:  # noqa: BLE001 — see the docstring
            tally.error = f"{type(exc).__name__}: {exc}"[:200]
        return tally

    # The trackers share one allowance, so they are read one after another.
    trackers = [s for s in sources if s.kind == "github"]
    others = [s for s in sources if s.kind != "github"]
    tallies = list(await asyncio.gather(*(one(s) for s in others)))
    for source in trackers:
        tallies.append(await one(source))
    return tallies


def summary(tallies: Sequence[Tally]) -> str:
    failed = [t for t in tallies if t.error]
    return (f"radar: {len(tallies)} sources read, {sum(t.kept for t in tallies)} items kept,"
            f" {sum(t.new for t in tallies)} new"
            + (f"; {len(failed)} could not be read: "
               + ", ".join(t.source for t in failed[:6]) if failed else ""))


async def collect_and_report(*, run_id: str | None = None, agent: str | None = None) -> str:
    tallies = await collect()
    await emit("radar.collected", run_id=run_id, agent=agent, payload={
        "sources": len(tallies), "kept": sum(t.kept for t in tallies),
        "new": sum(t.new for t in tallies),
        "failed": [{"source": t.source, "error": t.error} for t in tallies if t.error][:20]})
    return summary(tallies)
