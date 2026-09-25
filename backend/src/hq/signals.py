"""Per-concept signals: what landed and what lost him, one tap at a time.

Every lesson page opens with its concepts, and each carries "Got it" and
"Lost me". The page runs in a sandboxed frame with no network and no storage,
so the tap is a `postMessage` to the page around it. The console sends it
here; the phone reader sends it through `hq.api.reader` when the phone is on
his tailnet (no credential, only his Tailscale identity) and keeps it in an
outbox until then. `via` says which.

The rows are answers, not a score. Their one consumer today is the next
outline of the same course: a concept from an earlier phase that he marked
"lost me" is named in the material, so the new phase reconnects it where it
builds on it.

The message comes from model-written markup, so everything here is
validated as data: a concept id is `c` and one or two digits, a verdict is
one of two words, and a lesson id must name a real lesson.
"""

from __future__ import annotations

import html as html_lib
import logging
import re
import uuid
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any

from hq import db
from hq.config import settings

log = logging.getLogger(__name__)

CONCEPT_RE = re.compile(r"c\d{1,2}")
VERDICTS = ("got_it", "lost_me")
VIAS = ("console", "phone")
LOST_ME_MAX = 8             # the outline material stays small
CLAIM_CHARS = 200
LOST_HEADING = "He said these lost him; reconnect them where this phase uses them"


class SignalRefused(ValueError):
    """The tap is not one we store."""


def validate(concept: object, verdict: object) -> tuple[str, str]:
    """The (concept, verdict) pair, or SignalRefused saying why not."""
    if not isinstance(concept, str) or not CONCEPT_RE.fullmatch(concept):
        raise SignalRefused("concept must be c1..c99")
    if not isinstance(verdict, str) or verdict not in VERDICTS:
        raise SignalRefused(f"verdict must be one of {list(VERDICTS)}")
    return concept, verdict


def is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except (ValueError, TypeError):
        return False
    return True


async def record(lesson_id: str, concept: str, verdict: str, via: str = "console"
                 ) -> dict[str, Any] | None:
    """Store one tap. None when the lesson does not exist."""
    concept, verdict = validate(concept, verdict)
    if via not in VIAS:
        raise SignalRefused(f"via must be one of {list(VIAS)}")
    if not is_uuid(lesson_id):
        return None
    return await db.fetchone(
        "INSERT INTO hq.concept_signals (lesson_id, concept, verdict, via)"
        " SELECT id, %s, %s, %s FROM hq.lessons WHERE id = %s"
        " RETURNING lesson_id::text, concept, verdict, at, via",
        (concept, verdict, via, lesson_id),
    )


def latest(rows: Iterable[dict[str, Any]]) -> dict[str, str]:
    """His current answer per concept, from taps in the order they were made."""
    out: dict[str, str] = {}
    for row in rows:
        out[str(row["concept"])] = str(row["verdict"])
    return out


async def for_lesson(lesson_id: str) -> dict[str, Any]:
    """Every tap on one lesson, oldest first, and the current answer per concept."""
    rows = await db.fetch(
        "SELECT concept, verdict, at, via FROM hq.concept_signals"
        " WHERE lesson_id = %s ORDER BY at, id",
        (lesson_id,),
    ) if is_uuid(lesson_id) else []
    return {"lesson_id": lesson_id, "verdicts": latest(rows), "taps": rows}


# --- what the next outline reads -----------------------------------------------

_CONCEPT_ITEM_RE = re.compile(
    r"""<li\b[^>]*\bid\s*=\s*["'](c\d{1,2})["'][^>]*>\s*<b>(.*?)</b>""",
    re.IGNORECASE | re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


def concept_claims(page_html: str) -> dict[str, str]:
    """{c1: the claim} from a page's concept list, as plain text."""
    out: dict[str, str] = {}
    for cid, raw in _CONCEPT_ITEM_RE.findall(page_html):
        text = " ".join(html_lib.unescape(_TAG_RE.sub(" ", raw)).split())
        if text:
            out.setdefault(cid, text[:CLAIM_CHARS])
    return out


def _page_claims(html_path: str) -> dict[str, str]:
    if not html_path.strip():
        return {}
    page: Path = settings().learning_dir.parent / html_path.strip()
    try:
        return concept_claims(page.read_text())
    except OSError:
        return {}


def lost_section(rows: list[dict[str, Any]],
                 claims_for: Callable[[str], dict[str, str]] = _page_claims) -> str:
    """The outline's short list of earlier concepts he said lost him, or "".

    `rows` are his current "lost me" answers on earlier phases, in phase
    order: phase_title, concept, html_path.
    """
    lines: list[str] = []
    pages: dict[str, dict[str, str]] = {}
    for row in rows[:LOST_ME_MAX]:
        path = str(row.get("html_path") or "")
        if path not in pages:
            pages[path] = claims_for(path)
        concept = str(row["concept"])
        claim = pages[path].get(concept, "")
        title = str(row.get("phase_title") or "an earlier phase")
        lines.append(f"- {title}, {concept}" + (f": {claim}" if claim else ""))
    if not lines:
        return ""
    return f"## {LOST_HEADING}\n\n" + "\n".join(lines)


async def lost_before(course: str, slug: str) -> list[dict[str, Any]]:
    """His current "lost me" answers on phases of `course` before `slug`."""
    return await db.fetch(
        "SELECT phase_title, concept, html_path FROM ("
        "  SELECT DISTINCT ON (s.lesson_id, s.concept)"
        "         s.concept, s.verdict, l.html_path, p.title AS phase_title,"
        "         p.phase_order, p.slug"
        "  FROM hq.concept_signals s"
        "  JOIN hq.lessons l ON l.id = s.lesson_id AND l.kind = 'course'"
        "  JOIN hq.course_phases p ON (p.lesson_id = l.id OR p.slug = l.course_slug)"
        "  JOIN hq.course_phases cur ON cur.slug = %s"
        "  WHERE p.course = %s AND (p.phase_order, p.slug) < (cur.phase_order, cur.slug)"
        "  ORDER BY s.lesson_id, s.concept, s.at DESC, s.id DESC"
        ") t WHERE verdict = 'lost_me'"
        " ORDER BY phase_order, slug, length(concept), concept LIMIT %s",
        (slug, course, LOST_ME_MAX),
    )


async def lost_material(course: str, slug: str) -> str:
    """The section for the outline, or "" on none or on any failure: a missing
    signal must never stop a lesson being written."""
    if not course or not slug:
        return ""
    try:
        return lost_section(await lost_before(course, slug))
    except Exception:
        log.warning("concept signals unavailable for %s/%s", course, slug, exc_info=True)
        return ""
