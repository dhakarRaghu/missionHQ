"""The media router: manifest listing, Range streaming, captions, path safety
and signed URLs. A minimal app mounts only this router, so no database, DBOS
or scheduler starts."""

from __future__ import annotations

import json
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from hq.api import media
from hq.api.deps import require_auth
from hq.config import settings

VIDEO_BYTES = bytes(range(256)) * 40  # 10,240 bytes, each offset recognisable

SRT = """1
00:00:00,700 --> 00:00:03,533
You ship a support agent

2
00:00:03,533 --> 00:00:05,467
p95 < 2 s & falling
"""


@pytest.fixture
def client(tmp_path, monkeypatch):
    learning = tmp_path / "learning"
    media_dir = tmp_path / "media"
    (learning / "videos").mkdir(parents=True)
    (media_dir / "course").mkdir(parents=True)
    (media_dir / "course" / "yt-01.mp4").write_bytes(VIDEO_BYTES)
    (media_dir / "course" / "yt-01.srt").write_text(SRT)
    # A secret beside the media folder, for the escape attempts to aim at.
    (tmp_path / "secret.txt").write_text("not for the browser")
    # A symlink inside the folder that points out of it.
    os.symlink(tmp_path / "secret.txt", media_dir / "course" / "link.mp4")

    def entry(vid, **over):
        base = {
            "id": vid, "kind": "youtube", "course": "inference-internals",
            "phase_slug": "p-04a", "phase_slugs": ["p-04a"], "number": 11,
            "title": "Episode", "duration_s": 1.0, "chapters": [{"t": 0, "title": "Start"}],
            "file": "course/yt-01.mp4", "captions": "course/yt-01.srt",
            "youtube_id": None, "source_lesson": "learning/lessons/a.md",
        }
        return {**base, **over}

    manifest = {"videos": [
        entry("yt-01"),
        entry("course-02", kind="course", number=None, phase_slug="p-02a",
              phase_slugs=["p-02a", "p-02b"]),
        entry("escape-dots", file="../secret.txt"),
        entry("escape-abs", file=str(tmp_path / "secret.txt")),
        entry("escape-link", file="course/link.mp4"),
        entry("missing", file="course/nothing.mp4"),
        entry("Bad Id"),
    ]}
    (learning / "videos" / "index.json").write_text(json.dumps(manifest))

    monkeypatch.setattr(settings(), "learning_dir", learning)
    monkeypatch.setattr(settings(), "media_dir", media_dir)
    monkeypatch.setattr(settings(), "api_bearer_token", "")
    media._cache.update(key=None, videos=[])

    app = FastAPI()
    app.include_router(media.router, prefix="/api")

    async def no_auth() -> None:
        return None

    app.dependency_overrides[require_auth] = no_auth
    return TestClient(app)


def test_the_list_filters_and_carries_no_paths(client) -> None:
    rows = client.get("/api/media/videos").json()
    assert [r["id"] for r in rows] == [
        "yt-01", "course-02", "escape-dots", "escape-abs", "escape-link", "missing",
    ]  # "Bad Id" is skipped
    for row in rows:
        assert "file" not in row and "captions" not in row
        assert set(row["urls"]) == {"video", "captions"}
    first = rows[0]
    assert first["available"] is True
    assert first["urls"]["video"] == "/media/file/yt-01/video"
    # Escapes and missing files are listed as unavailable, with no URL.
    for row in rows[2:]:
        assert row["available"] is False and row["urls"]["video"] is None

    # Phase 2 covers 2A and 2B, so it is found from either.
    assert [r["id"] for r in client.get("/api/media/videos?phase=p-02b").json()] == ["course-02"]
    assert [r["id"] for r in client.get("/api/media/videos?kind=course").json()] == ["course-02"]
    assert client.get("/api/media/videos?course=other").json() == []


def test_a_range_request_returns_206_with_the_exact_bytes(client) -> None:
    full = client.get("/api/media/file/yt-01/video")
    assert full.status_code == 200
    assert full.headers["accept-ranges"] == "bytes"
    assert full.headers["content-type"] == "video/mp4"
    assert full.content == VIDEO_BYTES

    part = client.get("/api/media/file/yt-01/video", headers={"Range": "bytes=1000-1999"})
    assert part.status_code == 206
    assert part.headers["content-range"] == f"bytes 1000-1999/{len(VIDEO_BYTES)}"
    assert part.headers["content-length"] == "1000"
    assert part.content == VIDEO_BYTES[1000:2000]

    # The open-ended form a <video> sends when it seeks.
    tail = client.get("/api/media/file/yt-01/video", headers={"Range": "bytes=10000-"})
    assert tail.status_code == 206
    assert tail.content == VIDEO_BYTES[10000:]

    beyond = client.get("/api/media/file/yt-01/video", headers={"Range": "bytes=99999-"})
    assert beyond.status_code == 416


