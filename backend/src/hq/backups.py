"""The nightly database dump, made by the backend.

`ops/backup.sh run` was meant to do this from a launchd job, but a launchd
job running /bin/bash may not read ~/Desktop, where this repo lives: macOS
answered "Operation not permitted" on 2026-10-03, and the newest dump on
disk was from 2026-09-02. The backend already reads the repo, so it makes the
dump itself, after the nightly reindex, in the same shape the script made:
data/snapshots/missionhq-<date>.sql.gz, kept KEEP_DAYS days.
`ops/backup.sh restore-drill` still restores the newest one.
"""

from __future__ import annotations

import gzip
import logging
import shutil
import subprocess
import tempfile
import threading
import time
from datetime import date, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from hq.config import REPO_DIR, settings

log = logging.getLogger(__name__)

KEEP_DAYS = 14
DUMP_TIMEOUT_S = 600
# Where pg_dump lives when the backend's PATH does not name it: Postgres.app,
# Homebrew on Apple silicon and on Intel. The same list as ops/backup.sh.
PG_DUMP_PLACES = ("/Applications/Postgres.app/Contents/Versions/latest/bin/pg_dump",
                  "/opt/homebrew/opt/postgresql@16/bin/pg_dump",
                  "/opt/homebrew/bin/pg_dump", "/usr/local/bin/pg_dump")


def snapshot_dir() -> Path:
    return REPO_DIR / "data" / "snapshots"


def pg_dump_path() -> str:
    found = shutil.which("pg_dump") or next(
        (p for p in PG_DUMP_PLACES if Path(p).is_file()), None)
    if not found:
        raise FileNotFoundError("pg_dump is not on PATH or in " + ", ".join(PG_DUMP_PLACES))
    return found


def prune(folder: Path, keep_days: int = KEEP_DAYS, now: float | None = None) -> int:
    """Delete dumps older than `keep_days`. Returns how many."""
    cutoff = (now or time.time()) - keep_days * 86400
    old = [p for p in folder.glob("missionhq-*.sql.gz") if p.stat().st_mtime < cutoff]
    for p in old:
        p.unlink()
    return len(old)


def dump_sync(day: date | None = None) -> dict[str, Any]:
    """Blocking. pg_dump | gzip into the day's file, through a .part file so
    a failed dump never replaces a good one; then prune. Raises on failure.
    A timer stops a pg_dump that runs over DUMP_TIMEOUT_S; its errors go to
    a temporary file, so a full error pipe cannot stall it."""
    folder = snapshot_dir()
    folder.mkdir(parents=True, exist_ok=True)
    day = day or datetime.now(ZoneInfo(settings().cron_tz)).date()
    out = folder / f"missionhq-{day.isoformat()}.sql.gz"
    part = out.with_name(out.name + ".part")
    cmd = [pg_dump_path(), "--no-owner", "--no-privileges", settings().database_url]
    try:
        with tempfile.TemporaryFile() as errors, \
                subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errors) as proc, \
                gzip.open(part, "wb", compresslevel=9) as gz:
            timer = threading.Timer(DUMP_TIMEOUT_S, proc.kill)
            timer.start()
            try:
                assert proc.stdout is not None
                shutil.copyfileobj(proc.stdout, gz)
                code = proc.wait()
            finally:
                timer.cancel()
            errors.seek(0)
            err = errors.read().decode(errors="replace").strip()
        if code != 0:
            raise RuntimeError(f"pg_dump exited {code}: {err[:300]}"
                               if code > 0 else f"pg_dump stopped after {DUMP_TIMEOUT_S}s")
        part.replace(out)
    finally:
        part.unlink(missing_ok=True)
    return {"path": str(out.relative_to(REPO_DIR)), "bytes": out.stat().st_size,
            "pruned": prune(folder)}
