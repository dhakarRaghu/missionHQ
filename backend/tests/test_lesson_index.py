"""learning/lessons/index.json: written from the database, merged, never shrunk."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from hq import lesson_index


def test_an_export_keeps_the_other_laptops_lessons(tmp_path, monkeypatch) -> None:
    path = tmp_path / "index.json"
    other = {"md_path": "learning/lessons/2026-10-04-b.md", "title": "From the other laptop",
             "lesson_date": "2026-10-04", "kind": "course"}
    mine_old = {"md_path": "learning/lessons/2026-10-01-a.md", "title": "Old title",
                "lesson_date": "2026-10-01", "kind": "topic"}
    path.write_text(json.dumps([other, mine_old]))
    monkeypatch.setattr(lesson_index, "index_path", lambda: path)

    async def fetch(sql: str, params: Any = ()) -> list[dict[str, Any]]:
        return [{**{k: "" for k in lesson_index.FIELDS}, "md_path": mine_old["md_path"],
                 "title": "New title", "lesson_date": "2026-10-01", "kind": "topic"}]

    monkeypatch.setattr(lesson_index.db, "fetch", fetch)
    assert asyncio.run(lesson_index.export()) == 2
    written = {e["md_path"]: e for e in json.loads(path.read_text())}
    assert written[other["md_path"]]["title"] == "From the other laptop"   # kept
    assert written[mine_old["md_path"]]["title"] == "New title"            # this row wins
