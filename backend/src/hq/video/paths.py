"""Where a video's files live.

Code and small metadata live in git: the Remotion project (`video/`), the
prompts (`agents/tutor/video/`) and the manifest (`learning/videos/`). The
work files and the finished videos are large and live under `data/`, which
git ignores: GitHub refuses any file over 100 MB, and one finished episode is
160 to 450 MB.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from hq.config import REPO_DIR


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name, "").strip()
    return Path(value).expanduser() if value else default


def project_dir() -> Path:
    """The Remotion project: templates, narrate, render and verify scripts."""
    return _env_path("VIDEO_PROJECT_DIR", REPO_DIR / "video")


def work_root() -> Path:
    """One folder per video while it is written and built."""
    return _env_path("VIDEO_WORK_DIR", REPO_DIR / "data" / "video-work")


def media_root() -> Path:
    """Finished videos, served by the media API. Same default as settings.media_dir."""
    return _env_path("MEDIA_DIR", REPO_DIR / "data" / "media")


def manifest_path() -> Path:
    return REPO_DIR / "learning" / "videos" / "index.json"


def prompts_dir() -> Path:
    return REPO_DIR / "agents" / "tutor" / "video"


def node_bin() -> Path:
    """Folder holding the `node` that runs the Remotion scripts.

    Remotion needs an arm64 Node on Apple Silicon; an x86 Node fails at
    bundling. VIDEO_NODE_BIN names the folder; without it, the `node` on PATH
    is used, so nvm and Homebrew installs both work.
    """
    configured = os.environ.get("VIDEO_NODE_BIN", "").strip()
    if configured:
        return Path(configured).expanduser()
    found = shutil.which("node")
    if found:
        return Path(found).parent
    raise FileNotFoundError(
        "node is not on PATH. Install Node 20+ or set VIDEO_NODE_BIN to the folder holding it.")


_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,80}$")


def valid_id(video_id: str) -> bool:
    return bool(_ID_RE.match(video_id))


def work_dir(video_id: str) -> Path:
    if not valid_id(video_id):
        raise ValueError(f"bad video id {video_id!r}")
    return work_root() / video_id
