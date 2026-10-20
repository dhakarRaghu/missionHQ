#!/usr/bin/env python3
"""Term order for a course: every term is explained before a page uses it.

WHAT IT CHECKS
    1. The course term map (course.json): each phase lists the terms it
       introduces and the terms it assumes. Every assumed term must come from
       an earlier phase or from the learner profile.
    2. A page (a phase .md or a lesson .html): no term is used before the
       page defines it, unless the reader already has it. A term is defined
       where it is marked: <dfn>term</dfn> in HTML, *term* in Markdown.
    3. The chapter link: a phase names the phase before it near its start,
       and the phase after it near its end.

    The checks know nothing about any subject. The terms come from the map
    and from the page's own definitions; what the reader knows comes from the
    learner profile (_learner.json next to the course folders).

    This file is the single copy of the rules. Mission HQ keeps an identical
    copy at backend/src/hq/term_order.py; its tests compare the two.

HOW TO RUN
    python term_order.py --course <study-material>/<topic>            # map + every phase file
    python term_order.py --course <study-material>/<topic> --phase 3  # map + one phase
    python term_order.py --self-test

WHAT YOU SHOULD SEE
    term map: ok
    phase 3: 0 findings
    or one line per finding, then exit status 1.

COST
    Reads local files only. No network.
"""

from __future__ import annotations

import argparse
import html as html_lib
import json
import re
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

LEARNER_FILE = "_learner.json"
SCHEMA_VERSION = 1


# --- the learner profile and the term map ------------------------------------

def _named(word: str) -> bool:
    """A word whose capitals carry meaning: KEYS, TTL, LangGraph, I/O."""
    return len(word) > 1 and any(c.isupper() for c in word[1:])


def norm(term: str) -> str:
    """A term as the checks compare it: case, marks and a plural aside. A
    word written in capitals keeps them, so the command KEYS is not the word
    "key", and EVAL is not "eval"."""
    out = []
    for w in re.sub(r"[^A-Za-z0-9/+.#-]+", " ", term).split():
        if _named(w):
            out.append(w)
            continue
        w = w.lower()
        out.append(w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w)
    return " ".join(out)


def load_learner(base: Path) -> dict:
    """The learner profile at <base>/_learner.json, or an empty one."""
    path = base / LEARNER_FILE
    if not path.is_file():
        return {"schemaVersion": SCHEMA_VERSION, "reader": "", "knownTerms": [], "courses": {}}
    return json.loads(path.read_text())


def learner_known(learner: dict, topic: str) -> set[str]:
    course = (learner.get("courses") or {}).get(topic) or {}
    return {norm(t) for t in [*(learner.get("knownTerms") or []), *(course.get("knownTerms") or [])]}


def phase_key(label: object) -> tuple[int, str]:
    """Order of a phase number or slug tail: 0 < 1 < 2a < 2b < 3."""
    m = re.match(r"(\d+)([a-z]?)", str(label).lower())
    return (int(m.group(1)), m.group(2)) if m else (10**6, str(label))


def phase_label(label: object) -> str:
    """'Phase 2A' for 2a, '02a' or 'phase-02a'."""
    n, part = phase_key(str(label).lower().removeprefix("phase-"))
    return f"Phase {n}{part.upper()}"


def map_terms(entry: dict, kind: str) -> list[str]:
    return [t for t in ((entry.get("terms") or {}).get(kind) or []) if str(t).strip()]


def known_before(course: dict, learner: dict, phase: object) -> set[str]:
    """What the reader has when a phase starts: the profile, plus every term
    the earlier phases of the map introduce."""
    topic = str(course.get("topic") or "")
    known = learner_known(learner, topic)
    for entry in course.get("outline") or []:
        if phase_key(entry.get("phase")) < phase_key(phase):
            known |= {norm(t) for t in map_terms(entry, "introduces")}
    return known


