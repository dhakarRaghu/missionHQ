"""Constructs the DBOS instance exactly once, before any @DBOS decorator is used.

Import this module before importing any module that decorates workflows/steps.
``DBOS.launch()`` itself happens later, in the API lifespan (single owner).
"""

from __future__ import annotations

import hashlib
import hmac
from pathlib import Path

from dbos import DBOS, DBOSConfig
from dbos._error import (
    DBOSPatchNondeterminismError,
    DBOSStreamNondeterminismError,
    DBOSUnexpectedStepError,
)

from hq.config import settings

# A replay that calls a different step than the first run did. Code that
# catches every exception must let these through: caught, the replay goes on
# with its step numbers shifted, and DBOS reports a later step under the
# wrong name. On 2026-09-29 the engine's handler caught "writer.tighten was
# recorded when writer.section was expected" and failed again at its own
# bookkeeping, with "emit_step was recorded when _finish_run was expected".
REPLAY_ERRORS = (DBOSUnexpectedStepError, DBOSPatchNondeterminismError,
                 DBOSStreamNondeterminismError)


def code_version() -> str:
    """What a replay depends on: every backend source file, the libraries
    (uv.lock), the shared rule files the checks read, and the employer list
    the checks hold text to.
    DBOS's own version hashes only the workflow bodies, so a changed check
    (a sentence limit, a regex) was replayed against steps the old check
    chose. A new version is never replayed: the engine requeues its runs on
    boot, and the writer resumes from its saved parts."""
    digest = hashlib.sha256()
    src = Path(__file__).resolve().parent
    rules = settings().agents_dir / "_shared"
    lock = src.parents[1] / "uv.lock"       # the libraries a replay runs on
    for path in sorted([*src.rglob("*.py"), *rules.glob("*.yaml"),
                        *([lock] if lock.is_file() else [])]):
        digest.update(str(path.relative_to(path.parents[1])).encode())
        digest.update(path.read_bytes())
    # The version is stored and logged, and the repository is public: a plain
    # hash of the names could be tested against guesses. Keyed with the
    # database URL, which only this install holds, it cannot.
    digest.update(hmac.new(settings().database_url.encode(),
                           "\n".join(settings().private_employers).encode(),
                           hashlib.sha256).digest())
    return digest.hexdigest()[:32]


_config: DBOSConfig = {
    "name": "missionhq",
    "system_database_url": settings().database_url,
    "application_version": code_version(),
}

dbos = DBOS(config=_config)

__all__ = ["DBOS", "REPLAY_ERRORS", "dbos"]
