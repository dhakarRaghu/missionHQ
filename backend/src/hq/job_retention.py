"""The job ledger keeps one week of found and closed roles.

On 2026-10-02 he asked that the board show only roles from the last week and
that older ones be removed, not kept. A closed row was also how hunter knew
not to file the same role again, so removing it alone would bring the same
roles back night after night. So a role older than a week is:

* written to a monthly archive file (data/jobs/archive-YYYY-MM.jsonl), so
  nothing is lost by mistake;
* remembered by its dedupe key in data/jobs/removed.json for
  REMOVED_DAYS, so `record_job` refuses it while it is still being found;
* deleted from hq.jobs.

Roles he moved himself (shortlisted, applied, referral and later) stay.
State is in files, not a table: no migration for a list this small.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from hq import db
from hq.config import REPO_DIR

log = logging.getLogger(__name__)

KEEP_DAYS = 7              # found and closed roles stay this long after first seen
REMOVED_DAYS = 60          # a removed role is refused this long after removal
STATUSES = ("seen", "closed")


def _dir() -> Path:
    return REPO_DIR / "data" / "jobs"


def _removed_path() -> Path:
    return _dir() / "removed.json"


def _read_removed() -> dict[str, dict[str, str]]:
    try:
        raw = json.loads(_removed_path().read_text())
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in raw.items() if isinstance(v, dict)} if isinstance(raw, dict) else {}


def removed_recently(key: str, now: datetime | None = None) -> dict[str, str] | None:
    """The removal record for this dedupe key while it still holds, else None."""
    entry = _read_removed().get(key)
    if not entry:
        return None
    try:
        removed = datetime.fromisoformat(entry["removed"])
    except (KeyError, ValueError):
        return None
    now = now or datetime.now(UTC)
    return entry if now - removed < timedelta(days=REMOVED_DAYS) else None


def removed_matching(match: Callable[[str], bool],
                     now: datetime | None = None) -> dict[str, str] | None:
    """The removal record of any removed key `match` accepts, while it still
    holds. Keys of roles with no board id are matched by company, role and
    location (outreach.same_posting), so a role removed under the form used
    before 2026-10-04 stays out too."""
    now = now or datetime.now(UTC)
    for key in _read_removed():
        if match(key):
            entry = removed_recently(key, now)
            if entry:
                return entry
    return None


def _write(rows: list[dict[str, Any]], now: datetime) -> None:
    """Archive the rows, then remember their keys. Both before any delete."""
    folder = _dir()
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / f"archive-{now:%Y-%m}.jsonl").open("a") as archive:
        for row in rows:
            archive.write(json.dumps(row, default=str, ensure_ascii=False) + "\n")
    removed = _read_removed()
    cutoff = now - timedelta(days=REMOVED_DAYS)
    removed = {k: v for k, v in removed.items()
               if v.get("removed", "") >= cutoff.isoformat()}
    for row in rows:
        removed[str(row["dedupe_key"])] = {
            "company": str(row.get("company") or ""), "role": str(row.get("role") or ""),
            "status": str(row.get("status") or ""), "removed": now.isoformat()}
    tmp = _removed_path().with_suffix(".tmp")
    tmp.write_text(json.dumps(removed, indent=1, ensure_ascii=False))
    tmp.replace(_removed_path())


async def prune_old_jobs(now: datetime | None = None) -> int:
    """Move found and closed roles first seen more than KEEP_DAYS ago out of
    the ledger. Returns how many were moved."""
    now = now or datetime.now(UTC)
    rows = await db.fetch(
        "SELECT * FROM hq.jobs WHERE status = ANY(%s) AND first_seen < %s",
        (list(STATUSES), now - timedelta(days=KEEP_DAYS)))
    if not rows:
        return 0
    await asyncio.to_thread(_write, [dict(r) for r in rows], now)
    await db.execute("DELETE FROM hq.jobs WHERE id = ANY(%s)", ([r["id"] for r in rows],))
    log.info("job retention: %d role(s) older than %d days archived and removed",
             len(rows), KEEP_DAYS)
    return len(rows)