def term_map_findings(course: dict, learner: dict) -> list[str]:
    """Where the course plan uses a term before any phase teaches it."""
    out: list[str] = []
    outline = sorted(course.get("outline") or [], key=lambda e: phase_key(e.get("phase")))
    if not any((e.get("terms") or {}) for e in outline):
        return [("the course has no term map: give each outline entry"
                 ' "terms": {"introduces": [...], "assumes": [...]}')]
    listed = {norm(t) for e in outline for k in ("introduces", "assumes") for t in map_terms(e, k)}
    introduced_all = {norm(t) for e in outline for t in map_terms(e, "introduces")}
    for kind in ("aliases", "shortNames"):
        for other, name in (course.get(kind) or {}).items():
            if norm(other) in listed:
                out.append(f"'{other}' is in {kind} for '{name}', and also listed as a term:"
                           " list only the course's name")
            if norm(name) not in introduced_all:
                out.append(f"{kind}: '{other}' points to '{name}', which no phase introduces")
    first: dict[str, object] = {}
    for entry in outline:
        here = entry.get("phase")
        if not entry.get("terms"):
            out.append(f"{phase_label(here)} has no terms in the map")
            continue
        known = known_before(course, learner, here)
        for term in map_terms(entry, "assumes"):
            if norm(term) not in known:
                later = next((phase_label(e.get("phase")) for e in outline
                              if norm(term) in {norm(t) for t in map_terms(e, "introduces")}), "")
                where = f"{later} introduces it later" if later else "no phase introduces it"
                out.append(f"{phase_label(here)} assumes '{term}', but {where}, and the"
                           " learner profile does not list it")
        for term in map_terms(entry, "introduces"):
            if norm(term) in first:
                out.append(f"'{term}' is introduced twice: {phase_label(first[norm(term)])}"
                           f" and {phase_label(here)}; a later phase reminds, it does not introduce")
            first.setdefault(norm(term), here)
    return out


# --- reading a page in order --------------------------------------------------

_HTML_DROP_RE = re.compile(
    r"(?is)<(script|style|head|pre)\b.*?</\1>|<details\b[^>]*class=\"[^\"]*evidence[^\"]*\"[^>]*>.*?</details>")
_DFN_RE = re.compile(r"(?is)<dfn\b[^>]*>(.*?)</dfn>")
_TAG_RE = re.compile(r"(?s)<[^>]+>")
_MD_FENCE_RE = re.compile(r"(?ms)^(```|~~~).*?^\1[^\n]*$")
_MD_CODE_RE = re.compile(r"`[^`\n]*`")
_MD_DFN_RE = re.compile(r"(?<![*\w])\*(?!\*)([^*\n]{2,60}?)\*(?![*\w])")
_SENTENCE_START_RE = re.compile(r"(^|[.!?:]\s+|\n\s*[-*\d.]*\s*)$")


@dataclass
class Page:
    """A page as the reader meets it: its words in order, where each term is
    defined, which spans are code, and which sit in a collapsed box.

    `prose` is `text` with code blanked to spaces, so offsets match. A term
    written in lower case is looked for in `prose` only: `CLUSTER SHARDS` in
    code is not a use of "shard". A term with capitals, such as a command,
    is looked for in code too. `hidden` spans are inside collapsed "Go
    deeper" or answer boxes, which a reader may never open."""
    text: str
    defs: list[tuple[str, int, bool]] = field(default_factory=list)  # (term, offset, case matters)
    prose: str = ""
    hidden: list[tuple[int, int]] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.prose:
            self.prose = self.text

    def in_hidden(self, offset: int) -> bool:
        return any(a <= offset < b for a, b in self.hidden)


def _case_matters(term: str, before: str) -> bool:
    """'TTL' and 'LangGraph' keep their case. 'List' mid-sentence names a
    thing, so 'a list of steps' is not a use of it. 'Pipelining' at the start
    of a sentence is only capitalised there."""
    if any(c.isupper() for c in term[1:]):
        return True
    return term[:1].isupper() and not _SENTENCE_START_RE.search(before[-6:] or "\n")


