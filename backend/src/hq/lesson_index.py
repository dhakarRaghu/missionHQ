"""The lesson rows, as a file in git, so a second laptop sees what the first wrote.

A lesson is two things: its files in learning/lessons/ (git) and its row in
hq.lessons with the course phase pointing at it (the local database). The
Courses page shows a phase as built only from the row. So on 2026-10-06 a
phase generated and committed on one laptop still read "not built yet" on the
other after `git pull`: the files came, the rows did not.

`export()` writes every row to learning/lessons/index.json after any change
to a lesson (recorded, reviewed, read). `sync()` reads that file and adds the
rows this database does not have, links each course lesson to its phase, and
copies over a read time recorded on the other laptop. It runs at start-up and
whenever the Courses or Learn pages ask, when the file has changed since.
It only adds: it never deletes a row or replaces one this laptop has.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime
from pathlib import Path
from typing import Any

from hq import db
from hq.config import settings

log = logging.getLogger(__name__)

# Every column but the id and created_at: the id is this database's own, and
# the other laptop's row is matched by its md_path, which both share.
FIELDS = ("lesson_date", "title", "one_liner", "topic", "md_path", "html_path", "score",
          "sources", "path_step", "kind", "course_slug", "read_at", "review_status",
          "review_score", "review_notes", "review_round", "reviewed_at", "phase_slug",
          "relationship", "article_kind")
_last_mtime: float = 0.0


def index_path() -> Path:
    return settings().learning_dir / "lessons" / "index.json"


def _plain(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return value


async def export() -> int:
    """Write every lesson row to index.json. Sorted and stable, so git shows
    only the rows that changed. Returns how many rows were written."""
    global _last_mtime
    rows = await db.fetch(
        f"SELECT {', '.join(FIELDS)} FROM hq.lessons WHERE md_path <> ''"
        " ORDER BY lesson_date, md_path", ())
    entries = [{k: _plain(r.get(k)) for k in FIELDS} for r in rows]
    path = index_path()
    text = json.dumps(entries, indent=1, ensure_ascii=False, sort_keys=True) + "\n"
    if not path.is_file() or path.read_text() != text:
        tmp = path.with_suffix(".tmp")
        tmp.write_text(text)
        tmp.replace(path)
    _last_mtime = path.stat().st_mtime
    return len(entries)


async def export_quietly() -> None:
    """export() for the write paths: a failed export must not fail the lesson."""
    try:
        await export()
    except Exception as exc:  # noqa: BLE001 — the row is written; the file catches up later
        log.warning("lesson index not written: %s", exc)


def _entries() -> list[dict[str, Any]]:
    path = index_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text())
    except ValueError as exc:
        log.warning("lesson index unreadable: %s", exc)
        return []
    return [e for e in data if isinstance(e, dict) and e.get("md_path") and e.get("title")]


async def sync(force: bool = False) -> dict[str, int]:
    """Add the rows index.json has and this database lacks, link course
    lessons to their phases, and carry over read times. Only for lessons whose
    file is on disk. Skipped when the file has not changed since the last run."""
    global _last_mtime
    path = index_path()
    if not path.is_file():
        return {"added": 0, "linked": 0, "read": 0}
    mtime = path.stat().st_mtime
    if not force and mtime == _last_mtime:
        return {"added": 0, "linked": 0, "read": 0}
    root = settings().learning_dir.parent
    added = linked = read = 0
    for e in _entries():
        if not (root / str(e["md_path"])).is_file():
            continue
        have = await db.fetchone(
            "SELECT id::text, read_at FROM hq.lessons WHERE md_path = %s", (e["md_path"],))
        if have is None:
            row = await db.fetchone(
                "INSERT INTO hq.lessons (lesson_date, title, one_liner, topic, md_path,"
                " html_path, score, sources, path_step, kind, course_slug, read_at,"
                " review_status, review_score, review_notes, review_round, reviewed_at,"
                " phase_slug, relationship, article_kind)"
                " VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s,"
                " %s, %s, %s, %s, %s, %s)"
                # Another lesson already holds this phase or day here: keep it.
                " ON CONFLICT DO NOTHING RETURNING id::text",
                (e["lesson_date"], e["title"], e.get("one_liner") or "", e.get("topic") or "",
                 e["md_path"], e.get("html_path") or "", int(e.get("score") or 0),
                 json.dumps(e.get("sources") or []), e.get("path_step") or "",
                 e.get("kind") or "topic", e.get("course_slug") or "", e.get("read_at"),
                 e.get("review_status") or "none", e.get("review_score"),
                 e.get("review_notes") or "", int(e.get("review_round") or 0),
                 e.get("reviewed_at"), e.get("phase_slug") or "", e.get("relationship") or "",
                 e.get("article_kind") or ""))
            if not row:
                continue
            added += 1
            lesson_id = row["id"]
        else:
            lesson_id = have["id"]
            if e.get("read_at") and have.get("read_at") is None:
                await db.execute("UPDATE hq.lessons SET read_at = %s WHERE id = %s::uuid",
                                 (e["read_at"], lesson_id))
                read += 1
        slug = str(e.get("course_slug") or "")
        if e.get("kind") == "course" and slug:
            done = await db.fetch(
                "UPDATE hq.course_phases SET status = 'taught', lesson_id = %s::uuid,"
                " read_at = coalesce(read_at, %s::timestamptz)"
                " WHERE slug = %s AND (lesson_id IS NULL OR lesson_id = %s::uuid)"
                "   AND (lesson_id IS NULL OR status <> 'taught'"
                "        OR (read_at IS NULL AND %s::timestamptz IS NOT NULL))"
                " RETURNING slug",
                (lesson_id, e.get("read_at"), slug, lesson_id, e.get("read_at")))
            linked += len(done)
    _last_mtime = mtime
    if added or linked or read:
        log.info("lesson index: %s added, %s phases linked, %s read times copied",
                 added, linked, read)
    return {"added": added, "linked": linked, "read": read}


async def sync_quietly() -> None:
    try:
        await sync()
    except Exception as exc:  # noqa: BLE001 — the page still shows what this database has
        log.warning("lesson index not read: %s", exc)
