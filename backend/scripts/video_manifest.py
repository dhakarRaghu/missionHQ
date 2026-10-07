"""Fill in and check learning/videos/index.json from the files in the media folder.

You write the facts a person decides: id, kind, course, phase slugs, episode
number, file names and source lessons. This script fills in the facts the
files already hold, so they are never typed by hand:

* `duration_s`, from ffprobe on the video;
* `chapters`, from the "Chapters" block of `<video stem>.description.txt`;
* `title`, from the first line of that file, when the entry has none.

There are no thumbnails: the owner is the only viewer, and the player's
`preload="metadata"` shows the first frame.

Run from backend/:

    MEDIA_DIR=/path/to/missionHq/data/media uv run python scripts/video_manifest.py
    uv run python scripts/video_manifest.py --check   # report only; exit 1 on a problem

docs/videos.md has the whole procedure.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

from hq.api.media import manifest_path
from hq.config import settings

_CHAPTER_RE = re.compile(r"^((?:\d+:)?\d{1,2}:\d{2})\s+(.+?)\s*$")


def parse_chapters(description: str) -> list[dict]:
    """`0:00 Title` lines after a line reading `Chapters`, up to a blank line."""
    lines = description.splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.strip().lower() == "chapters")
    except StopIteration:
        return []
    chapters = []
    for line in lines[start + 1:]:
        if not line.strip():
            break
        m = _CHAPTER_RE.match(line.strip())
        if not m:
            continue
        seconds = 0
        for unit in m.group(1).split(":"):
            seconds = seconds * 60 + int(unit)
        chapters.append({"t": seconds, "title": m.group(2)})
    return chapters


def title_from(description: str) -> str:
    """The YouTube title without its series suffix ("… | Inference Internals #11")."""
    first = description.strip().splitlines()[0] if description.strip() else ""
    return first.split(" | ")[0].strip()


def probe_duration(video: Path) -> float | None:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(video)],
        capture_output=True, text=True, check=False,
    )
    try:
        return round(float(out.stdout.strip()), 1)
    except ValueError:
        return None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="report only; change nothing")
    args = parser.parse_args()

    media = settings().media_dir
    manifest_file = manifest_path()
    data = json.loads(manifest_file.read_text(encoding="utf-8"))
    problems: list[str] = []

    for entry in data["videos"]:
        vid = entry["id"]
        rel = entry.get("file") or ""
        if PurePosixPath(rel).is_absolute() or ".." in PurePosixPath(rel).parts:
            problems.append(f"{vid}: file must be relative to the media folder: {rel}")
            continue
        video = media / rel
        if not video.is_file():
            problems.append(f"{vid}: no video at {video}")
            continue
        stem = video.with_suffix("")
        if entry.get("captions") and not (media / entry["captions"]).is_file():
            problems.append(f"{vid}: no captions at {media / entry['captions']}")

        description = stem.with_name(stem.name + ".description.txt")
        if description.is_file():
            text = description.read_text(encoding="utf-8")
            chapters = parse_chapters(text)
            if not chapters:
                problems.append(f"{vid}: {description.name} has no Chapters block")
            if not args.check:
                entry["chapters"] = chapters
                entry["title"] = entry.get("title") or title_from(text)
        elif not entry.get("chapters"):
            problems.append(f"{vid}: no {description.name} and no chapters in the manifest")

        if not args.check:
            duration = probe_duration(video)
            if duration is None:
                problems.append(f"{vid}: ffprobe could not read the duration")
            else:
                entry["duration_s"] = duration

    if not args.check:
        manifest_file.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"wrote {manifest_file} ({len(data['videos'])} videos)")
    for line in problems:
        print(f"problem: {line}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