_HIDE_OPEN, _HIDE_CLOSE, _CODE_OPEN, _CODE_CLOSE = "\x01", "\x02", "\x03", "\x04"
_DETAILS_TAG_RE = re.compile(r"(?is)<details\b([^>]*)>|</details\s*>")
_COLLAPSED_RE = re.compile(r"""class\s*=\s*["'][^"']*\b(deeper|answer)\b""", re.IGNORECASE)


def _mark_regions(body: str) -> str:
    """Put one-character markers around code and around collapsed boxes, so
    their spans survive the removal of tags."""
    body = re.sub(r"(?is)<code\b[^>]*>", _CODE_OPEN, body)
    body = re.sub(r"(?is)</code\s*>", _CODE_CLOSE, body)
    out: list[str] = []
    pos = 0
    stack: list[bool] = []
    for m in _DETAILS_TAG_RE.finditer(body):
        out.append(body[pos:m.start()])
        if m.group(0).startswith("</"):
            out.append(_HIDE_CLOSE if stack and stack.pop() else " ")
        else:
            hidden = bool(_COLLAPSED_RE.search(m.group(1) or "")) and not any(stack)
            stack.append(hidden)
            out.append(_HIDE_OPEN if hidden else " ")
        pos = m.end()
    out.append(body[pos:])
    return "".join(out)


def _spans(text: str, open_: str, close: str) -> list[tuple[int, int]]:
    out, start = [], None
    for i, c in enumerate(text):
        if c == open_ and start is None:
            start = i
        elif c == close and start is not None:
            out.append((start, i))
            start = None
    return out


def _finish(text: str, defs: list[tuple[str, int, bool]]) -> Page:
    hidden = _spans(text, _HIDE_OPEN, _HIDE_CLOSE)
    code = _spans(text, _CODE_OPEN, _CODE_CLOSE)
    clean = re.sub("[\x01-\x04]", " ", text)
    prose = list(clean)
    for a, b in code:
        prose[a:b] = " " * (b - a)
    return Page(clean, defs, "".join(prose), hidden)


def read_html(page_html: str) -> Page:
    body = re.split(r"(?i)<main\b[^>]*>", page_html, maxsplit=1)[-1]
    body = _mark_regions(_HTML_DROP_RE.sub(" ", body))
    text_parts: list[str] = []
    defs: list[tuple[str, int, bool]] = []
    pos = 0
    length = 0
    for m in _DFN_RE.finditer(body):
        chunk = html_lib.unescape(_TAG_RE.sub(" ", body[pos:m.start()]))
        text_parts.append(chunk)
        length += len(chunk)
        term = html_lib.unescape(_TAG_RE.sub("", m.group(1))).strip()
        before = "".join(text_parts)
        defs.append((term, length, _case_matters(term, before.rstrip(" ") + " ")))
        text_parts.append(" " + term + " ")
        length += len(term) + 2
        pos = m.end()
    text_parts.append(html_lib.unescape(_TAG_RE.sub(" ", body[pos:])))
    return _finish("".join(text_parts), defs)


def read_markdown(md: str) -> Page:
    body = _MD_FENCE_RE.sub(" ", md)
    body = _MD_CODE_RE.sub(lambda m: _CODE_OPEN + m.group(0)[1:-1].replace("*", " ") + _CODE_CLOSE, body)
    defs = [(m.group(1).strip(), m.start(), _case_matters(m.group(1).strip(), body[:m.start()]))
            for m in _MD_DFN_RE.finditer(body)]
    return _finish(body, defs)


def _pattern(term: str, case: bool) -> re.Pattern[str]:
    words = [re.escape(w) for w in term.split()]
    core = r"\s+".join(words)
    flags = 0 if case else re.IGNORECASE
    return re.compile(r"(?<![\w-])" + core + r"(?:s|es)?(?![\w-])", flags)


def _word_at(text: str, offset: int) -> int:
    return len(text[:offset].split())


def _where(page: Page, term: str, case: bool) -> str:
    return page.text if case else page.prose


