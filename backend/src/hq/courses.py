"""The locally authored courses: parse `learning/courses/*/course.md`.

Course phases used to come from one place, his study platform, and the only
thing that tied the teach pipeline to that platform was where the module text
was fetched from. The seven courses written on 2026-09-14 live as spec files
in this repo instead — structure only, no content yet — and this module turns
those files into the same `hq.course_phases` rows the platform's phases use,
so hunter, tutor, the Courses page and the read gate need no second path.

The format is documented in `learning/courses/README.md`. It is written to be
edited by hand, so parsing is deliberately forgiving about whitespace and
strict about the things code relies on: the course header keys, the
`## Phase N — Title` headings, and the `key: value` lines under each.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from hq.config import settings

COURSES_DIR = "courses"

_HEADER_KEY_RE = re.compile(r"^([a-z][a-z-]*):\s*(.*?)\s*$")
_COURSE_TITLE_RE = re.compile(r"^#\s+Course\s+(\d+)\s+[—-]+\s+(.+?)\s*$")
_PHASE_RE = re.compile(r"^##\s+Phase\s+(\d+)\s+[—-]+\s+(.+?)\s*$")
_SUBHEAD_RE = re.compile(r"^###\s+(.+?)\s*$")
_SECTION_LINE_RE = re.compile(r"^\d+\.\d+\s+[—-]+\s+(.+?)\s*$")

# Phases the platform still lists that he asked to drop from Mission HQ on
# 2026-09-14: "remove haskell, next-js, go-mastery". They stay on his platform;
# the sync just stops importing them, and migration 024 removed the rows.
EXCLUDED_PLATFORM_COURSES = frozenset({
    "haskell",
    "next-js-16-app-router-server-vs-client-components",
    "go-mastery",
    "database-schema-design-principles",
    "databases",
    "own-production-code-understanding",
})


@dataclass
class PhaseSpec:
    order: int
    title: str
    question: str = ""
    minutes: int = 0
    assumes: str = ""
    introduces: str = ""
    leaves_for_later: str = ""
    why: str = ""
    sections: list[str] = field(default_factory=list)
    lab: str = ""
    demonstrate: str = ""
    test_out: str = ""
    body: str = ""  # the whole `## Phase` block, verbatim — what tutor reads

    def slug(self, course_slug: str) -> str:
        """`<course>-phase-<NN>-<title>`, which `course_sequence` can order."""
        tail = re.sub(r"[^a-z0-9]+", "-", self.title.lower()).strip("-")[:48]
        return f"{course_slug}-phase-{self.order:02d}-{tail}"


@dataclass
class CourseSpec:
    slug: str
    order: int
    title: str
    source: str = "local"  # "local" | "platform"
    platform_course: str = ""
    language: str = ""
    description: str = ""
    phases: list[PhaseSpec] = field(default_factory=list)
    path: str = ""

    @property
    def course_key(self) -> str:
        """The value of `course_phases.course` for this course's rows."""
        return self.platform_course if self.source == "platform" else self.slug


def courses_dir() -> Path:
    return settings().learning_dir / COURSES_DIR


def parse_course(text: str, path: str = "") -> CourseSpec:
    lines = text.splitlines()
    course = CourseSpec(slug="", order=0, title="", path=path)

    # --- header: the title line and the key: value lines before the first ## ---
    i = 0
    while i < len(lines) and not lines[i].startswith("## "):
        line = lines[i]
        m = _COURSE_TITLE_RE.match(line)
        if m:
            course.order, course.title = int(m.group(1)), m.group(2)
        else:
            k = _HEADER_KEY_RE.match(line)
            if k:
                key, value = k.group(1), k.group(2)
                if key == "slug":
                    course.slug = value
                elif key == "source":
                    course.source = value
                elif key == "platform-course":
                    course.platform_course = value
                elif key == "language":
                    course.language = value
        i += 1
    if not course.slug:
        raise ValueError(f"{path or 'course'}: missing `slug:` in the header")

    # `## Why this course` is the description shown on the Courses page.
    desc = _block_after(lines, "## Why this course")
    course.description = " ".join(desc.split())[:1200]

    # --- phases ---
    starts = [n for n, line in enumerate(lines) if _PHASE_RE.match(line)]
    for idx, start in enumerate(starts):
        end = starts[idx + 1] if idx + 1 < len(starts) else _next_h2(lines, start + 1)
        block = lines[start:end]
        m = _PHASE_RE.match(block[0])
        assert m is not None
        phase = PhaseSpec(order=int(m.group(1)), title=m.group(2), body="\n".join(block))
        # key: value lines directly under the heading
        n = 1
        while n < len(block) and not block[n].startswith("###"):
            k = _HEADER_KEY_RE.match(block[n])
            if k:
                key, value = k.group(1), k.group(2)
                if key == "question":
                    phase.question = value
                elif key == "minutes":
                    phase.minutes = int(value) if value.isdigit() else 0
                elif key == "assumes":
                    phase.assumes = value
                elif key == "introduces":
                    phase.introduces = value
                elif key == "leaves-for-later":
                    phase.leaves_for_later = value
            n += 1
        phase.why = _sub(block, "Why you're here")
        phase.lab = _sub(block, "Lab")
        phase.demonstrate = _sub(block, "Demonstrate")
        phase.test_out = _sub(block, "Test out")
        phase.sections = [
            m2.group(1) for line in _sub(block, "Sections").splitlines()
            if (m2 := _SECTION_LINE_RE.match(line.strip()))
        ]
        course.phases.append(phase)

    course.phases.sort(key=lambda p: p.order)
    return course


def load_courses() -> list[CourseSpec]:
    """Every course spec on disk, in path order (01-, 02-, …)."""
    root = courses_dir()
    if not root.exists():
        return []
    out: list[CourseSpec] = []
    for path in sorted(root.glob("*/course.md")):
        out.append(parse_course(path.read_text(encoding="utf-8"), str(path.relative_to(settings().learning_dir.parent))))
    return out


def find_phase(slug: str) -> tuple[CourseSpec, PhaseSpec] | None:
    """The local course and phase behind a `course_phases.slug`, or None."""
    for course in load_courses():
        if course.source != "local":
            continue
        for phase in course.phases:
            if phase.slug(course.slug) == slug:
                return course, phase
    return None


# --- helpers ------------------------------------------------------------------

def _next_h2(lines: list[str], start: int) -> int:
    for n in range(start, len(lines)):
        if lines[n].startswith("## "):
            return n
    return len(lines)


def _block_after(lines: list[str], heading: str) -> str:
    for n, line in enumerate(lines):
        if line.strip() == heading:
            return "\n".join(lines[n + 1:_next_h2(lines, n + 1)]).strip()
    return ""


def _sub(block: list[str], name: str) -> str:
    """The text under `### <name>` inside one phase block."""
    for n, line in enumerate(block):
        m = _SUBHEAD_RE.match(line)
        if m and m.group(1).strip().lower() == name.lower():
            end = len(block)
            for k in range(n + 1, len(block)):
                if _SUBHEAD_RE.match(block[k]):
                    end = k
                    break
            return "\n".join(block[n + 1:end]).strip()
    return ""
