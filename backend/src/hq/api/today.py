"""The Home page's one question: what needs him, and did the night run.

Home used to count approval tickets only, so it said "all caught up" on a
morning with six unread lessons, three open decisions, two memory proposals
and four posts waiting. Every item here is read from the same ledger the
nightly briefs use (hq.continuity), so the page and sage's note agree.
"""

from __future__ import annotations

import asyncio
import re
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from dbos._croniter import croniter  # type: ignore[attr-defined]
from fastapi import APIRouter

from hq import continuity, db, memory, value
from hq.config import settings

router = APIRouter()

PROPOSALS_DIR = "memory/proposals"
IDEAS_PATH = "projects/content/ideas.md"
WEEK = 7
# How long after its slot a scheduled run may still be starting before the
# page calls it missed.
DUE_GRACE = timedelta(minutes=20)
SYSTEM_LABELS = {
    "course_study": "Course study",
    "job_search": "LinkedIn job discovery",
    "learning_run": "Today's article",
    "source_hunt": "Source hunt",
}


def _local_now() -> datetime:
    return datetime.now(ZoneInfo(settings().cron_tz))


async def _rows(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
    try:
        return await db.fetch(sql, params)
    except Exception:  # noqa: BLE001 — one unreadable source must not blank the page
        return []


def _item(key: str, kind: str, title: str, detail: str, href: str, action: str,
          count: int = 1) -> dict[str, Any]:
    return {"key": key, "kind": kind, "title": title, "detail": detail, "href": href,
            "action": action, "count": count}


async def _reading() -> list[dict[str, Any]]:
    out = []
    # The newest unread course lesson is the one the evening starter checks,
    # so it is the one that holds the next phase back.
    course = await _rows(
        "SELECT l.title, l.course_slug AS slug, p.course FROM hq.lessons l"
        " LEFT JOIN hq.course_phases p ON p.slug = l.course_slug"
        " WHERE l.kind = 'course' AND l.read_at IS NULL"
        " ORDER BY l.lesson_date DESC, l.created_at DESC")
    if course:
        gate = course[0]
        more = (f" {len(course) - 1} older course lesson{'s' if len(course) > 2 else ''}"
                " unread too." if len(course) > 1 else "")
        href = (f"/courses?course={gate['course']}&phase={gate['slug']}"
                if gate.get("course") and gate.get("slug") else "/courses")
        out.append(_item(
            "course", "read", f"Read {gate['title']}",
            "The next phase starts once you mark this one read." + more,
            href, "Read", len(course)))
    other = await _rows(
        "SELECT title, kind FROM hq.lessons WHERE kind <> 'course' AND read_at IS NULL"
        " ORDER BY lesson_date DESC, created_at DESC")
    articles = [r for r in other if r["kind"] == "topic"]
    rest = len(other) - (1 if articles else 0)
    tail = f" {rest} more unread on Learn." if rest else ""
    if articles:
        # Learn opens on the newest article, which is also what the evening
        # starter checks before writing the next one.
        out.append(_item("articles", "read", f"Read {articles[0]['title']}",
                         "The next article waits until you read this one." + tail,
                         "/learn", "Read", len(other)))
    elif other:
        out.append(_item("articles", "read", f"{len(other)} weekend page"
                         f"{'s' if len(other) > 1 else ''} on Learn",
                         f"Newest: {other[0]['title']}.", "/learn", "Open", len(other)))
    return out


async def _decisions(today: date) -> list[dict[str, Any]]:
    text = await asyncio.to_thread(continuity._read_decisions)
    aged, _decided = await asyncio.to_thread(continuity.decisions_with_age, text, today)
    if not aged:
        return []
    aged.sort(key=lambda d: -(d[1] or 0))
    first, age = aged[0]
    shown = re.sub(r"^\s*[-*]\s*", "", first).strip()
    detail = (f"Open {age} day{'s' if age != 1 else ''}. " if age else "") + (
        f"{len(aged) - 1} more open." if len(aged) > 1 else "Sage asks every night until it closes.")
    return [_item("decisions", "decide", f"Decide: {shown[:110]}", detail,
                  "/vault?path=memory/decisions.md", "Decide", len(aged))]


def _proposal_files() -> list[str]:
    folder = settings().vault_dir / PROPOSALS_DIR
    if not folder.is_dir():
        return []
    files = sorted(folder.glob("*.md"), key=lambda p: p.name, reverse=True)
    return [f"{PROPOSALS_DIR}/{p.name}" for p in files]


async def _proposals() -> list[dict[str, Any]]:
    files = await asyncio.to_thread(_proposal_files)
    if not files:
        return []
    return [_item(
        "proposals", "review",
        "Review memory proposals" if len(files) > 1 else "Review a memory proposal",
        f"{len(files)} file{'s' if len(files) > 1 else ''} of edits to your memory blocks."
        " Only you change those blocks.",
        f"/vault?path={files[0]}", "Review", len(files))]


def _ideas_text() -> str | None:
    try:
        return memory.read(IDEAS_PATH)
    except (OSError, ValueError, PermissionError):
        return None


async def _posts(today: date) -> list[dict[str, Any]]:
    text = await asyncio.to_thread(_ideas_text)
    n = value.count_ideas(text, today - timedelta(days=1), today) or 0
    if not n:
        return []
    return [_item("posts", "post", f"{n} post{'s' if n > 1 else ''} ready to paste on X",
                  "Written in your voice from what happened this week. Copy one, post it.",
                  "/ideas", "Open", n)]


async def _jobs() -> list[dict[str, Any]]:
    rows = await _rows(
        "SELECT company, role, pay_lakh, (fit_parts->'pay'->>'estimated') AS estimated,"
        " last_seen FROM hq.jobs WHERE fit_score >= 8 AND status IN ('seen', 'referral')"
        " ORDER BY last_seen DESC")
    if not rows:
        return []
    stated = [r for r in rows if r["pay_lakh"] and str(r["estimated"]).lower() == "false"]
    newest = rows[0]
    detail = (f"{len(stated)} with stated pay. " if stated else "None states pay yet. ") + (
        f"Newest: {newest['company']}, {newest['role']}.")
    return [_item("jobs", "apply", f"{len(rows)} strong roles open", detail, "/jobs",
                  "Review", len(rows))]


async def _stopped() -> list[dict[str, Any]]:
    rows = await _rows(
        "SELECT count(*) AS n FROM hq.tasks WHERE status IN ('blocked', 'failed')"
        " AND updated_at > now() - interval '24 hours'")
    n = int(rows[0]["n"]) if rows else 0
    if not n:
        return []
    return [_item("stopped", "fix", f"{n} run{'s' if n > 1 else ''} stopped since yesterday",
                  "Retry or dismiss them on the board.", "/board", "Open", n)]


def _slot_rows(now: datetime) -> list[dict[str, Any]]:
    """Every schedule whose last slot fell in the past day: agent crons and
    the system starters, oldest first."""
    from hq import engine

    since = now - timedelta(hours=24)
    rows: list[dict[str, Any]] = []
    for name, schedule, _tool, _kwargs in engine.SYSTEM_DISPATCHES:
        slot = croniter(schedule, now).get_prev(datetime)
        if slot >= since:
            rows.append({"slot": slot, "agent": "system", "label": SYSTEM_LABELS.get(name, name),
                         "key": f"system:{name}:{slot:%Y-%m-%d-%H%M}", "system": True})
    for agent_name, (spec, _agent) in engine.AGENTS.items():
        for idx, entry in enumerate(spec.cron):
            slot = croniter(entry.schedule, now).get_prev(datetime)
            if slot >= since:
                rows.append({"slot": slot, "agent": agent_name,
                             "label": engine.cron_title(entry.prompt).rstrip("…").rstrip("."),
                             "key": f"cron:{agent_name}:{idx}:{slot:%Y-%m-%d-%H%M}",
                             "system": False})
    return sorted(rows, key=lambda r: r["slot"])


async def _night(now: datetime) -> dict[str, Any]:
    slots = []
    for row in _slot_rows(now):
        status, detail, task_id, cost = "due", "", None, None
        late = now - row["slot"] > DUE_GRACE
        if row["system"]:
            claim = await _rows("SELECT 1 FROM hq.control WHERE key = %s", (row["key"],))
            event = await _rows(
                "SELECT payload->>'result' AS result FROM hq.events WHERE payload->>'slot' = %s"
                " AND kind IN ('cron.dispatched', 'cron.caught_up') ORDER BY ts DESC LIMIT 1",
                (row["key"],))
            detail = str((event[0]["result"] if event else "") or "")
            if claim:
                status = "held" if detail.startswith("not starting") else "started"
            elif late:
                status = "missed"
        else:
            task = await _rows(
                "SELECT t.id::text AS id, t.status,"
                " (SELECT round(coalesce(sum(m.cost_usd), 0)::numeric, 3) FROM hq.model_calls m"
                "  WHERE m.task_id = t.id) AS cost"
                " FROM hq.tasks t WHERE t.dedup_key = %s", (row["key"],))
            if task:
                status, task_id, cost = str(task[0]["status"]), task[0]["id"], task[0]["cost"]
            elif late:
                status = "missed"
        slots.append({"at": row["slot"].isoformat(), "agent": row["agent"], "label": row["label"],
                      "status": status, "detail": detail[:160], "task_id": task_id,
                      "cost_usd": float(cost) if cost is not None else None})
    cut = await _rows(
        "SELECT count(DISTINCT task_id) AS n FROM hq.events WHERE kind = 'task.updated'"
        " AND payload->>'event' IN ('stopped_by_sleep', 'timed_out')"
        " AND ts > now() - interval '24 hours'")
    return {"slots": slots, "cut_runs": int(cut[0]["n"]) if cut else 0}


async def _week(now: datetime, today: date) -> dict[str, Any]:
    c = await continuity._counters(now.astimezone(UTC))
    text = await asyncio.to_thread(_ideas_text)
    spend = await _rows(
        "SELECT coalesce(sum(cost_usd), 0) AS usd FROM hq.model_calls"
        " WHERE started_at > now() - interval '7 days'")
    return {
        "lessons_written": c.written, "lessons_read": c.read,
        "unread": sum((c.unread_by_kind or {}).values()) if c.unread_by_kind else None,
        "jobs_found": c.jobs_found, "jobs_strong": c.jobs_strong, "jobs_applied": c.jobs_applied,
        "posts_filed": value.count_ideas(text, today - timedelta(days=WEEK - 1), today),
        "spend_usd": round(float(spend[0]["usd"]), 2) if spend else None,
    }


@router.get("/today", operation_id="getToday")
async def get_today() -> dict[str, Any]:
    now = _local_now()
    today = now.date()
    groups = await asyncio.gather(
        _reading(), _decisions(today), _proposals(), _posts(today), _jobs(), _stopped())
    needs = [item for group in groups for item in group]
    return {
        "date": today.isoformat(),
        "needs": needs,
        "night": await _night(now),
        "week": await _week(now, today),
    }
