"""The phone reader: every lesson as files the frontend can ship.

He reads on his laptop through the console, which talks to the backend, which
talks to Postgres on that same machine. None of that exists on his phone, and
he asked for the plain answer: "like a normal web app, when we create content
and then we push and then we have the content online."

So this writes the whole library into `frontend/public/reader`. The lesson
pages are already complete HTML documents with their stylesheet and their
scripts inline, so nothing has to be rendered again: they are copied as they
are, and one `index.json` says what exists. He commits the folder, pushes, and
Vercel serves it. The reader route fetches those files and nothing else, so
the phone needs no database, no token and no backend awake.

What it deliberately does NOT carry: anything the reader cannot use without
the backend. No study notes, no review notes, no task or run history. The
bundle is what he reads, and it goes on a Vercel deployment, so the less that
leaves this machine the better.

The read flags are true as of the export. Marking something read is a write,
and this bundle is read-only, so the phone shows them and the console remains
the place that changes them.
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any

from hq import db
from hq.config import REPO_DIR, settings

READER_DIR = REPO_DIR / "frontend" / "public" / "reader"


def _page_file(html_path: str) -> Path | None:
    """The lesson page on disk, or None when the row points at nothing."""
    if not html_path.strip():
        return None
    page = settings().learning_dir.parent / html_path.strip()
    return page if page.is_file() else None


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


async def _courses() -> list[dict[str, Any]]:
    """Every course that has at least one written phase, in reading order.

    The join starts at the phases, not at `hq.courses`. That table is his own
    roster, and a course imported from the study platform has no row in it:
    Kubernetes is taught, he reads it in the console, and an inner join left
    it out of the bundle entirely. A course with no roster row sorts last and
    is named after its slug.
    """
    rows = await db.fetch(
        "SELECT p.course, c.title, c.course_order,"
        "       p.slug, p.title AS phase_title, p.phase_order, p.minutes,"
        "       p.summary, l.title AS lesson_title, l.html_path, l.lesson_date,"
        "       l.read_at, l.one_liner"
        " FROM hq.course_phases p"
        " JOIN hq.lessons l ON l.id = p.lesson_id"
        " LEFT JOIN hq.courses c ON c.course = p.course"
        " ORDER BY c.course_order NULLS LAST, p.course, p.phase_order, p.slug",
        (),
    )
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        page = _page_file(str(row["html_path"] or ""))
        if page is None:
            continue
        slug = str(row["course"])
        course = out.setdefault(
            slug,
            {
                "slug": slug,
                "title": str(row["title"] or "") or slug.replace("-", " ").title(),
                "phases": [],
            },
        )
        course["phases"].append(
            {
                "slug": str(row["slug"]),
                "title": str(row["lesson_title"] or row["phase_title"] or ""),
                "one_liner": str(row["one_liner"] or row["summary"] or "")[:400],
                "minutes": int(row["minutes"] or 0) or None,
                "date": _iso(row["lesson_date"]),
                "read": row["read_at"] is not None,
                "file": page.name,
            }
        )
    return list(out.values())


async def _articles() -> list[dict[str, Any]]:
    """The Learn side: standalone articles, newest first."""
    rows = await db.fetch(
        "SELECT title, one_liner, topic, lesson_date, html_path, read_at,"
        "       article_kind, course_slug"
        " FROM hq.lessons WHERE kind <> 'course' ORDER BY lesson_date DESC",
        (),
    )
    out = []
    for row in rows:
        page = _page_file(str(row["html_path"] or ""))
        if page is None:
            continue
        out.append(
            {
                "title": str(row["title"] or ""),
                "one_liner": str(row["one_liner"] or "")[:400],
                "topic": str(row["topic"] or ""),
                "kind": str(row["article_kind"] or ""),
                "date": _iso(row["lesson_date"]),
                "read": row["read_at"] is not None,
                "file": page.name,
            }
        )
    return out


async def build(target: Path | None = None) -> dict[str, Any]:
    """Write the bundle. Returns what went into it, for the CLI to print."""
    out = target or READER_DIR
    pages = out / "lessons"
    # Rebuilt from scratch every time: a lesson he deleted, or one rebuilt
    # under a new date, must not linger in the folder he pushes.
    if pages.exists():
        shutil.rmtree(pages)
    pages.mkdir(parents=True, exist_ok=True)

    courses = await _courses()
    articles = await _articles()

    wanted = {p["file"] for c in courses for p in c["phases"]}
    wanted |= {a["file"] for a in articles}
    # Every page gets the same hardening the console's endpoint applies, and
    # for a stronger reason: on Vercel there is no endpoint in front of it.
    # Without it a lesson's source link navigates the frame itself to the live
    # site, which is the 2026-09-12 bug, and the in-document content policy
    # that blocks outside loads is gone too.
    from hq.api.learning import harden_page

    lessons_dir = settings().learning_dir / "lessons"
    copied = 0
    for name in sorted(wanted):
        source = lessons_dir / name
        if source.is_file():
            (pages / name).write_text(harden_page(source.read_text()))
            copied += 1

    index = {
        "built_at": datetime.now().astimezone().isoformat(),
        "courses": courses,
        "articles": articles,
    }
    (out / "index.json").write_text(json.dumps(index, indent=2) + "\n")
    return {
        "dir": str(out),
        "courses": len(courses),
        "phases": sum(len(c["phases"]) for c in courses),
        "articles": len(articles),
        "pages": copied,
        "bytes": sum(f.stat().st_size for f in pages.iterdir()),
    }