def order_findings(page: Page, known: Iterable[str] = (), extra_terms: Sequence[str] = (),
                   only: Iterable[str] | None = None,
                   short: dict[str, str] | None = None) -> list[str]:
    """Each term used before the page defines it, with both word positions.

    `known` terms are skipped: the reader has them from earlier phases or
    the profile. `extra_terms` (this phase's terms in the map) must be
    defined somewhere on the page. `only`, when given, limits the marks that
    count as definitions to these terms: in Markdown an italic is also
    emphasis, so only an italic map term is a definition. `short` maps a
    short name to its term ("PEL" to "pending entries list"): the short name
    is defined with the term, and may not be used before it.

    A definition inside a collapsed box counts only for a term the main text
    never uses: a reader who skips the box must still meet the meaning."""
    have = {norm(t) for t in known}
    allowed = {norm(t) for t in only} if only is not None else None
    out: list[str] = []
    by_term: dict[str, list[tuple[str, int, bool]]] = {}
    for term, offset, case in page.defs:
        key = norm(term)
        if len(key) < 2 or key in have or (allowed is not None and key not in allowed):
            continue
        by_term.setdefault(key, []).append((term, offset, case))
    first_def: dict[str, int] = {}
    for key, defs in by_term.items():
        term, _o, case = defs[0]
        pattern = _pattern(term, case)
        text = _where(page, term, case)
        core = [d for d in defs if not page.in_hidden(d[1])]
        core_use = next((m for m in pattern.finditer(text) if not page.in_hidden(m.start())), None)
        if not core and core_use:
            out.append(f"'{term}' is defined only inside a collapsed box, and the main text uses"
                       f" it at word {_word_at(page.text, core_use.start())}: define it in the"
                       " main text, where it is first used")
            continue
        term, offset, case = (core or defs)[0]
        first_def[key] = offset
        m = pattern.search(text, 0, offset)
        if m:
            out.append(f"'{term}' is used at word {_word_at(page.text, m.start())} and defined at"
                       f" word {_word_at(page.text, offset)}: define it where it is first used, or"
                       " say it in plain words until it is defined")
    for name, long in (short or {}).items():
        at = first_def.get(norm(long))
        if at is None:
            continue
        m = _pattern(name, True).search(page.text, 0, max(0, at - 1))
        if m:
            out.append(f"'{name}', the short name of '{long}', is used at word"
                       f" {_word_at(page.text, m.start())}, before '{long}' is defined at word"
                       f" {_word_at(page.text, at)}")
    for term in extra_terms:
        key = norm(term)
        if key not in have and key not in by_term:
            out.append(f"'{term}' is a term this phase introduces in the course map, and the page"
                       " never marks where it is defined")
    return out


def _sentence_span(text: str, offset: int) -> tuple[int, int]:
    start = max(text.rfind(c, 0, offset) for c in ".!?\n") + 1
    ends = [i for i in (text.find(c, offset) for c in ".!?\n") if i >= 0]
    return start, (min(ends) + 1 if ends else len(text))


_QUOTE_RE = re.compile(r'“[^”]{1,600}”|"[^"\n]{1,600}"')


def alias_findings(page: Page, aliases: dict[str, str]) -> list[str]:
    """One name for one idea across the course. `aliases` maps another name
    to the course's name ("thundering herd" to "cache stampede"). The other
    name may appear only in the sentence that defines the course's name. A
    quotation keeps its source's words, so text inside quotation marks is
    never a finding."""
    out: list[str] = []
    defs = {norm(t): o for t, o, _c in page.defs}
    quoted = [(m.start(), m.end()) for m in _QUOTE_RE.finditer(page.text)]
    for other, name in aliases.items():
        at = defs.get(norm(name))
        span = _sentence_span(page.text, at) if at is not None else (-1, -1)
        case = any(c.isupper() for c in other[1:])
        for m in _pattern(other, case).finditer(_where(page, other, case)):
            if not span[0] <= m.start() < span[1] and not any(a <= m.start() < b for a, b in quoted):
                out.append(f"'{other}' is another name for '{name}', at word"
                           f" {_word_at(page.text, m.start())}: use '{name}', the course's name,"
                           " and give the other name once, in the sentence that defines it")
                break
    return out


