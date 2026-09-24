"""The continuity block: state a scheduled sage run reads as data, never
re-derives.

Every code-built brief for a sage cron entry with a skill ends with a
``## Continuity`` block. Code builds it from the ledger and the vault at
dispatch, so the model does not count, does not remember last night, and
does not repeat a "Needs you" line whose subject the ledger already closed.

What it holds, by skill (``for_skill``):

- what last night's note led with, so tonight leads with something else;
- the "Needs you" lines of the last three notes, each with the status the
  ledger gives its subject now (a job row, a task, a lesson, a decision);
- the open decisions in ``memory/decisions.md`` with their age in days;
- counters code computed: unread lessons, lessons written and read this
  week, jobs found, strong and applied this week, open operator requests;
- for the shortlist: every candidate row's status, score, pay (stated,
  estimated or none) and when it was last live-checked;
- the owner-state block (``hq.owner_state``) where a claim about him is
  possible.

The renderers are pure: they take rows and text and return the block, so
every shape is tested without a database. The readers are small and each
one is guarded: a table that cannot be read shows as "not readable", never
as a zero that looks like a fact, and ``for_skill`` never raises, because a
brief that cannot be built would stop the night's run.
"""

from __future__ import annotations

import asyncio
import logging
import re
import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from hq import db, memory, owner_state
from hq.config import settings

log = logging.getLogger(__name__)

HEADING = "## Continuity"
LIMIT_CHARS = 2_500
NEEDS_NIGHTS = 3
COUNTER_DAYS = 7
STALE_DECISION_DAYS = 7
SHORTLIST_ROWS = 12
LINE_CHARS = 80          # a quoted "Needs you" line is cut here
STATUS_PARTS = 5         # ledger subjects named per line; the rest is "+N more"
PROPER_MIN_CHARS = 6
NOT_RECORDED = "not recorded"
NOT_READABLE = "not readable"
NOT_IN_LEDGER = "not in any ledger"
CLOSED_MARK = "[closed]"
OPEN_MARK = "[still open]"
DECISIONS_PATH = "memory/decisions.md"
DAILY_DIR = "daily"
OPEN_JOB_STATUSES = ("seen", "shortlisted", "referral")
CLOSED_JOB_STATUSES = ("closed", "rejected")
DONE_TASK_STATUSES = ("done", "failed", "archived")
SKILLS = ("daily-note", "consolidate", "job-shortlist", "daily-posts", "weekly-review")
# Which sections each skill's brief carries. The daily note gets everything;
# the shortlist gets the rows it must pick from; the posts and the review get
# what he has done, because that is where a claim about him is possible.
SECTIONS: dict[str, tuple[str, ...]] = {
    "daily-note": ("lead", "needs", "decisions", "counters", "owner"),
    "consolidate": ("needs", "decisions", "counters"),
    "job-shortlist": ("shortlist", "decisions", "counters"),
    "daily-posts": ("lead", "counters", "owner"),
    "weekly-review": ("needs", "decisions", "counters", "owner"),
}

_DAILY_NAME_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")
_DATE_RE = re.compile(r"(?<!\d)(20\d\d-\d\d-\d\d)(?!\d)")
_NEEDS_HEADING_RE = re.compile(r"^(?:#{1,6}\s*)?\**needs you\**:?\s*$", re.IGNORECASE)
_LABEL_RE = re.compile(r"^\**[A-Za-z][\w ]{1,30}\**:\s*$")
_LEAD_PREFIX_RE = re.compile(
    r"^(?:the one thing(?: you did not know)?|one thing)\s*[:.]?\s*", re.IGNORECASE)
_TASK_ID_RE = re.compile(r"\b[0-9a-f]{8}\b")
_PHASE_RE = re.compile(r"\bphase\s+\d+\s?[a-z]?\b", re.IGNORECASE)
_PROPER_RE = re.compile(r"[A-Z][\w.-]*[\w]")
_SENTENCE_END_RE = re.compile(r"(?<=[.!?])\s")


# --- vault parsing (pure) ------------------------------------------------------


def _body(text: str) -> str:
    _meta, body = memory.parse_frontmatter(text)
    return body


