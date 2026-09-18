#!/usr/bin/env python3
"""Copy the learning content itself into the off-machine mirror.

The database stores paths, not text: `hq.lessons` says
`learning/lessons/2026-09-17-….md`, and the lesson lives in the repo. Most of
those files are on GitHub, but not all of them — the imported course sources
that name a former employer are deliberately not in git — so a mirror that
carries only the database is not a backup of what he learned.

This writes every learning file into one table on the mirror:

    hq.learning_files(path, bytes, sha256, updated_at, content)

Restoring is a loop over that table, writing each `path` back under the repo.
Nothing here reads the mirror while Mission HQ runs, and nothing is deleted
locally. The vault stays out of it: that is the agents' memory, not his
learning.

Run through the backup script: `ops/backup.sh sync-remote`.
"""

from __future__ import annotations

import hashlib
import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parent.parent
# What counts as learning content. Everything under these folders, plus his
# own files at the top of learning/.
FOLDERS = ("learning/lessons", "learning/courses", "learning/study-material")
SUFFIXES = {".md", ".html", ".json"}
# A lesson page is large; a runaway file is not learning content.
MAX_BYTES = 4_000_000

DDL = """
CREATE TABLE IF NOT EXISTS hq.learning_files (
    path       text PRIMARY KEY,
    bytes      integer NOT NULL,
    sha256     text NOT NULL,
    updated_at timestamptz NOT NULL DEFAULT now(),
    content    text NOT NULL
)
"""


def files() -> list[Path]:
    found: list[Path] = []
    for folder in FOLDERS:
        base = ROOT / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            # Drafts are half-written parts of a run in progress.
            if any(part.startswith(".") for part in path.relative_to(ROOT).parts):
                continue
            if path.is_file() and path.suffix in SUFFIXES:
                found.append(path)
    found += [p for p in sorted((ROOT / "learning").glob("*.md")) if p.is_file()]
    return found


def main() -> int:
    url = os.environ.get("BACKUP_DATABASE_URL", "").strip()
    if not url:
        print("no BACKUP_DATABASE_URL in the environment", file=sys.stderr)
        return 2

    rows = []
    skipped = []
    for path in files():
        raw = path.read_bytes()
        rel = str(path.relative_to(ROOT))
        if len(raw) > MAX_BYTES:
            skipped.append(f"{rel} ({len(raw)} bytes)")
            continue
        rows.append((rel, len(raw), hashlib.sha256(raw).hexdigest(),
                     raw.decode("utf-8", errors="replace")))

    with psycopg.connect(url) as conn, conn.cursor() as cur:
        cur.execute(DDL)
        # The mirror equals local: a file he deleted here goes there too.
        cur.execute("DELETE FROM hq.learning_files WHERE path <> ALL(%s)",
                    ([r[0] for r in rows],))
        cur.executemany(
            "INSERT INTO hq.learning_files (path, bytes, sha256, content)"
            " VALUES (%s, %s, %s, %s)"
            " ON CONFLICT (path) DO UPDATE SET bytes = EXCLUDED.bytes,"
            " sha256 = EXCLUDED.sha256, content = EXCLUDED.content,"
            " updated_at = now() WHERE hq.learning_files.sha256 <> EXCLUDED.sha256",
            rows,
        )
        conn.commit()
        cur.execute("SELECT count(*), coalesce(sum(bytes), 0) FROM hq.learning_files")
        count, total = cur.fetchone() or (0, 0)

    print(f"learning files on the mirror: {count} file(s), {total / 1024:.0f} KB")
    for line in skipped:
        print(f"  skipped, too large: {line}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
