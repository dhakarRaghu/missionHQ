"""The register a finished video is written to: `learning/videos/index.json`,
a small JSON file in git that the media API reads. The video files
themselves live under the media folder, outside git."""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any

from hq.video import paths

_LOCK = threading.Lock()


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower().replace("'", "")).strip("-")


def _read(path: Path, empty: Any) -> Any:
    try:
        return json.loads(path.read_text())
    except FileNotFoundError:
        return empty


def _write(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(path)


# --- the manifest -----------------------------------------------------------------

def manifest() -> dict[str, Any]:
    data = _read(paths.manifest_path(), {"videos": []})
    if isinstance(data, list):           # tolerate a bare list
        data = {"videos": data}
    data.setdefault("videos", [])
    return data


def upsert_video(entry: dict[str, Any]) -> None:
    """Add a finished video, or replace the entry with the same id."""
    with _LOCK:
        data = manifest()
        videos = [v for v in data["videos"] if v.get("id") != entry["id"]]
        videos.append(entry)
        data["videos"] = videos
        _write(paths.manifest_path(), data)
