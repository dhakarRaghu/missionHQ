"""What the phone reader sends back: "mark read" and a tap per concept.

The reader is a static bundle on Vercel (`hq.reader_export`), and it holds no
credential for this backend, by design. It reaches these two endpoints only
from a phone on his tailnet: the reader page posts to the backend's tailnet
origin (`NEXT_PUBLIC_READER_SYNC_URL`, public and not a secret) with no token
and no cookie, Tailscale Serve adds the `Tailscale-User-Login` header, and
`require_auth` accepts it when it names the owner. Off the tailnet the request
never arrives, and the page keeps the event to send later.

The browser needs the Vercel origin in `CORS_ORIGINS` to read the reply;
that is configuration (docs/deploy.md §12), never a domain in code.

A lesson is named here by its page file, as in the bundle's `index.json`,
because that is the only name the phone has. Everything in the body is
checked as data: the file name has one shape and must match a lesson's
`html_path`; the concept and verdict go through `signals.validate`.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from hq import db, signals
from hq.api import learning as learning_api
from hq.api.deps import require_auth

router = APIRouter(prefix="/reader", dependencies=[Depends(require_auth)])

# A page file as the export names it: `2026-09-22-some-slug.html`. No slash,
# no dot but the extension's, so it can only ever be a name, never a path.
FILE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,199}\.html")


class ReadBody(BaseModel):
    """He finished this page on the phone."""

    file: str = Field(max_length=220)


class PhoneSignalBody(BaseModel):
    """One "Got it" / "Lost me" tap, made on the phone."""

    file: str = Field(max_length=220)
    concept: str = Field(max_length=8)
    verdict: str = Field(max_length=16)


def check_file(file: str) -> str:
    if not FILE_RE.fullmatch(file):
        raise HTTPException(400, "file must be a lesson page name like 2026-09-22-slug.html")
    return file


async def lesson_for_file(file: str) -> str:
    """The lesson id whose page is `file`, or 404."""
    check_file(file)
    row = await db.fetchone(
        "SELECT id::text FROM hq.lessons"
        " WHERE html_path = %s OR right(html_path, %s) = %s"
        " ORDER BY lesson_date DESC LIMIT 1",
        (file, len(file) + 1, f"/{file}"),
    )
    if row is None:
        raise HTTPException(404, "no lesson has that page")
    return str(row["id"])


@router.post("/read", operation_id="readerMarkRead")
async def reader_mark_read(body: ReadBody) -> dict[str, Any]:
    """Mark a lesson read from the phone: the console's mark-read, unchanged."""
    lesson_id = await lesson_for_file(body.file)
    row = await learning_api.mark_read(lesson_id)
    if row is None:
        raise HTTPException(404, "no lesson has that page")
    return {"ok": True, "title": row["title"]}


@router.post("/signal", operation_id="readerSignal", status_code=201)
async def reader_signal(body: PhoneSignalBody) -> dict[str, Any]:
    """Record a concept tap made on the phone, stored as the console's are."""
    check_file(body.file)
    try:
        signals.validate(body.concept, body.verdict)
    except signals.SignalRefused as exc:
        raise HTTPException(400, str(exc)) from exc
    lesson_id = await lesson_for_file(body.file)
    row = await signals.record(lesson_id, body.concept, body.verdict, via="phone")
    if row is None:
        raise HTTPException(404, "no lesson has that page")
    return row