def link_findings(head: str, tail: str, *, previous: str = "", previous_title: str = "",
                  following: str = "", following_title: str = "") -> list[str]:
    """The phase names the phase before it near its start, and the one after
    it near its end, by its label ('Phase 2') or its title."""
    def names(text: str, label: str, title: str) -> bool:
        low = " ".join(text.lower().split())
        if label and re.search(rf"(?<![\w]){re.escape(label.lower())}(?![\w])", low):
            return True
        return bool(title) and " ".join(title.lower().split()) in low
    out: list[str] = []
    if previous and not names(head, previous, previous_title):
        out.append(f"the opening does not say where {previous} left the reader: name it, say"
                   " what it let the reader do, and the problem this phase starts from")
    if following and not names(tail, following, following_title):
        out.append(f"the ending does not lead to {following}: say what the reader can do now,"
                   " and the question the next phase answers")
    return out


# --- a course folder ----------------------------------------------------------

def _phase_files(folder: Path, topic: str) -> dict[str, Path]:
    out: dict[str, Path] = {}
    for p in sorted(folder.glob(f"{topic}-phase-*.md")):
        tail = p.stem.split("-phase-", 1)[1]
        m = re.match(r"\d+[a-z]?", tail)
        out.setdefault(m.group(0) if m else tail, p)
    return out


def _md_head_tail(md: str) -> tuple[str, str]:
    """The text before the first numbered section, and the text from the last
    numbered section to the end."""
    heads = [m.start() for m in re.finditer(r"(?m)^## \d", md)]
    if not heads:
        return md[:3000], md[-3000:]
    return md[:heads[0]], md[heads[-1]:]


def check_course(folder: Path, only: str | None = None) -> list[str]:
    course = json.loads((folder / "course.json").read_text())
    topic = str(course.get("topic") or folder.name)
    learner = load_learner(folder.parent)
    out = [f"term map: {f}" for f in term_map_findings(course, learner)]
    entries = {str(e.get("phase")): e for e in course.get("outline") or []}
    files = _phase_files(folder, topic)
    order = sorted(files, key=phase_key)
    for i, key in enumerate(order):
        if only is not None and phase_key(key) != phase_key(only):
            continue
        entry: dict[str, Any] = next((e for k, e in entries.items() if phase_key(k) == phase_key(key)), {})
        md = files[key].read_text()
        known = known_before(course, learner, key)
        every = [t for e in course.get("outline") or [] for k in ("introduces", "assumes")
                 for t in map_terms(e, k)]
        page = read_markdown(md)
        found = order_findings(page, known, map_terms(entry, "introduces"), only=every,
                               short=course.get("shortNames") or {})
        found += alias_findings(page, course.get("aliases") or {})
        head, tail = _md_head_tail(md)
        prev = order[i - 1] if i else ""
        nxt = order[i + 1] if i + 1 < len(order) else ""
        prev_e: dict[str, Any] = next((e for k, e in entries.items() if prev and phase_key(k) == phase_key(prev)), {})
        next_e: dict[str, Any] = next((e for k, e in entries.items() if nxt and phase_key(k) == phase_key(nxt)), {})
        found += link_findings(head, tail,
                               previous=phase_label(prev) if prev else "",
                               previous_title=str(prev_e.get("title") or ""),
                               following=phase_label(nxt) if nxt else "",
                               following_title=str(next_e.get("title") or ""))
        out += [f"{phase_label(key)}: {f}" for f in found]
    return out


# --- self-test ----------------------------------------------------------------

