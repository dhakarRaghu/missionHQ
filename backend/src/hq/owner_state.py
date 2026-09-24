"""The owner-state block: what he has done, from the ledger, as data.

A claim about him ("you read the caching lesson", "you applied to Rippling",
"you posted on Tuesday") is only true when a table says so. The daily note
said "Apply to Cloudflare" five nights running while the row was closed, and
an article's "why it matters to you" named work he had not done. So the
tables are rendered once, by code, under one heading, and the charter rule
says: a claim about him traces to a line here, or it is not made.

Sources, all his own actions:

- lessons he marked read (``hq.lessons.read_at``, set only from the reader);
- lessons written for him and still unread;
- jobs he moved himself on the board (``job.updated`` events carry a status
  change only when the console's ``update_job`` wrote it);
- posts he published: nothing records one, so the line says so;
- operator requests he answered himself (``decided_by = 'owner'``; sage
  routes and closes them, so this is usually none).

``render`` is pure; ``block`` gathers the rows and never raises.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from hq import db

log = logging.getLogger(__name__)

HEADING = "## What he has done (from the ledger)"
RULE = ("Every claim about what he has done, read, built, applied to or posted must"
        " trace to a line here. With no such line, say nothing about him.")
DAYS = 14
SHOW_LIMIT = 8           # items per list before the fit loop shortens them
ROW_LIMIT = SHOW_LIMIT + 1
NOT_RECORDED = "not recorded"
NOT_READABLE = "not readable"
LIMIT_CHARS = 1_400
# A move he made toward a role. A move to closed or rejected is his too, but
# it is not something a note should tell him to act on again.
FORWARD_STATUSES = ("shortlisted", "referral", "applied", "interviewing", "offer")
STATUS_FIELD = "status = %s"


def _day(value: object) -> str:
    if isinstance(value, datetime | date):
        return f"{value:%Y-%m-%d}"
    if isinstance(value, str) and value:
        return value[:10]
    return "?"


def _cut(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _lesson(row: dict[str, Any], when: str) -> str:
    return (f"“{_cut(str(row.get('title') or ''), 48)}”"
            f" ({row.get('kind') or 'lesson'}, {when})")


def _listed(label: str, items: list[str] | None, shown: int, empty: str = "none",
            tail: str = "") -> str:
    """One line: the label, then the first ``shown`` items and a count of the
    rest. ``None`` items means the source could not be read."""
    if items is None:
        return f"- {label}: {NOT_READABLE}"
    if not items:
        return f"- {label}: {empty}{tail}"
    more = f"; and {len(items) - shown} more" if len(items) > shown else ""
    return f"- {label}: {'; '.join(items[:shown])}{more}{tail}"


def _job(r: dict[str, Any], when: str) -> str:
    return (f"{_cut(str(r.get('company') or ''), 24)}, {_cut(str(r.get('role') or ''), 32)}"
            f" {when}")


def render(
    *,
    read: list[dict[str, Any]] | None,
    unread: list[dict[str, Any]] | None,
    moved: list[dict[str, Any]] | None,
    applied: list[dict[str, Any]] | None,
    answered: int | None,
    days: int = DAYS,
    limit: int = LIMIT_CHARS,
) -> str:
    """The block from its rows. ``None`` for a source means it could not be
    read, which is said as such; an empty list means none. Under ``limit``
    characters: the lists lose items from the end, each with a count of what
    was left out; no line is ever cut mid-way, so a name never becomes half a
    name."""
    forward = [r for r in moved or [] if str(r.get("status")) in FORWARD_STATUSES]
    closed = len(moved or []) - len(forward)
    lists: list[tuple[str, list[str] | None, str, str]] = [
        (f"Lessons he read (last {days} days)",
         None if read is None else [_lesson(r, f"read {_day(r.get('read_at'))}") for r in read],
         "none", ""),
        ("Lessons written for him, not yet read",
         None if unread is None else [_lesson(r, _day(r.get("lesson_date"))) for r in unread],
         "none", ""),
        (f"Jobs he moved himself on the board (last {days} days)",
         None if moved is None else [_job(r, f"-> {r.get('status')} ({_day(r.get('ts'))})")
                                     for r in forward],
         "none" if not moved else "none forward", f"; {closed} he closed" if closed else ""),
        ("Roles he has applied to (board status applied)",
         None if applied is None else [_job(r, f"({_day(r.get('updated_at'))})") for r in applied],
         "none", ""),
    ]
    shown = [SHOW_LIMIT] * len(lists)

    def assemble() -> str:
        lines = [HEADING, RULE]
        lines.extend(_listed(label, items, n, empty, tail)
                     for (label, items, empty, tail), n in zip(lists, shown, strict=True))
        lines.append(f"- Posts he published: {NOT_RECORDED} (nothing records a post going out)")
        if answered is None:
            lines.append(f"- Operator requests he answered himself: {NOT_READABLE}")
        else:
            lines.append("- Operator requests he answered himself: "
                         + (str(answered) if answered else "none recorded"))
        return "\n".join(lines)

    text = assemble()
    while len(text) > limit and any(n > 1 for n in shown):
        longest = max(range(len(lists)), key=lambda i: (shown[i], -i))
        shown[longest] -= 1
        text = assemble()
    return text


async def _rows(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]] | None:
    try:
        return await db.fetch(sql, params)
    except Exception:
        log.warning("owner state: could not read %s", sql[:60], exc_info=True)
        return None


async def block(now: datetime | None = None, days: int = DAYS) -> str:
    """The block, gathered. Never raises: a source that cannot be read says so."""
    until = now or datetime.now(UTC)
    since = until - timedelta(days=days)
    read = await _rows(
        "SELECT title, kind, read_at FROM hq.lessons WHERE read_at >= %s"
        " ORDER BY read_at DESC LIMIT %s", (since, ROW_LIMIT))
    unread = await _rows(
        "SELECT title, kind, lesson_date FROM hq.lessons WHERE read_at IS NULL"
        " ORDER BY lesson_date DESC LIMIT %s", (ROW_LIMIT,))
    moved = await _rows(
        "SELECT DISTINCT ON (j.id) e.ts, j.company, j.role, j.status"
        " FROM hq.events e JOIN hq.jobs j ON j.id::text = e.payload->>'job_id'"
        " WHERE e.kind = 'job.updated' AND e.payload->'fields' ? %s AND e.ts >= %s"
        " ORDER BY j.id, e.ts DESC", (STATUS_FIELD, since))
    if moved is not None:
        moved.sort(key=lambda r: _day(r.get("ts")), reverse=True)
    applied = await _rows(
        "SELECT company, role, updated_at FROM hq.jobs WHERE status = 'applied'"
        " ORDER BY updated_at DESC LIMIT %s", (ROW_LIMIT,))
    answered_rows = await _rows(
        "SELECT count(*) AS n FROM hq.operator_requests WHERE decided_by = 'owner'")
    answered = int(answered_rows[0]["n"]) if answered_rows else None
    return render(read=read, unread=unread, moved=moved, applied=applied, answered=answered,
                  days=days)
