"""Shared test setup."""

import pytest


@pytest.fixture(autouse=True)
def _no_lesson_index_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests record lessons against a stand-in database. The lesson index is a
    real file in git (learning/lessons/index.json): on 2026-10-06 a test run
    wrote one stand-in row over nineteen real ones and it was committed."""
    from hq import lesson_index

    async def nothing() -> None:
        return None

    monkeypatch.setattr(lesson_index, "export_quietly", nothing)
    monkeypatch.setattr(lesson_index, "sync_quietly", nothing)
