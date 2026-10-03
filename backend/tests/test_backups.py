"""The nightly database dump runs in the backend, after the reindex.

A launchd job running /bin/bash could not read ~/Desktop ("Operation not
permitted"), and no dump had been made since 2026-09-02. pg_dump is faked
here with a small script; nothing touches the real database."""

from __future__ import annotations

import asyncio
import gzip
import inspect
import os
import time
from datetime import date
from pathlib import Path

import pytest

from hq import backups, engine


def _fake_pg_dump(tmp_path: Path, body: str) -> str:
    script = tmp_path / "pg_dump"
    script.write_text("#!/bin/sh\n" + body + "\n")
    script.chmod(0o755)
    return str(script)


@pytest.fixture
def snaps(tmp_path, monkeypatch) -> Path:
    folder = tmp_path / "snapshots"
    monkeypatch.setattr(backups, "snapshot_dir", lambda: folder)
    monkeypatch.setattr(backups, "REPO_DIR", tmp_path)
    return folder


def test_a_dump_is_gzipped_into_the_days_file(tmp_path, snaps, monkeypatch) -> None:
    fake = _fake_pg_dump(tmp_path, 'echo "-- dump of $3"; echo "CREATE TABLE t ();"')
    monkeypatch.setattr(backups, "pg_dump_path", lambda: fake)
    out = backups.dump_sync(date(2026, 10, 3))
    assert out["path"] == "snapshots/missionhq-2026-10-03.sql.gz" and out["bytes"] > 0
    text = gzip.decompress((snaps / "missionhq-2026-10-03.sql.gz").read_bytes()).decode()
    assert "CREATE TABLE t ();" in text and "postgresql://" in text
    assert not list(snaps.glob("*.part"))


def test_a_failed_dump_raises_and_leaves_no_file(tmp_path, snaps, monkeypatch) -> None:
    fake = _fake_pg_dump(tmp_path, 'echo "half a dump"; echo "connection refused" >&2; exit 1')
    monkeypatch.setattr(backups, "pg_dump_path", lambda: fake)
    with pytest.raises(RuntimeError, match="exited 1: connection refused"):
        backups.dump_sync(date(2026, 10, 3))
    assert list(snaps.iterdir()) == []                  # no dump and no .part


def test_a_hung_dump_is_stopped(tmp_path, snaps, monkeypatch) -> None:
    fake = _fake_pg_dump(tmp_path, "exec sleep 30")
    monkeypatch.setattr(backups, "pg_dump_path", lambda: fake)
    monkeypatch.setattr(backups, "DUMP_TIMEOUT_S", 0.5)
    started = time.monotonic()
    with pytest.raises(RuntimeError, match="stopped after"):
        backups.dump_sync(date(2026, 10, 3))
    assert time.monotonic() - started < 10 and list(snaps.iterdir()) == []


def test_dumps_older_than_two_weeks_are_pruned(snaps) -> None:
    snaps.mkdir()
    now = time.time()
    for name, age_days in (("missionhq-2026-09-01.sql.gz", 20), ("missionhq-2026-10-01.sql.gz", 2),
                           ("remote-sync.log", 30)):
        p = snaps / name
        p.write_text("x")
        os.utime(p, (now - age_days * 86400,) * 2)
    assert backups.prune(snaps, now=now) == 1
    assert sorted(p.name for p in snaps.iterdir()) == ["missionhq-2026-10-01.sql.gz",
                                                        "remote-sync.log"]


def test_the_dump_runs_after_the_nightly_reindex_as_a_step_that_cannot_fail_it(
        monkeypatch) -> None:
    src = inspect.getsource(engine._nightly_reindex)
    assert src.index("_publish_reader()") < src.index("_db_dump_step()")
    assert '@DBOS.step(name="backups.db_dump")' in inspect.getsource(engine._db_dump_step)

    def broken(day=None):
        raise FileNotFoundError("pg_dump is not on PATH")
    monkeypatch.setattr(backups, "dump_sync", broken)
    out = asyncio.run(inspect.unwrap(engine._db_dump_step)())
    assert out == {"error": "pg_dump is not on PATH"}
