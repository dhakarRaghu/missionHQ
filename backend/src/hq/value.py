"""The weekly value report: what Mission HQ made, and what he did with it.

Seven days, counted from the tables, no model call:

- lessons written vs read (`hq.lessons.created_at`, `read_at`),
- concept taps, got it vs lost me (`hq.concept_signals`),
- jobs he moved (`job.updated` events that changed a status; only the
  console's `update_job` emits them, so every one is his),
- posts written vs drafts (posts are counted in the dated batches sage's
  daily-posts skill puts at the top of `projects/content/ideas.md`, drafts
  from `post.drafted` events;
  nothing records a post going out, so that one says "not recorded"),
- model spend (`hq.model_calls`) and tutor's spend per lesson written.

Its reason to exist is the plan's throttle rule: two weeks of decline in a
role's numbers reopens that role's design. So it states counts, not
judgements, and a source it cannot read shows as not recorded rather than as
a zero that looks like a fact.

`summarize` is pure, so the arithmetic is tested without a database;
`week_report` gathers the rows and never raises.
"""

from __future__ import annotations

import asyncio
import logging
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any

from hq import db, memory

log = logging.getLogger(__name__)

DAYS = 7
IDEAS_PATH = "projects/content/ideas.md"
NOT_RECORDED = "not recorded"
LESSON_AGENT = "tutor"
_STATUS_FIELD = "status = %s"      # how update_job names a status change in its event
_BATCH_RE = re.compile(r"^##\s+(\d{4}-\d{2}-\d{2})")
# One idea is one top-level item: a `- ` bullet (the content-ideas skill's
# shape) or a numbered item (older batches). Its indented `why:` and
# `Sources:` lines, and any copy under it, are not ideas.
_IDEA_RE = re.compile(r"^(?:-|\d+\.)\s+\S")
# Since 2026-10-02 a daily batch can hold one post, which has no `---`. A
# body with no separator and no list item, short enough to be a post
# (content_tools.POST_WORDS), is one post.
SINGLE_POST_WORDS = 160


