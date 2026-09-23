"""Constructs the DBOS instance exactly once, before any @DBOS decorator is used.

Import this module before importing any module that decorates workflows/steps.
``DBOS.launch()`` itself happens later, in the API lifespan (single owner).
"""

from __future__ import annotations

from dbos import DBOS, DBOSConfig

from hq.config import settings

_config: DBOSConfig = {
    "name": "missionhq",
    "system_database_url": settings().database_url,
}

dbos = DBOS(config=_config)

__all__ = ["DBOS", "dbos"]