def self_test() -> int:
    import tempfile

    checks: list[tuple[str, bool]] = []
    page = read_html('<main><p>Set a TTL on the key. Here is a list of steps. We use'
                     ' pipelining.</p><pre>Pipelining in code</pre><p>A <dfn>TTL</dfn> is the'
                     ' time to live.</p><p>A <dfn>List</dfn> keeps order.</p><p><dfn>Pipelining</dfn>'
                     ' sends many commands.</p></main>')
    found = order_findings(page)
    checks.append(("finds a term used before its definition", any("'TTL'" in f for f in found)))
    checks.append(("an everyday 'list' is not a use of 'List'", not any("'List'" in f for f in found)))
    checks.append(("a capital at a sentence start does not make case matter",
                   any("'Pipelining'" in f for f in found)))
    checks.append(("a known term is skipped",
                   order_findings(page, known=["TTL", "pipelining"]) == []))
    checks.append(("a command in capitals is not the word", norm("KEYS") != norm("key")
                   and norm("EVAL") != norm("eval") and norm("Replicas") == norm("replica")))
    checks.append(("a map term with no definition is named",
                   any("'eviction policy'" in f for f in order_findings(page, extra_terms=["eviction policy"]))))
    md = read_markdown("Use a *cache* here.\n\nA *cache* is a copy.\n\n```\ncache\n```\n")
    checks.append(("markdown: *term* marks the definition", bool(md.defs) and md.defs[0][0] == "cache"))
    late = read_markdown("Every replica lags. It is not fast.\n\nA *replica* is a copy, *not* a backup.")
    checks.append(("markdown: use before definition", len(order_findings(late)) == 2))
    checks.append(("markdown: an emphasis italic is not a definition",
                   len(order_findings(late, only=["replica"])) == 1))

    coded = read_html('<main><p>Run <code>CLUSTER SHARDS</code> and <code>SET k v</code>.</p>'
                      '<p>A <dfn>shard</dfn> is a part. <dfn>SET</dfn> stores a value.</p></main>')
    cf = order_findings(coded)
    checks.append(("code: a lowercase term in code is not a use", not any("'shard'" in f for f in cf)))
    checks.append(("code: a command in code is a use", any("'SET'" in f for f in cf)))
    boxed = read_html('<main><p>The fork is slow.</p><details class="answer deeper"><summary>Go'
                      ' deeper</summary><p>A <dfn>fork</dfn> copies the process.</p></details>'
                      '<details class="answer deeper"><p>A <dfn>COW page</dfn> is shared.</p></details>'
                      '<details class="predict"><summary>Predict</summary><p>A <dfn>replica</dfn>'
                      ' lags.</p></details><p>Each replica lags.</p></main>')
    bf = order_findings(boxed)
    checks.append(("collapsed: a box definition for a main-text term is refused",
                   any("'fork' is defined only inside a collapsed box" in f for f in bf)))
    checks.append(("collapsed: a term used only in its box is fine", not any("COW page" in f for f in bf)))
    checks.append(("collapsed: a predict box is not collapsed for this rule", not any("'replica'" in f for f in bf)))
    sp = read_html('<main><p>Read the PEL first.</p><p>The <dfn>pending entries list</dfn>, the PEL,'
                   ' holds entries. The PEL grows.</p></main>')
    sf = order_findings(sp, short={"PEL": "pending entries list"})
    checks.append(("short name: used before its term is defined", len(sf) == 1 and "'PEL'" in sf[0]))
    al = read_html('<main><p>A <dfn>cache stampede</dfn>, also called a thundering herd, hits the'
                   ' database.</p><p>Each cache stampede costs time.</p></main>')
    checks.append(("alias: allowed in the defining sentence",
                   alias_findings(al, {"thundering herd": "cache stampede"}) == []))
    al2 = read_html('<main><p>A <dfn>cache stampede</dfn> hits the database. A thundering herd'
                    ' again.</p></main>')
    checks.append(("alias: refused elsewhere", len(alias_findings(al2, {"thundering herd": "cache stampede"})) == 1))
    al3 = read_html('<main><p>A <dfn>cache stampede</dfn> hits the database. Facebook calls it'
                    ' “particularly susceptible to thundering herds”.</p></main>')
    checks.append(("alias: a quotation keeps its words", alias_findings(al3, {"thundering herd": "cache stampede"}) == []))
    amap = {"topic": "t", "aliases": {"full sync": "full resync"}, "outline": [
        {"phase": 0, "terms": {"introduces": ["full resync", "full sync"], "assumes": []}}]}
    checks.append(("map: an alias listed as a term", any("'full sync' is in aliases" in f
                                                         for f in term_map_findings(amap, {}))))

    course = {"topic": "t", "outline": [
        {"phase": 0, "title": "Why", "terms": {"introduces": ["cache", "key"], "assumes": []}},
        {"phase": 1, "title": "Types", "terms": {"introduces": ["hash"], "assumes": ["key", "replica"]}},
        {"phase": 2, "title": "HA", "terms": {"introduces": ["replica", "key"], "assumes": []}},
    ]}
    learner: dict[str, Any] = {"knownTerms": ["HTTP"], "courses": {"t": {"knownTerms": []}}}
    fm = term_map_findings(course, learner)
    checks.append(("map: an assumed term taught only later", any("'replica'" in f and "Phase 2" in f for f in fm)))
    checks.append(("map: a term introduced twice", any("'key' is introduced twice" in f for f in fm)))
    learner["courses"]["t"]["knownTerms"] = ["replica"]
    checks.append(("map: the profile covers a term",
                   not any("assumes 'replica'" in f for f in term_map_findings(course, learner))))
    checks.append(("map: no map at all is one finding",
                   len(term_map_findings({"outline": [{"phase": 0}]}, {})) == 1))
    checks.append(("labels", phase_label("02a") == "Phase 2A" and phase_label(3) == "Phase 3"))
    checks.append(("phase order", sorted(["2b", "10", "2a", "0"], key=phase_key) == ["0", "2a", "2b", "10"]))
    lf = link_findings("Phase 1 showed the types.", "Next, Phase 3 asks how.",
                       previous="Phase 1", following="Phase 3")
    checks.append(("link: names both phases", lf == []))
    lf = link_findings("We start.", "The end.", previous="Phase 1", following="Phase 3",
                       following_title="Replication")
    checks.append(("link: missing both", len(lf) == 2))
    checks.append(("link: the title is enough",
                   link_findings("", "Replication comes next.", following="Phase 3",
                                 following_title="Replication") == []))

    d = Path(tempfile.mkdtemp())
    (d / "t").mkdir()
    (d / LEARNER_FILE).write_text(json.dumps({"knownTerms": [], "courses": {}}))
    (d / "t" / "course.json").write_text(json.dumps({"topic": "t", "outline": [
        {"phase": 0, "title": "Why", "terms": {"introduces": ["cache"], "assumes": []}},
        {"phase": 1, "title": "Types", "terms": {"introduces": ["hash"], "assumes": ["cache"]}}]}))
    (d / "t" / "t-phase-00-why.md").write_text("# Phase 0\n\nA *cache* is a copy.\n\n## 0.1 x\n\nNext is Phase 1.\n")
    (d / "t" / "t-phase-01-types.md").write_text("# Phase 1\n\nAfter Phase 0, a cache.\n\n## 1.1 x\n\nA hash here. A *hash* maps fields.\n")
    res = check_course(d / "t")
    checks.append(("course: finds the late definition in Phase 1", any("Phase 1:" in f and "'hash'" in f for f in res)))
    checks.append(("course: Phase 0 is clean", not any(f.startswith("Phase 0:") for f in res)))
    checks.append(("course: one phase only", all(f.startswith(("Phase 1:", "term map:"))
                                                 for f in check_course(d / "t", only="1"))))

    bad = 0
    print("term_order self-test\n")
    for label, ok in checks:
        print(f"  [{'ok ' if ok else 'BAD'}] {label}")
        bad += not ok
    print("\nall checks passed" if not bad else f"\n{bad} check(s) failed")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--course", type=Path, help="a course folder that holds course.json")
    ap.add_argument("--phase", help="check only this phase, such as 3 or 2a")
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        return self_test()
    if not args.course:
        ap.error("--course is required")
    found = check_course(args.course, args.phase)
    for f in found:
        print(f)
    if not found:
        print("term map: ok" if args.phase is None else f"{phase_label(args.phase)}: 0 findings")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
