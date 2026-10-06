"""Course videos for the console: the manifest, and the files behind it.

The videos are too large for git: 17 MP4s of 160 MB to 1 GB each, and GitHub
refuses any file over 100 MB. So the repo holds only a small manifest,
`learning/videos/index.json`, and the files live in `media_dir` (by default
`data/media`, which is gitignored). docs/videos.md says how to add one.

Two endpoints:

* `GET /api/media/videos` lists the manifest entries. Each entry carries
  short-lived signed URLs for its video and captions, never a file-system
  path. There are no thumbnails: the owner is the only viewer, and
  `preload="metadata"` shows the first frame.
* `GET /api/media/file/{id}/{part}` serves one of those two files.
* `PATCH /api/media/videos/{id}` sets or clears the entry's YouTube id. The
  videos stay local; when he uploads one as a private YouTube video, the
  console plays the YouTube embed instead of the local file. The video
  supports HTTP Range requests, so seeking works in a `<video>` tag. Starlette's
  `FileResponse` answers Range itself (206, `Accept-Ranges`, `Content-Range`).
  Captions are stored as SRT, which browsers do not read, and are converted to
  WebVTT on each request.

Why signed URLs. A `<video>` or `<track>` request cannot carry an
`Authorization` header. The bearer token in the query string would work
(`require_auth` accepts `?token=`), but that token can start agents, and a
media URL sits in the page's DOM, the browser history and every proxy log.
A signed URL names one file of one video and expires, so a leaked one exposes
one video for a day. The signing key is derived from the bearer token, so
changing the token revokes every URL. With no token set (local dev), there is
nothing to sign and the files are served openly, as every other route is.

Path safety. The caller names a manifest id, never a path. The id must exist
in the manifest, the manifest's path must be relative with no `..`, and the
resolved file must sit inside the media folder, so a symlink out of the
folder is refused too.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import time
from pathlib import Path, PurePosixPath
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from hq.api.deps import require_auth
from hq.config import settings
from hq.video import register

log = logging.getLogger(__name__)

router = APIRouter(prefix="/media")

MANIFEST_DIR = "videos"
MANIFEST_NAME = "index.json"
KINDS = frozenset({"course", "youtube", "article"})
_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,127}$")

Part = Literal["video", "captions"]
# The manifest field that names each part's file.
_FIELD: dict[str, str] = {"video": "file", "captions": "captions"}
_MEDIA_TYPES = {".mp4": "video/mp4", ".webm": "video/webm"}

# A URL is valid for at least URL_TTL_S and at most URL_TTL_S + URL_STEP_S.
# The expiry is rounded up to the hour so the URL stays the same for an hour:
# the browser can cache the file, and a list refetch does not change the
# player's source under it.
URL_STEP_S = 3600
URL_TTL_S = 24 * 3600


# --- the manifest -------------------------------------------------------------

def manifest_path() -> Path:
    return settings().learning_dir / MANIFEST_DIR / MANIFEST_NAME


_cache: dict[str, Any] = {"key": None, "videos": []}


def load_manifest() -> list[dict[str, Any]]:
    """Every valid entry of the manifest, in file order.

    Read again only when the file changes: a seek in the player is a new Range
    request, and each one looks its video up here. An entry with a bad id or
    kind is skipped with a warning rather than failing the whole list.
    """
    path = manifest_path()
    try:
        stat = path.stat()
    except FileNotFoundError:
        return []
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    if _cache["key"] == key:
        return _cache["videos"]
    data = json.loads(path.read_text(encoding="utf-8"))
    videos: list[dict[str, Any]] = []
    seen: set[str] = set()
    for entry in data.get("videos", []):
        vid = entry.get("id")
        if not isinstance(vid, str) or not _ID_RE.match(vid) or vid in seen:
            log.warning("video manifest: skipped an entry with a bad or repeated id: %r", vid)
            continue
        if entry.get("kind") not in KINDS:
            log.warning("video manifest: skipped %s, unknown kind %r", vid, entry.get("kind"))
            continue
        seen.add(vid)
        videos.append(entry)
    _cache.update(key=key, videos=videos)
    return videos


def find_video(video_id: str) -> dict[str, Any] | None:
    return next((v for v in load_manifest() if v["id"] == video_id), None)


def resolve_part(entry: dict[str, Any], part: str) -> Path | None:
    """The file behind one part of one entry, or None.

    None for a missing field, an absolute path, a `..`, a file that is not
    there, or a path that resolves outside the media folder (a symlink out of
    it).
    """
    rel = entry.get(_FIELD[part])
    if not isinstance(rel, str) or not rel.strip():
        return None
    pure = PurePosixPath(rel)
    if pure.is_absolute() or ".." in pure.parts:
        return None
    base = settings().media_dir.resolve()
    full = (base / pure).resolve()
    if base in full.parents and full.is_file():
        return full
    return None


# --- signed URLs --------------------------------------------------------------

def _signing_key() -> bytes | None:
    token = settings().api_bearer_token
    if not token:
        return None
    # Derived, not the token itself, so a signature reveals nothing about it.
    return hashlib.sha256(b"hq-media-url-v1:" + token.encode()).digest()


def _signature(key: bytes, video_id: str, part: str, exp: int) -> str:
    message = f"{video_id}\n{part}\n{exp}".encode()
    return hmac.new(key, message, hashlib.sha256).hexdigest()


def file_url(video_id: str, part: str, now: float | None = None) -> str:
    """The URL of one part, relative to the API base (`/api`)."""
    path = f"/media/file/{quote(video_id, safe='')}/{part}"
    key = _signing_key()
    if key is None:
        return path
    now = time.time() if now is None else now
    exp = (int(now) // URL_STEP_S + 1) * URL_STEP_S + URL_TTL_S
    return f"{path}?exp={exp}&sig={_signature(key, video_id, part, exp)}"


async def require_media_access(request: Request, video_id: str, part: str) -> None:
    """A valid signature for this exact file, or the usual bearer auth.

    The bearer form stays so the endpoint can be called with curl. A signature
    that is present but wrong or expired is refused outright (403), rather
    than falling through, so the player can tell an expired link from a
    signed-out console.
    """
    key = _signing_key()
    if key is None:
        return  # dev mode: no token configured, same as require_auth
    exp_raw = request.query_params.get("exp")
    sig = request.query_params.get("sig")
    if exp_raw is not None or sig is not None:
        try:
            exp = int(exp_raw or "")
        except ValueError:
            raise HTTPException(403, "invalid media link") from None
        expected = _signature(key, video_id, part, exp)
        if not sig or not hmac.compare_digest(sig, expected):
            raise HTTPException(403, "invalid media link")
        if exp < time.time():
            raise HTTPException(403, "media link expired; reload the list")
        return
    await require_auth(
        authorization=request.headers.get("authorization"),
        tailscale_user_login=request.headers.get("tailscale-user-login"),
        token_query=request.query_params.get("token"),
    )


# --- captions -----------------------------------------------------------------

_SRT_TIME_RE = re.compile(r"(\d{1,2}:\d{2}:\d{2}),(\d{3})")


def srt_to_vtt(text: str) -> str:
    """Convert SRT captions to WebVTT, which is what a `<track>` reads.

    Three differences matter: the `WEBVTT` header, a dot instead of a comma
    in timestamps, and cue text that WebVTT parses for tags. The text is
    escaped, so a caption such as "p95 < 2 s" shows as written.
    """
    text = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    out = ["WEBVTT", ""]
    for block in re.split(r"\n\s*\n", text.strip()):
        lines = [line for line in block.split("\n") if line.strip()]
        if lines and "-->" not in lines[0]:
            lines = lines[1:]  # the SRT cue number
        if not lines or "-->" not in lines[0]:
            continue
        out.append(_SRT_TIME_RE.sub(r"\1.\2", lines[0].strip()))
        for line in lines[1:]:
            out.append(
                line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
                .replace("-->", "→")
            )
        out.append("")
    return "\n".join(out)


# --- endpoints ----------------------------------------------------------------

def _public(entry: dict[str, Any]) -> dict[str, Any]:
    """An entry as the console sees it: no file names, signed URLs instead.

    `available` is false when the manifest names a video this machine does
    not have, such as a fresh clone without the media folder.
    """
    out = {k: v for k, v in entry.items() if k not in _FIELD.values()}
    out.setdefault("phase_slugs", [entry["phase_slug"]] if entry.get("phase_slug") else [])
    out["available"] = resolve_part(entry, "video") is not None
    out["urls"] = {
        part: file_url(entry["id"], part) if resolve_part(entry, part) else None
        for part in _FIELD
    }
    return out


@router.get("/videos", operation_id="listVideos", dependencies=[Depends(require_auth)])
async def list_videos(course: str = "", phase: str = "", kind: str = "") -> list[dict[str, Any]]:
    """The manifest, filtered.

    `phase` matches any of an entry's `phase_slugs`: the Phase 2 video covers
    2A and 2B, so it is listed on both. `kind` takes several, comma-separated.
    Entries come in manifest order, which lists the course videos in phase
    order and then the YouTube episodes by number.
    """
    kinds = {k.strip() for k in kind.split(",") if k.strip()}
    rows = []
    for entry in load_manifest():
        if course and entry.get("course") != course:
            continue
        if kinds and entry.get("kind") not in kinds:
            continue
        slugs = entry.get("phase_slugs") or [entry.get("phase_slug")]
        if phase and phase not in slugs:
            continue
        rows.append(_public(entry))
    return rows


@router.get("/file/{video_id}/{part}", operation_id="getVideoFile")
async def get_video_file(
    video_id: str,
    part: Part,
    _: None = Depends(require_media_access),
) -> Response:
    entry = find_video(video_id)
    if entry is None:
        raise HTTPException(404, f"no video {video_id!r}")
    full = resolve_part(entry, part)
    if full is None:
        raise HTTPException(404, f"video {video_id!r} has no {part} file here")
    # private: the console is signed in; no shared cache should keep a copy.
    cache = {"Cache-Control": "private, max-age=3600"}
    if part == "captions":
        vtt = srt_to_vtt(full.read_text(encoding="utf-8", errors="replace"))
        return Response(vtt, media_type="text/vtt; charset=utf-8", headers=cache)
    media_type = _MEDIA_TYPES.get(full.suffix.lower(), "application/octet-stream")
    return FileResponse(full, media_type=media_type, headers=cache)


# --- the YouTube id -----------------------------------------------------------

_YT_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
_YT_URL_RE = re.compile(
    r"^(?:https?://)?(?:www\.|m\.)?"
    r"(?:youtube\.com/(?:watch\?(?:.*&)?v=|embed/|shorts/|live/)"
    r"|youtube-nocookie\.com/embed/|youtu\.be/)"
    r"([A-Za-z0-9_-]{11})(?:[?&#/].*)?$"
)


def parse_youtube_id(text: str) -> str | None:
    """The 11-character video id from an id or any usual YouTube URL, or None."""
    text = text.strip()
    if _YT_ID_RE.match(text):
        return text
    m = _YT_URL_RE.match(text)
    return m.group(1) if m else None


class YoutubeBody(BaseModel):
    """A full YouTube URL or a bare id; null or "" clears it."""

    youtube_id: str | None


def set_youtube_id(video_id: str, youtube_id: str | None) -> dict[str, Any] | None:
    """Write one entry's YouTube id into the manifest, in place.

    Under the video pipeline's own lock (`hq.video.register`), which writes
    the same file when a video is finished, so neither write loses the other.
    The file is replaced atomically, so a reader never sees half of it.
    """
    path = manifest_path()
    with register._LOCK:  # the pipeline's lock: one lock for the one file
        data = json.loads(path.read_text(encoding="utf-8"))
        entry = next((v for v in data.get("videos", []) if v.get("id") == video_id), None)
        if entry is None:
            return None
        entry["youtube_id"] = youtube_id
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        tmp.replace(path)
    return entry


@router.patch("/videos/{video_id}", operation_id="setVideoYoutubeId",
              dependencies=[Depends(require_auth)])
async def update_video(video_id: str, body: YoutubeBody) -> dict[str, Any]:
    """Set or clear the YouTube id of one video. Accepts a URL or an id."""
    raw = (body.youtube_id or "").strip()
    youtube_id = parse_youtube_id(raw) if raw else None
    if raw and youtube_id is None:
        raise HTTPException(422, "not a YouTube video URL or id")
    if find_video(video_id) is None:
        raise HTTPException(404, f"no video {video_id!r}")
    entry = set_youtube_id(video_id, youtube_id)
    if entry is None:
        raise HTTPException(404, f"no video {video_id!r}")
    return _public(entry)