def _at(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return None


def count_ideas(markdown: str | None, since: date, until: date) -> int | None:
    """Posts (or, in older batches, ideas) in the dated `## YYYY-MM-DD`
    batches inside the window. A daily posts batch separates its posts with a
    line holding only `---`; an older ideas batch lists one top-level `- ` or
    numbered item per idea. None when the file could not be read."""
    if markdown is None:
        return None
    batches: list[tuple[bool, list[str]]] = []
    for line in markdown.splitlines():
        head = _BATCH_RE.match(line)
        if head:
            try:
                day = date.fromisoformat(head.group(1))
            except ValueError:
                batches.append((False, []))
                continue
            batches.append((since <= day <= until, []))
        elif line.startswith("## "):
            batches.append((False, []))
        elif batches:
            batches[-1][1].append(line)
    n = 0
    for inside, lines in batches:
        if not inside:
            continue
        separators = sum(1 for ln in lines if ln.strip() == "---")
        if separators:
            n += separators + 1
            continue
        ideas = sum(1 for ln in lines if _IDEA_RE.match(ln))
        text = "\n".join(lines).strip()
        if not ideas and text and len(text.split()) <= SINGLE_POST_WORDS:
            ideas = 1
        n += ideas
    return n


def summarize(*, since: datetime, until: datetime,
              lessons: list[dict[str, Any]], taps: list[dict[str, Any]] | None,
              job_events: list[dict[str, Any]], job_status: dict[str, str],
              spend: list[dict[str, Any]], ideas: int | None,
              drafted: int) -> dict[str, Any]:
    """The report from its rows. Every input may be empty; nothing divides by zero."""
    written = [r for r in lessons if (t := _at(r.get("created_at"))) and since <= t <= until]
    read = [r for r in lessons if (t := _at(r.get("read_at"))) and since <= t <= until]
    by_kind: dict[str, int] = {}
    for r in written:
        kind = str(r.get("kind") or "?")
        by_kind[kind] = by_kind.get(kind, 0) + 1

    tap_counts = {"got_it": 0, "lost_me": 0}
    for r in taps or []:
        verdict = str(r.get("verdict") or "")
        if verdict in tap_counts:
            tap_counts[verdict] += int(r.get("n") or 0)

    moved: list[str] = []
    for e in job_events:
        payload = e.get("payload")
        if not isinstance(payload, dict):
            continue
        fields = payload.get("fields") or []
        job_id = str(payload.get("job_id") or "")
        if job_id and _STATUS_FIELD in fields and job_id not in moved:
            moved.append(job_id)
    now_status: dict[str, int] = {}
    for job_id in moved:
        status = job_status.get(job_id, "?")
        now_status[status] = now_status.get(status, 0) + 1

    by_agent: dict[str, float] = {}
    for r in spend:
        agent = str(r.get("agent") or "?")
        by_agent[agent] = by_agent.get(agent, 0.0) + float(r.get("cost") or 0)
    total = round(sum(by_agent.values()), 4)
    lesson_spend = round(by_agent.get(LESSON_AGENT, 0.0), 4)

    return {
        "since": since.isoformat(),
        "until": until.isoformat(),
        "lessons": {
            "written": len(written),
            "read": len(read),
            "written_and_read": sum(1 for r in written if _at(r.get("read_at"))),
            "written_by_kind": by_kind,
        },
        "taps": {**tap_counts, "recorded": taps is not None},
        "jobs": {"moved": len(moved), "updates": len(job_events), "now": now_status},
        "content": {
            "ideas": ideas if ideas is not None else NOT_RECORDED,
            "drafted": drafted,
            "posted": NOT_RECORDED,
        },
        "spend": {
            "total_usd": total,
            "by_agent": {a: round(c, 4) for a, c in sorted(by_agent.items(), key=lambda x: -x[1])},
            "lesson_agent_usd": lesson_spend,
        },
        "cost_per_lesson_usd": round(lesson_spend / len(written), 4) if written else None,
    }


async def _rows(sql: str, params: tuple[Any, ...]) -> list[dict[str, Any]] | None:
    """Rows, or None when the source cannot be read (a table not migrated yet)."""
    try:
        return await db.fetch(sql, params)
    except Exception:
        log.warning("value report: could not read %s", sql[:60], exc_info=True)
        return None


def _read_ideas() -> str | None:
    try:
        return memory.read(IDEAS_PATH)
    except (OSError, ValueError, PermissionError):
        return None


async def week_report(now: datetime | None = None) -> dict[str, Any]:
    """The past seven days, gathered and summarized. Never raises."""
    until = now or datetime.now(UTC)
    if until.tzinfo is None:
        until = until.replace(tzinfo=UTC)
    since = until - timedelta(days=DAYS)
    lessons = await _rows(
        "SELECT kind, created_at, read_at FROM hq.lessons"
        " WHERE created_at >= %s OR read_at >= %s", (since, since)) or []
    taps = await _rows(
        "SELECT verdict, count(*) AS n FROM hq.concept_signals WHERE at >= %s AND at <= %s"
        " GROUP BY verdict", (since, until))
    events = await _rows(
        "SELECT payload FROM hq.events WHERE kind = 'job.updated' AND ts >= %s AND ts <= %s",
        (since, until)) or []
    ids = sorted({str(e["payload"].get("job_id") or "") for e in events
                  if isinstance(e.get("payload"), dict)} - {""})
    status_rows = await _rows(
        "SELECT id::text AS id, status FROM hq.jobs WHERE id::text = ANY(%s)", (ids,)
    ) if ids else []
    spend = await _rows(
        "SELECT agent, coalesce(sum(cost_usd), 0) AS cost FROM hq.model_calls"
        " WHERE started_at >= %s AND started_at <= %s GROUP BY agent", (since, until)) or []
    drafted_rows = await _rows(
        "SELECT count(*) AS n FROM hq.events WHERE kind = 'post.drafted'"
        " AND ts >= %s AND ts <= %s", (since, until)) or []
    ideas_md = await asyncio.to_thread(_read_ideas)
    return summarize(
        since=since, until=until, lessons=lessons, taps=taps, job_events=events,
        job_status={str(r["id"]): str(r["status"]) for r in status_rows or []},
        spend=spend, ideas=count_ideas(ideas_md, since.date(), until.date()),
        drafted=int(drafted_rows[0]["n"]) if drafted_rows else 0,
    )


def format_report(r: dict[str, Any]) -> str:
    """Five plain lines, for the digest and the terminal."""
    lessons, taps, jobs, content, spend = (r["lessons"], r["taps"], r["jobs"],
                                           r["content"], r["spend"])
    since, until = _at(r["since"]), _at(r["until"])
    span = f"{since:%m-%d} to {until:%m-%d}" if since and until else "past 7 days"
    now = ", ".join(f"{s} {n}" for s, n in sorted(jobs["now"].items()))
    per = r["cost_per_lesson_usd"]
    tap_line = (f"{taps['got_it']} got it, {taps['lost_me']} lost me"
                if taps.get("recorded", True) else NOT_RECORDED)
    return "\n".join([
        f"Value, {span}:",
        (f"- Lessons: {lessons['written']} written, {lessons['read']} read"
         f" ({lessons['written_and_read']} of the new ones)"),
        f"- Concept taps: {tap_line}",
        f"- Jobs you moved: {jobs['moved']}" + (f" (now {now})" if now else ""),
        (f"- Content: {content['ideas']} ideas, {content['drafted']} drafted,"
         f" posted {content['posted']}"),
        f"- Model spend: ${spend['total_usd']:.2f}; {LESSON_AGENT} ${spend['lesson_agent_usd']:.2f}"
        + (f", ${per:.2f} per lesson written" if per is not None else ", no lessons written"),
    ])