def parse_lead(text: str) -> str:
    """What a daily note leads with: the first sentence of its first paragraph
    after the title, with the "one thing" label and bold marks removed."""
    lines = _body(text).splitlines()
    paragraph: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            if paragraph:
                break
            continue
        if stripped.startswith(("- ", "* ")):
            if paragraph:
                break
            continue
        paragraph.append(stripped)
    joined = " ".join(paragraph).replace("**", "").strip()
    joined = _LEAD_PREFIX_RE.sub("", joined)
    first = _SENTENCE_END_RE.split(joined, maxsplit=1)[0].strip()
    return _cut(first, 160)


def parse_needs_you(text: str) -> list[str]:
    """The bullet lines of a note's "Needs you" section, wrapped continuation
    lines joined. Both shapes are read: ``## Needs you`` and ``Needs you:``.
    The section ends at the next heading, the next ``Label:`` line, or a
    plain paragraph after the bullets."""
    out: list[str] = []
    inside = False
    for line in _body(text).splitlines():
        stripped = line.strip()
        if not inside:
            inside = bool(_NEEDS_HEADING_RE.match(stripped))
            continue
        if not stripped:
            continue
        if stripped.startswith("#") or _LABEL_RE.match(stripped):
            break
        if stripped.startswith(("- ", "* ")):
            out.append(stripped[2:].strip())
        elif out and line[:1] in (" ", "\t"):
            out[-1] = out[-1] + " " + stripped
        elif out:
            break
        else:
            out.append(stripped)
    return [ln.replace("**", "") for ln in out if ln]


def parse_decisions(text: str) -> tuple[list[str], list[str]]:
    """``(open, decided)`` lines of memory/decisions.md."""
    open_: list[str] = []
    decided: list[str] = []
    section = ""
    for line in _body(text).splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            section = stripped.lstrip("#").strip().lower()
            continue
        if stripped.startswith(("- ", "* ")):
            item = stripped[2:].strip()
            if section.startswith("open"):
                open_.append(item)
            elif section.startswith("decided"):
                decided.append(item)
    return open_, decided


def date_on_line(line: str) -> date | None:
    m = _DATE_RE.search(line)
    if not m:
        return None
    try:
        return date.fromisoformat(m.group(1))
    except ValueError:
        return None


def line_added_in_git(line: str, rel_path: str = DECISIONS_PATH) -> date | None:
    """The day a line first appeared in a vault file, from the vault's own git
    history. None when the vault is not a repo or the line is uncommitted."""
    vault = settings().vault_dir
    if not (vault / ".git").exists():
        return None
    try:
        out = subprocess.run(
            ["git", "log", "--reverse", "--format=%aI", "-S", line, "--", rel_path],
            cwd=vault, check=True, capture_output=True, text=True, timeout=10,
        ).stdout
    except (subprocess.SubprocessError, OSError):
        return None
    first = out.strip().splitlines()[0] if out.strip() else ""
    try:
        return datetime.fromisoformat(first).date() if first else None
    except ValueError:
        return None


# --- matching a "Needs you" line to the ledger (pure) ---------------------------


@dataclass
class Ledger:
    """The rows a "Needs you" line can be about. Every list may be empty."""
    jobs: list[dict[str, Any]] = field(default_factory=list)
    tasks: list[dict[str, Any]] = field(default_factory=list)
    lessons: list[dict[str, Any]] = field(default_factory=list)
    open_decisions: list[str] = field(default_factory=list)
    decided: list[str] = field(default_factory=list)


def company_key(company: str) -> str:
    """The name a note would use: "Cardboard (YC W26)" is "Cardboard"."""
    return re.split(r"\s*[(,/]", company.strip(), maxsplit=1)[0].strip()


def _mentions(line: str, key: str) -> bool:
    return len(key) >= 4 and re.search(rf"(?<!\w){re.escape(key)}(?!\w)", line, re.IGNORECASE) is not None


def proper_nouns(text: str) -> list[str]:
    """Distinctive tokens of a decision line: capitalised words past the first
    of six letters or more, and any token with a digit, hyphen or dot inside
    (YC-India, Optifye.ai). "India" alone is not distinctive: it matched
    "YC-India" and "India-remote" and tied every job line to every decision."""
    words = text.split()
    out: list[str] = []
    for i, raw in enumerate(words):
        token = raw.strip("()[]{}:;,.?!\"'")
        if len(token) < 4:
            continue
        marked = bool(re.search(r"[\d-]|\.\w", token))
        if marked or (i > 0 and len(token) >= PROPER_MIN_CHARS and _PROPER_RE.fullmatch(token)):
            out.append(token)
    return out


