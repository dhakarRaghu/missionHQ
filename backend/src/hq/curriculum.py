"""The applied-AI curriculum: 22 modules in 7 layers, read from the repo.

`learning/study-material/_curriculum/README.md` is the durable record. It
carries a table of modules with their layer, status, research file and planned
phases, and a core path of the eight worth doing first. That file is written
by hand and by research runs; this module parses it so the Courses page can
show the whole plan instead of only the courses that already exist.

Nothing here invents a module. A row that is not in the table is not a module,
and a module whose course exists is matched by its topic slug, so the page can
link the plan to the published course.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from hq.config import settings

CURRICULUM_DIR = "study-material/_curriculum"
README = "README.md"
# The statuses the README defines, weakest first.
STATUSES = ("not started", "partial", "ready", "complete")
# Module 1's research is a coverage file, not a dossier, so its name carries
# no topic. It is the published inference course.
KNOWN_TOPICS = {1: "inference-internals"}
# Every other module's dossier is `module-NN-<topic>.md`, and <topic> is the
# slug its course is published under (study-material/<topic>/course.json).
_DOSSIER_RE = re.compile(r"^module-\d+-([a-z0-9-]+)\.md$")

_ROW_RE = re.compile(
    r"^\|\s*(\d+)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|"
    r"\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*$"
)
_CORE_RE = re.compile(r"^\d+\.\s+Module\s+(\d+)", re.MULTILINE)


@dataclass(frozen=True)
class Module:
    number: int
    layer: str
    title: str
    status: str
    research: str
    planned_phases: str
    # Where it sits on the core path (1-based), or 0 when it is not on it.
    core_order: int
    # The published course, when one exists.
    topic: str

    def to_dict(self) -> dict[str, object]:
        return {
            "number": self.number, "layer": self.layer, "title": self.title,
            "status": self.status, "research": self.research,
            "planned_phases": self.planned_phases, "core_order": self.core_order,
            "topic": self.topic,
        }


def curriculum_path() -> Path:
    return settings().learning_dir / CURRICULUM_DIR / README


def _clean(cell: str) -> str:
    """A table cell without its markdown emphasis or backticks.

    Only `**bold**` goes: a single `*` is part of a file name in this table
    (`raw-research/module-04-*.md`), and stripping it printed a path that does
    not exist.
    """
    return re.sub(r"\*\*|`", "", cell).strip()


def _topic(number: int, status: str, research: str) -> str:
    """The published course behind a module, or "" while it has none.

    Only a complete module has a course: a ready one has a dossier and no
    phases yet, so its name is a plan, not a link.
    """
    if number in KNOWN_TOPICS:
        return KNOWN_TOPICS[number]
    match = _DOSSIER_RE.match(research)
    return match.group(1) if match and status == "complete" else ""


@lru_cache(maxsize=1)
def _parse(text: str, mtime: float) -> tuple[Module, ...]:
    # mtime is not read: it is in the signature so a changed file misses the cache.
    core = [int(m.group(1)) for m in _CORE_RE.finditer(text)]
    modules: list[Module] = []
    for line in text.splitlines():
        match = _ROW_RE.match(line)
        if not match:
            continue
        number = int(match.group(1))
        status = _clean(match.group(4)).lower()
        if status not in STATUSES:
            continue  # the header row, or a table that is not this one
        modules.append(Module(
            number=number,
            layer=_clean(match.group(2)),
            title=_clean(match.group(3)),
            status=status,
            research=_clean(match.group(5)),
            planned_phases=_clean(match.group(6)),
            core_order=core.index(number) + 1 if number in core else 0,
            topic=_topic(number, _clean(match.group(4)).lower(), _clean(match.group(5))),
        ))
    return tuple(sorted(modules, key=lambda m: m.number))


def load_modules() -> list[Module]:
    """Every module in the curriculum, in order. Empty when the file is absent."""
    path = curriculum_path()
    if not path.is_file():
        return []
    return list(_parse(path.read_text(), path.stat().st_mtime))


def layers(modules: list[Module] | None = None) -> list[tuple[str, list[Module]]]:
    """The modules grouped by layer, in the order the layers first appear."""
    out: dict[str, list[Module]] = {}
    for module in modules if modules is not None else load_modules():
        out.setdefault(module.layer, []).append(module)
    return list(out.items())