def test_captions_are_served_as_webvtt(client) -> None:
    res = client.get("/api/media/file/yt-01/captions")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/vtt")
    assert res.text.startswith("WEBVTT\n\n00:00:00.700 --> 00:00:03.533\n")
    assert "p95 &lt; 2 s &amp; falling" in res.text
    assert "\n1\n" not in res.text  # SRT cue numbers are dropped


@pytest.mark.parametrize("vid", ["escape-dots", "escape-abs", "escape-link", "missing", "no-such-id"])
def test_no_path_leaves_the_media_folder(client, vid) -> None:
    res = client.get(f"/api/media/file/{vid}/video")
    assert res.status_code == 404
    assert "not for the browser" not in res.text


@pytest.mark.parametrize("path", [
    "/api/media/file/..%2F..%2Fsecret.txt/video",
    "/api/media/file/yt-01/..%2F..%2Fsecret.txt",
    "/api/media/file/yt-01/file",
    "/api/media/file/yt-01/thumbnail",  # no thumbnails: the owner is the only viewer
])
def test_a_path_in_the_url_is_refused(client, path) -> None:
    res = client.get(path)
    assert res.status_code in (404, 422)
    assert "not for the browser" not in res.text


def test_with_a_token_only_a_signed_url_or_the_bearer_opens_a_file(client, monkeypatch) -> None:
    monkeypatch.setattr(settings(), "api_bearer_token", "t0ken")
    rows = client.get("/api/media/videos").json()
    signed = "/api" + rows[0]["urls"]["video"]
    assert "sig=" in signed and "exp=" in signed

    assert client.get(signed, headers={"Range": "bytes=0-9"}).status_code == 206
    # No signature and no token: the bearer check refuses it.
    assert client.get("/api/media/file/yt-01/video").status_code == 401
    assert client.get(
        "/api/media/file/yt-01/video", headers={"Authorization": "Bearer t0ken"}
    ).status_code == 200
    # A signature for the video does not open the captions.
    other = signed.replace("/video?", "/captions?")
    assert client.get(other).status_code == 403
    # A tampered expiry breaks the signature.
    exp = signed.split("exp=")[1].split("&")[0]
    assert client.get(signed.replace(f"exp={exp}", f"exp={int(exp) + 1}")).status_code == 403


def test_an_expired_signed_url_is_refused(client, monkeypatch) -> None:
    monkeypatch.setattr(settings(), "api_bearer_token", "t0ken")
    old = media.file_url("yt-01", "video", now=0)  # expired in 1970
    assert client.get("/api" + old).status_code == 403


@pytest.mark.parametrize("text", [
    "dQw4w9WgXcQ",
    "https://www.youtube.com/watch?v=dQw4w9WgXcQ&t=42s",
    "https://youtu.be/dQw4w9WgXcQ?si=abc",
    "youtube.com/shorts/dQw4w9WgXcQ",
    "https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ",
])
def test_a_youtube_url_or_id_is_reduced_to_the_id(text) -> None:
    assert media.parse_youtube_id(text) == "dQw4w9WgXcQ"


def test_setting_and_clearing_the_youtube_id_writes_the_manifest(client) -> None:
    res = client.patch("/api/media/videos/yt-01",
                       json={"youtube_id": "https://youtu.be/dQw4w9WgXcQ"})
    assert res.status_code == 200
    assert res.json()["youtube_id"] == "dQw4w9WgXcQ"
    data = json.loads(media.manifest_path().read_text())
    assert data["videos"][0]["youtube_id"] == "dQw4w9WgXcQ"
    assert [v["id"] for v in data["videos"]][:2] == ["yt-01", "course-02"]  # order kept
    assert client.get("/api/media/videos").json()[0]["youtube_id"] == "dQw4w9WgXcQ"

    assert client.patch("/api/media/videos/yt-01", json={"youtube_id": None}).json()["youtube_id"] is None
    assert client.patch("/api/media/videos/yt-01", json={"youtube_id": "https://evil.example/x"}).status_code == 422
    assert client.patch("/api/media/videos/nope", json={"youtube_id": "dQw4w9WgXcQ"}).status_code == 404