def pay_text(pay_lakh: float | None, estimated: object) -> str:
    """"stated 30 LPA", "estimated 35 LPA" or "no figure"."""
    if pay_lakh is None:
        return "no figure"
    kind = "estimated" if _truthy(estimated) else "stated"
    return f"{kind} {float(pay_lakh):g} LPA"


def _pay_short(pay_lakh: float | None, estimated: object) -> str:
    return pay_text(pay_lakh, estimated).replace("estimated", "est")


def _truthy(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in ("true", "t", "1", "yes")
    return bool(value)


def _day(value: object) -> str:
    if isinstance(value, datetime | date):
        return f"{value:%Y-%m-%d}"
    if isinstance(value, str) and value:
        return value[:10]
    return "?"


def _job_line(row: dict[str, Any]) -> str:
    """"Cloudflare seen 10/10, est 35 LPA, seen 09-24" or "Cardboard CLOSED"."""
    status = str(row.get("status") or "?")
    if status in CLOSED_JOB_STATUSES:
        return f"{company_key(str(row.get('company') or ''))} {status.upper()}"
    return (f"{company_key(str(row.get('company') or ''))} {status}"
            f" {row.get('fit_score', '?')}/10, {_pay_short(row.get('pay_lakh'), row.get('estimated'))},"
            f" checked {_day(row.get('last_seen'))[5:]}")


def _pick_job(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """One row per company: the strongest open one, else the newest closed."""
    open_rows = [r for r in rows if str(r.get("status")) not in CLOSED_JOB_STATUSES]
    if open_rows:
        return max(open_rows, key=lambda r: (int(r.get("fit_score") or 0), _day(r.get("last_seen"))))
    return max(rows, key=lambda r: _day(r.get("last_seen")))


def line_status(line: str, ledger: Ledger) -> tuple[str, bool | None]:
    """``(status text, closed)`` for one "Needs you" line. ``closed`` is True
    when every subject found is closed, done, read or decided; None when no
    ledger row matches the line at all."""
    parts: list[str] = []
    closed: list[bool] = []

    by_company: dict[str, list[dict[str, Any]]] = {}
    for row in ledger.jobs:
        key = company_key(str(row.get("company") or ""))
        if key and _mentions(line, key):
            by_company.setdefault(key, []).append(row)
    for key in sorted(by_company):
        row = _pick_job(by_company[key])
        parts.append("job " + _job_line(row))
        closed.append(str(row.get("status")) in CLOSED_JOB_STATUSES)

    ids = set(_TASK_ID_RE.findall(line))
    for row in ledger.tasks:
        tid = str(row.get("id") or "")
        if tid[:8] in ids:
            status = str(row.get("status") or "?")
            parts.append(f"task {tid[:8]} {status}")
            closed.append(status in DONE_TASK_STATUSES)

    phases = {" ".join(m.group(0).lower().split()) for m in _PHASE_RE.finditer(line)}
    for row in ledger.lessons:
        title = str(row.get("title") or "")
        norm = " ".join(title.lower().split())
        if any(_mentions(norm, p) or _mentions(norm, p.replace(" ", "")) for p in phases):
            read_at = row.get("read_at")
            state = f"read {_day(read_at)}" if read_at else "unread"
            parts.append(f"lesson “{_cut(title, 40)}” {state}")
            closed.append(bool(read_at))

    for item, state in ((d, "open") for d in ledger.open_decisions):
        if any(_mentions(line, key) for key in proper_nouns(item)):
            parts.append(f"decision {state}: {_cut(item, 50)}")
            closed.append(False)
    for item in ledger.decided:
        if any(_mentions(line, key) for key in proper_nouns(item)):
            parts.append(f"decided: {_cut(item, 50)}")
            closed.append(True)

    if not parts:
        return NOT_IN_LEDGER, None
    if len(parts) > STATUS_PARTS:
        # The closed ones first, so a closed subject is never the one cut.
        parts.sort(key=lambda p: 0 if p.endswith(("CLOSED", "REJECTED")) or "decided:" in p else 1)
        parts = parts[:STATUS_PARTS] + [f"+{len(parts) - STATUS_PARTS} more"]
    return "; ".join(parts), all(closed)


@dataclass
class Need:
    """One "Needs you" line with the status the ledger gives it now. ``also``
    holds the earlier nights the same status line was raised on."""
    day: str
    line: str
    status: str
    closed: bool | None
    also: list[str] = field(default_factory=list)


def dedupe_needs(needs: list[Need]) -> list[Need]:
    """Newest first. A line raised again on a later night with the same
    ledger status is one entry that names every night, so the model sees
    that it has been repeating without reading it three times."""
    def key(n: Need) -> str:
        if n.closed is not None:
            return n.status
        return re.sub(r"[^\w ]", "", n.line.lower())[:60]

    out: list[Need] = []
    for need in sorted(needs, key=lambda n: n.day, reverse=True):
        prior = next((o for o in out if key(o) == key(need)), None)
        if prior is not None:
            prior.also.append(need.day)
        else:
            out.append(Need(need.day, need.line, need.status, need.closed, list(need.also)))
    return out


# --- rendering (pure) ----------------------------------------------------------


@dataclass
class Counters:
    unread_by_kind: dict[str, int] | None = None     # None: not readable
    written: int | None = None
    read: int | None = None
    jobs_found: int | None = None
    jobs_strong: int | None = None
    jobs_applied: int | None = None
    open_requests: int | None = None
    days: int = COUNTER_DAYS


def _n(value: int | None) -> str:
    return NOT_READABLE if value is None else str(value)


def render_counters(c: Counters) -> list[str]:
    if c.unread_by_kind is None:
        unread = NOT_READABLE
    elif not c.unread_by_kind:
        unread = "0"
    else:
        total = sum(c.unread_by_kind.values())
        unread = f"{total} (" + ", ".join(
            f"{k} {n}" for k, n in sorted(c.unread_by_kind.items())) + ")"
    return [
        f"- Days since he last published a post: {NOT_RECORDED} (nothing records a post going out)",
        f"- Unread lessons: {unread}",
        f"- Last {c.days} days: lessons written {_n(c.written)}, read {_n(c.read)}",
        (f"- Last {c.days} days: jobs found {_n(c.jobs_found)}, strong {_n(c.jobs_strong)},"
         f" applied {_n(c.jobs_applied)}"),
        f"- Open operator requests: {_n(c.open_requests)}",
    ]


def render_decisions(decisions: list[tuple[str, int | None]]) -> list[str]:
    """Open decisions with their age; seven days or more gets the flag."""
    out: list[str] = []
    for text, age in decisions:
        if age is None:
            tail = "age unknown"
        else:
            tail = f"open {age} day{'' if age == 1 else 's'}"
            if age >= STALE_DECISION_DAYS:
                tail += "; propose a default"
        out.append(f"- {_cut(text, 90)} ({tail})")
    return out


def render_needs(needs: list[Need]) -> list[str]:
    """One status line per need. These are never truncated away: they are
    what stops a closed item repeating."""
    out: list[str] = []
    for n in needs:
        mark = OPEN_MARK if n.closed is False else (CLOSED_MARK if n.closed else f"[{NOT_IN_LEDGER}]")
        days = n.day[5:] + (f" (also {', '.join(d[5:] for d in n.also)})" if n.also else "")
        out.append(f"- {mark} {days}: “{_cut(n.line, LINE_CHARS)}” -> {n.status}")
    return out


def render_shortlist(rows: list[dict[str, Any]], bar: float) -> list[str]:
    out = [
        (f"Candidate rows (open statuses, best first). `file_shortlist` allows action"
         f" \"apply\" only for STATED pay at or above {bar:g} LPA, and refuses a closed row;"
         " estimated or missing pay gets \"verify_pay\"."),
    ]
    for r in rows:
        job_id = str(r.get("job_id") or r.get("id") or "")[:8]
        out.append(
            f"- {job_id} {_cut(str(r.get('company') or ''), 28)}, {_cut(str(r.get('role') or ''), 40)}:"
            f" {r.get('status', '?')} {r.get('fit_score', '?')}/10,"
            f" {pay_text(r.get('pay_lakh'), r.get('estimated'))},"
            f" live-checked {_day(r.get('last_seen'))}")
    if len(out) == 1:
        out.append("- no open rows in the ledger")
    return out


def render_block(
    *,
    sections: tuple[str, ...],
    lead: tuple[str, str] | None = None,
    needs: list[Need] | None = None,
    decisions: list[tuple[str, int | None]] | None = None,
    counters: Counters | None = None,
    shortlist: list[dict[str, Any]] | None = None,
    bar: float = 25.0,
    owner: str = "",
    limit: int = LIMIT_CHARS,
) -> str:
    """The block, under ``limit`` characters. Lists are cut from the end to
    fit (with a count of what was left out); the "Needs you" status lines and
    the counters are never cut. The owner-state block follows it whole; it
    keeps its own limit and is not counted here."""
    fixed: list[str] = [HEADING, ("Built by code from the ledger and the vault. Read it as"
                                  " fact; do not count or recall these yourself.")]
    if "lead" in sections:
        if lead:
            fixed.append(f"Last note ({lead[0]}) led with: “{lead[1]}”."
                         " Tonight leads with something else.")
        else:
            fixed.append("Last note: none found. Tonight has no subject to avoid.")
    if "needs" in sections:
        fixed.append(f"Needs-you lines from the last {NEEDS_NIGHTS} notes, with their status now"
                     f" ({CLOSED_MARK} means do not repeat it):")
        fixed.extend(render_needs(needs or []) or ["- none"])
    cuttable: list[tuple[str, list[str]]] = []
    if "decisions" in sections:
        cuttable.append(("Open decisions (memory/decisions.md):",
                         render_decisions(decisions or []) or ["- none open"]))
    if "shortlist" in sections:
        head, *rows = render_shortlist(shortlist or [], bar)
        cuttable.append((head, rows))
    if "counters" in sections:
        fixed.append("Counters, computed by code:")
        fixed.extend(render_counters(counters or Counters()))
    tail = owner.strip() if "owner" in sections and owner.strip() else ""

    def assemble(kept: list[list[str]]) -> str:
        parts = list(fixed)
        for (head, _rows), rows in zip(cuttable, kept, strict=True):
            parts.append(head)
            parts.extend(rows)
        return "\n".join(parts)

    kept = [list(rows) for _h, rows in cuttable]
    text = assemble(kept)
    while len(text) > limit and any(len(rows) > 1 for rows in kept):
        longest = max(range(len(kept)), key=lambda i: len(kept[i]))
        rows = kept[longest]
        rows.pop(-2 if rows[-1].startswith("- (") else -1)
        left = len(cuttable[longest][1]) - sum(1 for r in rows if not r.startswith("- ("))
        if rows and rows[-1].startswith("- ("):
            rows[-1] = f"- ({left} more not shown)"
        else:
            rows.append(f"- ({left} more not shown)")
        text = assemble(kept)
    return text + ("\n\n" + tail if tail else "")


def _cut(text: str, limit: int) -> str:
    text = " ".join(text.split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


# --- readers ---------------------------------------------------------------------


async def _rows(sql: str, params: tuple[Any, ...] = ()) -> list[dict[str, Any]] | None:
    """Rows, or None when the source cannot be read. A brief is built at
    dispatch; a table that is missing must not stop the night."""
    try:
        return await db.fetch(sql, params)
    except Exception:
        log.warning("continuity: could not read %s", sql[:60], exc_info=True)
        return None


def _daily_notes(limit: int) -> list[tuple[str, str]]:
    """``(day, text)`` of the newest daily notes, newest first."""
    folder: Path = settings().vault_dir / DAILY_DIR
    if not folder.is_dir():
        return []
    days = sorted((p for p in folder.iterdir() if _DAILY_NAME_RE.match(p.name)),
                  key=lambda p: p.name, reverse=True)
    out: list[tuple[str, str]] = []
    for path in days[:limit]:
        try:
            out.append((path.name[:-3], path.read_text()))
        except OSError:
            continue
    return out


def _read_decisions() -> str:
    try:
        return memory.read(DECISIONS_PATH)
    except (OSError, ValueError, PermissionError):
        return ""


def decisions_with_age(
    text: str, today: date, added: Callable[[str], date | None] = line_added_in_git,
) -> tuple[list[tuple[str, int | None]], list[str]]:
    """Open decisions with their age in days (a date on the line, else the
    day git first saw the line, else None) and the decided lines."""
    open_, decided = parse_decisions(text)
    aged: list[tuple[str, int | None]] = []
    for line in open_:
        when = date_on_line(line) or added(line)
        aged.append((line, (today - when).days if when else None))
    return aged, decided


async def _ledger(lines: list[str], decisions: str) -> Ledger:
    open_, decided = parse_decisions(decisions)
    ledger = Ledger(open_decisions=open_, decided=decided)
    ledger.jobs = await _rows(
        "SELECT id::text AS job_id, company, role, status, fit_score, pay_lakh::float8 AS pay_lakh,"
        " fit_parts->'pay'->>'estimated' AS estimated, last_seen FROM hq.jobs") or []
    ids = sorted({m for ln in lines for m in _TASK_ID_RE.findall(ln)})
    if ids:
        ledger.tasks = await _rows(
            "SELECT id::text AS id, status FROM hq.tasks WHERE left(id::text, 8) = ANY(%s)",
            (ids,)) or []
    ledger.lessons = await _rows(
        "SELECT title, kind, read_at FROM hq.lessons ORDER BY lesson_date DESC LIMIT 60") or []
    return ledger


async def _counters(now: datetime) -> Counters:
    since = now - timedelta(days=COUNTER_DAYS)
    c = Counters(days=COUNTER_DAYS)
    unread = await _rows(
        "SELECT kind, count(*) AS n FROM hq.lessons WHERE read_at IS NULL GROUP BY kind")
    if unread is not None:
        c.unread_by_kind = {str(r["kind"]): int(r["n"]) for r in unread}
    lessons = await _rows(
        "SELECT count(*) FILTER (WHERE created_at >= %s) AS written,"
        " count(*) FILTER (WHERE read_at >= %s) AS read FROM hq.lessons", (since, since))
    if lessons:
        c.written, c.read = int(lessons[0]["written"]), int(lessons[0]["read"])
    jobs = await _rows(
        "SELECT count(*) FILTER (WHERE first_seen >= %s) AS found,"
        " count(*) FILTER (WHERE first_seen >= %s AND fit_bucket = 'strong') AS strong,"
        " count(*) FILTER (WHERE status = 'applied' AND updated_at >= %s) AS applied"
        " FROM hq.jobs", (since, since, since))
    if jobs:
        c.jobs_found = int(jobs[0]["found"])
        c.jobs_strong = int(jobs[0]["strong"])
        c.jobs_applied = int(jobs[0]["applied"])
    requests = await _rows(
        "SELECT count(*) AS n FROM hq.operator_requests WHERE status IN ('pending', 'dispatched')")
    if requests:
        c.open_requests = int(requests[0]["n"])
    return c


async def _shortlist_rows() -> list[dict[str, Any]]:
    return await _rows(
        "SELECT id::text AS job_id, company, role, status, fit_score, pay_lakh::float8 AS pay_lakh,"
        " fit_parts->'pay'->>'estimated' AS estimated, last_seen FROM hq.jobs"
        " WHERE status = ANY(%s) ORDER BY fit_score DESC, last_seen DESC LIMIT %s",
        (list(OPEN_JOB_STATUSES), SHORTLIST_ROWS)) or []


async def build(skill: str, now: datetime | None = None) -> str:
    """The block for one skill, or "" for a skill that has none."""
    sections = SECTIONS.get(skill)
    if not sections:
        return ""
    now = now or datetime.now(UTC)
    today = memory.today()
    notes = await asyncio.to_thread(_daily_notes, NEEDS_NIGHTS)
    decisions_text = await asyncio.to_thread(_read_decisions)

    lead = (notes[0][0], parse_lead(notes[0][1])) if notes and parse_lead(notes[0][1]) else None
    needs: list[Need] = []
    if "needs" in sections:
        raw = [(day, ln) for day, text in notes for ln in parse_needs_you(text)]
        ledger = await _ledger([ln for _d, ln in raw], decisions_text)
        for day, ln in raw:
            status, closed = line_status(ln, ledger)
            needs.append(Need(day, ln, status, closed))
        needs = dedupe_needs(needs)
    aged: list[tuple[str, int | None]] = []
    if "decisions" in sections:
        aged, _decided = await asyncio.to_thread(decisions_with_age, decisions_text, today)
    counters = await _counters(now) if "counters" in sections else None
    shortlist = await _shortlist_rows() if "shortlist" in sections else None
    owner = await owner_state.block() if "owner" in sections else ""
    return render_block(
        sections=sections, lead=lead, needs=needs, decisions=aged, counters=counters,
        shortlist=shortlist, bar=settings().job_target_ctc_lakh, owner=owner,
    )


async def for_skill(skill: str) -> str:
    """``build``, and never an exception: the brief goes out with whatever
    could be read, and a failure is a log line."""
    try:
        return await build(skill)
    except Exception:
        log.warning("continuity: block for %s could not be built", skill, exc_info=True)
        return f"{HEADING}\n\nThe ledger could not be read when this brief was built."
