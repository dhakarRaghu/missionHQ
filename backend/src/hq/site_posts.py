"""Posts for his site, checked the way a stranger reads them.

A lesson is written for him: he will read all of it because it is his course.
A post is read by someone who owes him nothing. That reader sees a title,
gives the first screen a few seconds, scans the headings, and leaves when a
paragraph gives nothing. Most of a page goes unread, so a post that keeps its
point for the end is a post whose point nobody reaches.

Two things live here, and neither asks a model anything:

- ``reader_problems``: what would make that reader leave, measured. Sentence
  length, the share of very short and very long sentences, how far apart the
  headings are, whether the result is stated first, whether the post says
  where it stops working. The targets were measured from essays he reads and
  finishes, not chosen by taste.
- ``shortlist``: he reads far more than he publishes, so a week's two posts
  are picked from what he read. Candidates are scored on what makes a post
  worth a stranger's time: he has his own result for it, he wrote down what
  he did, he marked it, readers look for the topic now (``topics.md``), it
  was hard for him, it is recent.

``python -m hq.site_posts check <file> [--shape lab]`` measures a draft.
``python -m hq.site_posts shortlist`` prints this week's five.
``python -m hq.site_posts field-note <name>`` starts a field note: what he
did and the number he got, the material a post can say "I" from.
"""

from __future__ import annotations

import re
import statistics
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from hq.config import settings

# --- shapes ----------------------------------------------------------------------


@dataclass(frozen=True)
class Shape:
    """One kind of post: where it lands on the site and what it must carry."""

    name: str
    section: str                 # the folder under content/ on his site
    words: tuple[int, int]
    in_short: bool               # the result stated in the first lines
    headings: bool
    limits: bool                 # a section that says where it stops working
    evidence: bool               # a table or a code block: the thing measured
    numbers_per_1000: float      # at least this many, each with its condition
    figures: int = 0             # diagrams, charts or calculators it must carry


SHAPES: Mapping[str, Shape] = {
    # The week's post from something he read: what it says, what he makes of
    # it, where it stops. Short, because extra words get almost no extra time.
    "brief": Shape("brief", "blog", (700, 1200), True, True, True, False, 5.0),
    # He ran something and has a number. The easiest post to make his own.
    "lab": Shape("lab", "blog", (700, 1400), True, True, True, True, 5.0),
    # The main post on his blog: one topic taught from first principles, the
    # essay a reader bookmarks. Long, because the reader came to learn it
    # completely; its first two paragraphs do the work of an opening block.
    "explainer": Shape("explainer", "blog", (1500, 3500), False, True, True, True, 5.0,
                       figures=1),
    # One idea and the one line to keep. No headings: it is read in a minute.
    "note": Shape("note", "notes", (100, 300), False, False, False, False, 0.0),
    # A paper read closely: the claim, the measurement, where it stops.
    "paper": Shape("paper", "papershelf", (500, 1400), True, True, True, False, 3.0),
}
DEFAULT_SHAPE = "brief"

# What the console and the lesson pipeline call a section, and the folder it
# becomes. His site renamed "writing" to "blog"; callers keep their word.
SITE_FOLDER: Mapping[str, str] = {
    "writing": "blog", "blog": "blog", "notes": "notes", "papershelf": "papershelf",
}
# A blog post is an explainer unless the task names another shape: a
# retelling of one article is what made his first posts read like anyone's.
SHAPE_OF_SECTION: Mapping[str, str] = {
    "writing": "explainer", "blog": "explainer", "notes": "note", "papershelf": "paper",
}

# --- targets, measured -----------------------------------------------------------
#
# From eight essays by an author he reads to the end. In seven the median
# sentence ran 12 to 17 words and 4 to 8% of sentences had five words or
# fewer; no stretch ran past 305 words without a heading; the seven technical
# ones carried 7 to 27 numbers in a thousand words. The bands below are those
# with room on each side. Run against the same eight, the rhythm checks pass
# five. Two of the three they refuse have 16% and 38% of sentences at thirty
# words or more, and he reads English as a second language, so that line
# stays. The third is an opinion piece with 16% very short sentences.
SENTENCE_MEDIAN = (10, 19)
SHORT_WORDS = 5
SHORT_SHARE_MAX = 0.14          # a run of short sentences reads as loose facts
LONG_WORDS = 30
LONG_SHARE_MAX = 0.15           # a long sentence hides a second one
WORDS_PER_HEADING_MAX = 260
STRETCH_MAX = 420               # words in a row with no heading to land on
IN_SHORT_WORDS = (20, 80)
IN_SHORT_SENTENCES = 4          # the result, not a second introduction
# A search result and a shared card both cut what runs past these.
TITLE_CHARS = 70
SUMMARY_CHARS = 160
# The categories his site filters by. The site keeps the same list in
# src/lib/site.ts; a post names one so the filter can find it.
CATEGORIES = ("inference", "retrieval", "agents", "evals", "backend", "career")
FIRST_PARAGRAPH_MAX = 90
MIN_SENTENCES = 6               # below this the shares say nothing

# The opening block, in the ways a writer reasonably marks it: bold with
# either mark, the colon inside or outside it, a quote mark in front.
IN_SHORT_RE = re.compile(
    r"^(?:>\s*)?(?:(?:\*\*|__)In short[:.]?(?:\*\*|__)[:.]?|In short:)[ \t]*(.*)",
    re.IGNORECASE | re.DOTALL)
# A section of its own, found by its heading: a word like "cannot" somewhere
# in a heading ("A reranker cannot recover...") is a claim, not a reader
# being told where the result ends.
_LIMITS_RE = re.compile(
    r"^limits?$|^caveats?$|\blimitations?\b|\bthe limits\b|when not to|"
    r"(when|where) (it|this|that) (fails|breaks|stops|does(n't| not) (hold|work|apply|pay))|"
    r"stops? (working|holding|paying)|"
    r"what (it|this|i) (does(n't| not)|did(n't| not)|cannot|can't)"
    r" (tell|check|test|measure|cover|show)|"
    r"what .{1,40} (cannot|can't|does(n't| not)) do\b|"
    r"did(n't| not) (check|test|measure)|not (checked|measured|tested)|"
    r"the wrong tool|falls? short",
    re.IGNORECASE)
# A heading is what a scanning reader reads instead of the section. These
# name a position in the post, not what the section says.
GENERIC_HEADINGS = frozenset({
    "introduction", "intro", "overview", "background", "conclusion", "conclusions",
    "final thoughts", "closing thoughts", "wrapping up", "summary", "outro",
    "takeaway", "the takeaway", "takeaways", "key takeaways", "tl;dr", "tldr",
    "the situation", "situation", "the setup", "setup", "context", "the problem",
})
# Openers that spend the reader's first seconds on the post, not the subject.
_META_OPENERS = (
    "in this post", "in this article", "in this blog", "this post", "this article",
    "today we", "today i", "welcome", "have you ever",
)
_LETS_RE = re.compile(r"^let['’]?s\s+[a-z]")     # "Let's look", not "Let's Encrypt"
# Phrases a reader has learned to skip.
STOCK_PHRASES = (
    "delve", "in today's", "game changer", "dive into", "deep dive",
    "unleash", "tapestry", "testament to", "it is worth noting", "it's worth noting",
    "needless to say", "at the end of the day", "the bottom line", "ever-evolving",
    "fast-paced", "in conclusion", "without further ado", "buckle up",
    # Figures of speech. He reads English as a second language, and a picture
    # has to be translated before the sentence can be read.
    "vanity metric", "all over again", "silver bullet", "low-hanging fruit",
    "double-edged sword", "tip of the iceberg", "under the hood", "heavy lifting",
    "boils down to", "rabbit hole", "garbage", "tripwire", "judgement call",
    "judgment call", "pays out", "pays off",
)
# Words that confused him when others used them, each with the plain thing to
# say instead. Common in engineering writing (five of the eight reference
# essays use one), which is why the message carries the replacement: the
# rewrite is one phrase, and the sentence reads the same to every reader.
# His list; edit it here.
PLAIN_WORDS: Mapping[str, str] = {
    "leverage": "use",
    "bottleneck": "the slowest step",
    "compounds": "grows with each step",
    "flywheel": "a loop that strengthens itself",
    "on-ramp": "a way to start",
    "plumbing": "the connecting code",
    "altitude": "level of detail",
    "canon": "the standard set",
}
ASKS = (
    "what do you think", "let me know", "drop a comment", "comment below", "thoughts?",
    "follow for more", "like and share", "repost if", "dm me", "subscribe to my",
    "subscribe for",
)

# A fence may be indented (inside a list) and may use more than three marks.
_FENCE_RE = re.compile(r"^[ \t]*(`{3,}|~{3,})[^\n]*\n.*?^[ \t]*\1[ \t]*$",
                       re.DOTALL | re.MULTILINE)
# A fence that is never closed runs to the end, as a renderer shows it.
_OPEN_FENCE_RE = re.compile(r"^[ \t]*(?:`{3,}|~{3,})[^\n]*\n.*\Z", re.DOTALL | re.MULTILINE)
_FRONT_RE = re.compile(r"\A---\n.*?\n---\n", re.DOTALL)
_HEADING_RE = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")
_TITLE_LINE_RE = re.compile(r"\A\s*#\s+[^\n]*\n")
_TABLE_LINE_RE = re.compile(r"^\s*\|.*\|\s*$")
_LIST_MARK_RE = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+")
_LINK_RE = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
_INLINE_CODE_RE = re.compile(r"`[^`\n]*`")
# Where a sentence may end: the marks, any closing quote or bracket, a space.
_SENTENCE_END_RE = re.compile(r"[.!?]+[\"'’)\]]*\s+")
# Short forms whose period ends nothing.
_ABBREVIATIONS = frozenset({
    "e.g", "i.e", "vs", "etc", "al", "fig", "dr", "mr", "mrs", "ms", "no", "approx", "cf",
    "inc", "st", "eq", "sec",
})
# A number a reader can act on. Not the digit in a name ("gpt-4", "H100").
_NUMBER_RE = re.compile(
    r"(?<![\w.])(?<![A-Za-z]-)\d[\d,]*(?:\.\d+)?(?:%|x|ms|s|k|K|M|GB|MB)?(?![\w])")
_WORD_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9'’./%-]*")


def _pattern(label: str) -> re.Pattern[str]:
    """A phrase and its plain inflections: "delve" finds "delving", "deep
    dive" finds "deep-dives". Whole words only, so "canon" is not "canonical"."""
    words = re.split(r"[ -]", label.casefold())
    last = words[-1]
    if last.endswith("e") and len(last) > 3:
        tail = re.escape(last[:-1]) + r"(?:e|es|ed|ing)"
    else:
        tail = re.escape(last) + r"(?:s|es|ed|ing)?"
    head = r"[- ]".join(re.escape(w) for w in words[:-1])
    body = f"{head}[- ]{tail}" if head else tail
    return re.compile(rf"(?<![a-z]){body}(?![a-z])")


_STOCK_PATTERNS = {label: _pattern(label) for label in STOCK_PHRASES}
_PLAIN_PATTERNS = {word: _pattern(word) for word in PLAIN_WORDS}
_PLAIN_PATTERNS["on-ramp"] = re.compile(r"(?<![a-z])on[- ]?ramps?(?![a-z])")


def found_in(text: str, patterns: Mapping[str, re.Pattern[str]]) -> tuple[str, ...]:
    lowered = text.casefold().replace("’", "'")
    return tuple(label for label, pattern in patterns.items() if pattern.search(lowered))


# --- measuring -------------------------------------------------------------------


@dataclass(frozen=True)
class Measure:
    """What one draft looks like to a reader, as numbers."""

    words: int                   # prose, list items and the opening block
    sentences: int
    sentence_median: float
    short_share: float
    long_share: float
    headings: tuple[str, ...]
    longest_stretch: int         # most words between two headings
    numbers_per_1000: float
    code_blocks: int
    tables: int
    in_short: str                # the text of the opening block, "" when absent
    first_paragraph: str
    last_paragraph: str
    has_limits: bool
    em_dashes: int
    title_line: bool = False     # it starts with "# Title", which the site prints itself
    stock: tuple[str, ...] = field(default=())
    unclear: tuple[str, ...] = field(default=())   # his avoid list, found

    def line(self) -> str:
        return (f"{self.words} words, {self.sentences} sentences, median "
                f"{self.sentence_median:g} words, {self.short_share:.0%} short, "
                f"{self.long_share:.0%} long, {len(self.headings)} headings, longest "
                f"stretch {self.longest_stretch} words, "
                f"{self.numbers_per_1000:.1f} numbers per 1,000 words")


def _words(text: str) -> int:
    return len(_WORD_RE.findall(text))


def _a(name: str) -> str:
    return f"an {name}" if name[:1] in "aeiou" else f"a {name}"


def _plain(line: str) -> str:
    """One prose line as a reader sees it: link text, no marks, no code."""
    line = _LINK_RE.sub(r"\1", line)
    line = _INLINE_CODE_RE.sub(" code ", line)
    line = _LIST_MARK_RE.sub("", line)
    return re.sub(r"[*_>#]+", " ", line).strip()


def _blocks(body: str) -> tuple[list[str], list[str]]:
    """Prose paragraphs and list items, each in order. Headings and tables
    are neither. A list item is not a sentence of the prose: eight short
    bullets are a list, not eight loose facts."""
    paragraphs: list[str] = []
    items: list[str] = []
    block: list[str] = []

    def close() -> None:
        if block:
            paragraphs.append(" ".join(block))
            block.clear()

    for raw in body.splitlines():
        line = raw.rstrip()
        if not line.strip() or _HEADING_RE.match(line) or _TABLE_LINE_RE.match(line):
            close()
            continue
        text = _plain(line)
        if not text:
            continue
        if _LIST_MARK_RE.match(line):
            close()
            items.append(text)
        else:
            block.append(text)
    close()
    return paragraphs, items


def sentences_of(text: str) -> list[str]:
    """Split prose into sentences. A period after a short form ("e.g.",
    "vs.") ends nothing, and a sentence may start lowercase ("vLLM is")."""
    out: list[str] = []
    start = 0
    for found in _SENTENCE_END_RE.finditer(text):
        before = text[start:found.start()]
        last = re.findall(r"[A-Za-z.]+$", before)
        token = last[0].casefold().strip(".") if last else ""
        following = text[found.end():found.end() + 1]
        if token in _ABBREVIATIONS and found.group().lstrip().startswith("."):
            continue
        if following.islower() and len(token) <= 2:
            continue
        piece = text[start:found.end()].strip()
        if piece:
            out.append(piece)
        start = found.end()
    rest = text[start:].strip()
    if rest:
        out.append(rest)
    return [s for s in out if _words(s) >= 1]


def measure(markdown: str) -> Measure:
    """Measure a draft. Frontmatter is dropped; code and tables are counted
    and then left out of the prose, as a reader skips them while reading.
    Words are prose, list items and the opening block: headings, tables and
    code are not counted."""
    text = markdown.replace("\r\n", "\n").lstrip()
    text = _FRONT_RE.sub("", text, count=1).lstrip()
    title_line = bool(_TITLE_LINE_RE.match(text + "\n"))
    if title_line:
        text = _TITLE_LINE_RE.sub("", text + "\n", count=1)
    code_blocks = len(_FENCE_RE.findall(text))
    body = _FENCE_RE.sub("\n", text)
    if _OPEN_FENCE_RE.search(body):
        code_blocks += 1
        body = _OPEN_FENCE_RE.sub("\n", body)

    lines = body.splitlines()
    table_lines = [line for line in lines if _TABLE_LINE_RE.match(line)]
    tables = sum(
        1 for i, line in enumerate(lines)
        if _TABLE_LINE_RE.match(line) and (i == 0 or not _TABLE_LINE_RE.match(lines[i - 1]))
    )

    headings: list[str] = []
    stretch = longest = 0
    for line in lines:
        found = _HEADING_RE.match(line)
        if found:
            headings.append(_plain(found.group(1)))
            longest = max(longest, stretch)
            stretch = 0
        elif not _TABLE_LINE_RE.match(line):
            stretch += _words(_plain(line))
    longest = max(longest, stretch)

    paragraphs, items = _blocks(body)
    in_short = ""
    raw = [block.strip() for block in re.split(r"\n\s*\n", body) if block.strip()]
    found_short = IN_SHORT_RE.match(raw[0]) if raw else None
    if found_short:
        rest = found_short.group(1).strip()
        # The label alone on its line, the text in the paragraph under it.
        if not rest and len(raw) > 1 and not _HEADING_RE.match(raw[1]):
            rest, paragraphs = raw[1], paragraphs[1:]
        in_short = _plain(rest.replace("\n", " "))
        paragraphs = paragraphs[1:]

    prose = " ".join(paragraphs)
    lengths = [_words(s) for s in sentences_of(prose)]
    count = len(lengths)
    total = sum(lengths) + sum(_words(i) for i in items) + _words(in_short)
    everything = " ".join([in_short, prose, *items, *headings])
    numbered = " ".join([in_short, prose, *items, *(_plain(t) for t in table_lines)])
    return Measure(
        words=total,
        sentences=count,
        sentence_median=float(statistics.median(lengths)) if lengths else 0.0,
        short_share=sum(1 for n in lengths if n <= SHORT_WORDS) / count if count else 0.0,
        long_share=sum(1 for n in lengths if n >= LONG_WORDS) / count if count else 0.0,
        headings=tuple(headings),
        longest_stretch=longest,
        numbers_per_1000=1000 * len(_NUMBER_RE.findall(numbered)) / total if total else 0.0,
        code_blocks=code_blocks,
        tables=tables,
        in_short=in_short,
        first_paragraph=paragraphs[0] if paragraphs else "",
        last_paragraph=paragraphs[-1] if paragraphs else "",
        has_limits=any(_LIMITS_RE.search(h.replace("’", "'").strip(" .:")) for h in headings),
        em_dashes=text.count("—"),
        title_line=title_line,
        stock=found_in(everything, _STOCK_PATTERNS),
        unclear=found_in(everything, _PLAIN_PATTERNS),
    )


# --- figures -------------------------------------------------------------------
#
# His site renders two kinds of block as figures: ```mermaid for a flow
# diagram, and ```widget <name> with JSON props for a chart or a calculator.
# A bad block shows as raw text or breaks the page build, so both are checked
# here before a draft is saved.

WIDGETS = ("chart", "kv-calculator")
CHART_TYPES = ("bar", "line", "stack")
_FIGURE_BLOCK_RE = re.compile(r"^```(mermaid|widget)[ \t]*([\w-]*)[ \t]*\n(.*?)^```[ \t]*$",
                              re.MULTILINE | re.DOTALL)


def figures_in(markdown: str) -> list[tuple[str, str, str]]:
    """Each figure block as (kind, widget name, body)."""
    return [(m.group(1), m.group(2), m.group(3)) for m in _FIGURE_BLOCK_RE.finditer(markdown)]


def figure_problems(markdown: str) -> list[str]:
    """What would break a figure on his site, or []."""
    import json

    problems: list[str] = []
    for kind, name, body in figures_in(markdown):
        if kind == "mermaid":
            first = next((ln.strip() for ln in body.splitlines()
                          if ln.strip() and not ln.strip().startswith("%%")), "")
            if not first.startswith(("flowchart", "graph", "sequenceDiagram", "stateDiagram")):
                problems.append(f"a mermaid block starts with {first[:30]!r}; use it for a"
                                " flowchart or a sequence diagram, and a widget chart for numbers")
            continue
        if name not in WIDGETS:
            problems.append(f"widget {name!r} does not exist; use one of {', '.join(WIDGETS)}")
            continue
        try:
            props = json.loads(body or "{}")
        except ValueError:
            problems.append(f"the props of widget {name} are not valid JSON")
            continue
        if name == "chart":
            if props.get("type", "bar") not in CHART_TYPES:
                problems.append(f"chart type must be one of {', '.join(CHART_TYPES)}")
            labels = props.get("labels") or []
            series = props.get("series") or []
            if not labels or not series:
                problems.append("a chart needs labels and at least one series")
            for one in series:
                values = one.get("values") or []
                if len(values) != len(labels) or not all(
                        isinstance(v, int | float) for v in values):
                    problems.append(f"chart series {one.get('name', '')!r} needs one number"
                                    f" per label: {len(labels)} labels, {len(values)} values")
    return problems


def shape_for(section: str, shape: str = "") -> Shape:
    """The shape a post is held to: the one named, or the section's own."""
    name = (shape or SHAPE_OF_SECTION.get(section, DEFAULT_SHAPE)).strip().lower()
    if name not in SHAPES:
        raise ValueError(f"shape must be one of {', '.join(SHAPES)}")
    return SHAPES[name]


def reader_problems(markdown: str, shape: str = DEFAULT_SHAPE) -> list[str]:
    """Why a stranger would leave this post, in plain words, or [].

    Every line says what was measured and what to do about it, because the
    writer reads it as the reason a draft came back."""
    rule = SHAPES[shape] if shape in SHAPES else shape_for("", shape)
    m = measure(markdown)
    problems: list[str] = []

    if m.title_line:
        problems.append(
            "it starts with a title line; the site prints the title. Remove the line and"
            " start with the opening block")

    low, high = rule.words
    if m.words < low:
        problems.append(
            f"{m.words} words of prose; {_a(rule.name)} post runs {low} to {high}, not"
            " counting headings, tables and code. It has lost the substance: put back the"
            " numbers, the conditions and the steps")
    elif m.words > high:
        problems.append(
            f"{m.words} words of prose; {_a(rule.name)} post runs {low} to {high}, not"
            " counting headings, tables and code. A reader gives extra words almost no extra"
            " time: cut what repeats, keep every number")

    if rule.in_short:
        if not m.in_short:
            problems.append(
                'it does not open with the result. Start with one paragraph "**In short:**'
                ' ..." that states the finding and its number, so a reader who stops there'
                " still leaves with it")
        else:
            short_low, short_high = IN_SHORT_WORDS
            size = _words(m.in_short)
            count = len(sentences_of(m.in_short))
            if not short_low <= size <= short_high:
                problems.append(
                    f'the "In short" block is {size} words; keep it {short_low} to'
                    f" {short_high}, two or three sentences"
                    + (f". Remove a whole sentence, at least {size - short_high + 15} words:"
                       " a model that trims a word at a time comes back over the limit"
                       if size > short_high else ""))
            elif count > IN_SHORT_SENTENCES:
                problems.append(
                    f'the "In short" block has {count} sentences; state the one result in'
                    f" at most {IN_SHORT_SENTENCES}, and leave the rest to the sections")

    first = m.first_paragraph
    if first:
        opener = first.casefold()
        meta = (next((p for p in _META_OPENERS if opener.startswith(p)), "")
                or ("let's" if _LETS_RE.match(first[:1].casefold() + first[1:]) else ""))
        if meta:
            problems.append(
                f'it opens with "{first[:40].strip()}...": that talks about the post. Open on'
                " the situation the reader is in, then what goes wrong in it")
        if first.rstrip().endswith("?") and len(sentences_of(first)) == 1:
            problems.append("it opens on a question alone; state the situation instead")
        # A note is one piece; its first paragraph may be all of it.
        if rule.in_short and _words(first) > FIRST_PARAGRAPH_MAX:
            problems.append(
                f'the paragraph under the "In short" block, which starts'
                f' "{first[:40].strip()}...", is {_words(first)} words; a reader decides to'
                f" stay in a few seconds, keep it under {FIRST_PARAGRAPH_MAX}. Remove a"
                f" whole sentence, at least {_words(first) - FIRST_PARAGRAPH_MAX + 15} words,"
                " and keep only where the reader is and what goes wrong there")
        about = next((s for s in sentences_of(first)
                      if re.match(r"(?:this|the) (?:post|article|piece|blog) (?:is|covers|"
                                  r"explains|shows|looks|walks)", s.casefold())), "")
        if about and not meta:
            problems.append(
                f'"{about[:60].strip()}..." talks about the post. The reader is already'
                " reading it: say the thing itself")

    if m.sentences >= MIN_SENTENCES:
        med_low, med_high = SENTENCE_MEDIAN
        if m.sentence_median > med_high:
            problems.append(
                f"the median sentence is {m.sentence_median:g} words; keep it {med_low} to"
                f" {med_high}. Split the long ones where the second idea starts")
        elif m.sentence_median < med_low:
            problems.append(
                f"the median sentence is {m.sentence_median:g} words; keep it {med_low} to"
                f" {med_high}. Join a claim to its reason with because, so or but")
        if m.short_share > SHORT_SHARE_MAX:
            problems.append(
                f"{m.short_share:.0%} of sentences have {SHORT_WORDS} words or fewer; short"
                " sentences in a row read as loose facts. Keep the reason inside the sentence")
        if m.long_share > LONG_SHARE_MAX:
            problems.append(
                f"{m.long_share:.0%} of sentences have {LONG_WORDS} words or more; split them")

    if rule.headings:
        if not m.headings:
            problems.append(
                "no headings; a reader scans them first. Add one for each section, written"
                " as what the section says")
        else:
            per = m.words / len(m.headings)
            if per > WORDS_PER_HEADING_MAX:
                problems.append(
                    f"one heading every {per:.0f} words; a reader needs one at least every"
                    f" {WORDS_PER_HEADING_MAX}. Split the long sections")
            if m.longest_stretch > STRETCH_MAX:
                problems.append(
                    f"{m.longest_stretch} words run without a heading; keep a stretch under"
                    f" {STRETCH_MAX}")
            generic = [h for h in m.headings if h.casefold().strip(" .:") in GENERIC_HEADINGS]
            if generic:
                problems.append(
                    "these headings name a place in the post, not what the section says: "
                    + ", ".join(f'"{h}"' for h in generic)
                    + ". Write each as the claim the section makes")
    elif m.headings:
        problems.append(f"{_a(rule.name)} has no headings; it is read in a minute, in one piece")

    if rule.limits and not m.has_limits:
        problems.append(
            "no section says where this stops working. Add one, with a heading that says"
            " so: the conditions under which the result does not hold, and what was not"
            " checked")
    shown = figures_in(markdown)
    if len(shown) < rule.figures:
        problems.append(
            f"no figure; {_a(rule.name)} post needs at least {rule.figures}. Draw the"
            " mechanism as a ```mermaid flowchart, or show the numbers as a ```widget chart")
    problems += figure_problems(markdown)
    if rule.evidence and not (m.code_blocks or m.tables or shown):
        problems.append(
            "no table and no code block; show the thing measured: the result table or the"
            " command that produced the number")
    if rule.numbers_per_1000 and m.numbers_per_1000 < rule.numbers_per_1000:
        problems.append(
            f"{m.numbers_per_1000:.1f} numbers per 1,000 words; at least"
            f" {rule.numbers_per_1000:g}. Replace words like faster or most with the number"
            " and the condition it was measured under")

    if rule.in_short and re.match(r"(?:I|We|My|Our)\b", m.in_short):
        problems.append(
            'the "In short" block starts with the author. Start it with the finding and'
            " its number; a reader who stops there came for the result")
    if m.em_dashes:
        problems.append(f"{m.em_dashes} em dash(es); he uses none, split the sentence")
    if m.stock:
        problems.append(
            "phrases a reader skips: "
            + ", ".join(f'"{p}"' for p in m.stock) + ". Say the plain thing")
    if m.unclear:
        problems.append(
            "words he asked to avoid: "
            + ", ".join(f'"{w}" (say "{PLAIN_WORDS[w]}")' for w in m.unclear))
    closing = m.last_paragraph.casefold()
    asked = next((a for a in ASKS
                  if re.search(rf"(?<![a-z]){re.escape(a)}(?![a-z])", closing)), "")
    if asked:
        problems.append(f'it closes by asking for something ("{asked}"); end on the takeaway')
    return problems


_QUOTED_RE = re.compile(r"\"[^\"\n]*\"|“[^”\n]*”|\*[^*\n]+\*")
_FIRST_PERSON_RE = re.compile(r"(?<![A-Za-z'’])(?:I|I'm|I've|I'd|I'll|my|me|we|our)(?![A-Za-z])",
                              re.IGNORECASE)


def first_person(markdown: str) -> list[str]:
    """Each sentence that speaks as him. A model cannot know what he did, so
    these are the sentences he reads first when he checks a draft."""
    text = _FRONT_RE.sub("", markdown.replace("\r\n", "\n").lstrip(), count=1)
    body = _OPEN_FENCE_RE.sub("\n", _FENCE_RE.sub("\n", text))
    # A title he links to and words he quotes are someone else's.
    paragraphs, items = _blocks(_QUOTED_RE.sub(" ", _LINK_RE.sub("a link", body)))
    found: list[str] = []
    for block in (*paragraphs, *items):
        for sentence in sentences_of(block):
            own = _QUOTED_RE.sub(" ", sentence)
            hit = _FIRST_PERSON_RE.search(own)
            # "I" must be the capital letter: "i" is an index or a list mark.
            if hit and not (hit.group().casefold() == "i" and hit.group() != "I"):
                found.append(sentence)
    return found


_FIGURE_RE = re.compile(r"(?<![\w.#/-])\d[\d,]*(?:\.\d+)?")


def numbers_not_in(markdown: str, source: str) -> list[str]:
    """The numbers in the post's prose that its material does not hold, in
    the order met. Some are sums he can check by hand and some are invented:
    code cannot tell which, so they are listed for him, not refused."""
    text = _FRONT_RE.sub("", markdown.replace("\r\n", "\n").lstrip(), count=1)
    prose = _OPEN_FENCE_RE.sub("\n", _FENCE_RE.sub("\n", text))
    prose = re.sub(r"\]\([^)]*\)", "]", prose)             # a link's address
    known = {n.replace(",", "") for n in _FIGURE_RE.findall(source)}
    known |= {n.rstrip("0").rstrip(".") for n in known if "." in n}
    missing: list[str] = []
    for found in _FIGURE_RE.findall(prose):
        n = found.replace(",", "")
        if len(n) == 1 or n in known or n in missing:       # "5 attempts", "2 articles"
            continue
        # 0.6 in the post is 60% in the material.
        if "." in n and f"{float(n) * 100:g}" in known:
            continue
        missing.append(n)
    return missing


_NOT_RUN_RE = re.compile(
    r"(?:has|have|was|were) not (?:been )?(?:run|tested|executed)|did not run|"
    r"(?:un|never )(?:run|tested)", re.IGNORECASE)


def unrun_code(markdown: str) -> bool:
    """Whether the post shows code and says nobody ran it. Two readers out of
    two lost trust at that sentence, so he is told before he publishes."""
    text = _FRONT_RE.sub("", markdown.replace("\r\n", "\n").lstrip(), count=1)
    return bool(_FENCE_RE.search(text)) and bool(_NOT_RUN_RE.search(_FENCE_RE.sub("", text)))


def headline_problems(title: str, summary: str, category: str = "") -> list[str]:
    """What is wrong with the two lines a reader sees before he clicks."""
    problems: list[str] = []
    title, summary = title.strip(), " ".join(summary.split())
    if len(title) > TITLE_CHARS:
        problems.append(
            f"the title is {len(title)} characters; a search result and a shared card cut"
            f" it at about {TITLE_CHARS}. State the claim or the question, no subtitle")
    if len(summary) > SUMMARY_CHARS:
        problems.append(
            f"the summary is {len(summary)} characters; keep it under {SUMMARY_CHARS}, one"
            " line that says what the reader gets")
    stock = found_in(f"{title} {summary}", {**_STOCK_PATTERNS, **_PLAIN_PATTERNS})
    if stock:
        problems.append("the title or summary uses: " + ", ".join(f'"{p}"' for p in stock)
                        + ". Say the plain thing")
    if category and category not in CATEGORIES:
        problems.append(f"category must be one of {', '.join(CATEGORIES)}")
    return problems


# --- field notes: what he did, in his own words -------------------------------
#
# A post written from a lesson retells an article he read. A stranger can read
# that article, so the post gives him nothing, and nothing in it is his. A
# field note is the other source: a few lines he writes after he built or
# measured something. It is the only record of what he did, so it is the only
# material that lets a post say "I".

FIELD_NOTES_DIR = "projects/content/field-notes"

# Each heading he fills, and the key the writer reads it by. The first two
# are required: a post with no deed and no number of his is a retelling.
FIELD_NOTE_PARTS: Mapping[str, str] = {
    "what i did": "did",
    "the number": "number",
    "what surprised me": "surprised",
    "what i would do differently": "view",
    "where i disagree": "view",
    "links": "links",
}

FIELD_NOTE_TEMPLATE = """---
project: ""   # optional: the slug of a project on your site, such as mission-hq
---

## What I did

What you built, ran or changed, and where. Say "at work" for your job; do not
name the company. Three to six lines.

## The number

The result you measured, with its conditions: the data, its size, the model,
the machine. One number is enough. Paste the command and its output if you
have it.

## What surprised me

What you expected, and what happened instead.

## What I would do differently

Your own view: what you would change, or where you disagree with an article.

## Links

Articles or repositories the post may link to. One url per line.
"""

_HEADING_LINE_RE = re.compile(r"^#{1,6}\s+(.*?)\s*$", re.MULTILINE)
_PROJECT_RE = re.compile(r"^project:\s*[\"']?([a-z0-9-]*)[\"']?\s*(?:#.*)?$", re.MULTILINE)
_TEMPLATE_HINTS = tuple(
    " ".join(block.split())[:40]
    for block in re.split(r"^## .*$", FIELD_NOTE_TEMPLATE, flags=re.MULTILINE)[1:]
)


@dataclass(frozen=True)
class FieldNote:
    """One field note, read into its parts."""

    text: str
    parts: Mapping[str, str]
    project: str = ""

    @property
    def has_number(self) -> bool:
        return bool(re.search(r"\d", self.parts.get("number", "")))


def read_field_note(text: str) -> FieldNote:
    """Split a field note by its headings. Text he left from the template
    counts as empty, so an unfilled note is never taken for a filled one."""
    front = _FRONT_RE.match(text)
    project = ""
    if front:
        found = _PROJECT_RE.search(front.group(0))
        project = found.group(1) if found else ""
    body = _FRONT_RE.sub("", text, count=1)
    parts: dict[str, str] = {}
    marks_ = list(_HEADING_LINE_RE.finditer(body))
    for n, m in enumerate(marks_):
        key = FIELD_NOTE_PARTS.get(m.group(1).strip().rstrip(":").casefold())
        if not key:
            continue
        end = marks_[n + 1].start() if n + 1 < len(marks_) else len(body)
        part = body[m.end():end].strip()
        if " ".join(part.split())[:40] in _TEMPLATE_HINTS:
            part = ""
        if part:
            parts[key] = (parts[key] + "\n\n" + part) if key in parts else part
    return FieldNote(text=text, parts=parts, project=project)


def field_note_problems(note: FieldNote) -> list[str]:
    """Why this note cannot carry a post yet, or []. Said to him, not to a
    model: only he can fill these in."""
    problems: list[str] = []
    if not note.parts.get("did"):
        problems.append('fill in "What I did": a post needs something you did')
    if not note.has_number:
        problems.append('fill in "The number" with a result you measured; without a'
                        " number of your own the post is a retelling of the source")
    return problems


def field_note_path(name: str) -> str:
    """The note's path in the vault, from its name or its path. Raises
    ValueError for anything outside the field notes folder."""
    raw = name.strip()
    if raw.startswith(FIELD_NOTES_DIR + "/"):
        raw = raw[len(FIELD_NOTES_DIR) + 1:]
    stem = raw.removesuffix(".md")
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", stem):
        raise ValueError(f"a field note name is lowercase words joined by hyphens: {name!r}")
    return f"{FIELD_NOTES_DIR}/{stem}.md"


def field_note_candidates(vault: Path) -> list[Candidate]:
    """His field notes, as shortlist candidates. A note with a number is his
    own result; one without is still his words."""
    folder = vault / FIELD_NOTES_DIR
    out: list[Candidate] = []
    for path in sorted(folder.glob("*.md")) if folder.is_dir() else []:
        note = read_field_note(path.read_text())
        if not note.parts.get("did"):
            continue
        first_line = note.parts["did"].splitlines()[0]
        out.append(Candidate(
            key=f"{FIELD_NOTES_DIR}/{path.name}",
            title=path.stem.replace("-", " "),
            kind="field_note",
            why=" ".join(first_line.split())[:240],
            own_result=note.has_number,
            first_seen=datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)))
    return out


_HIS_WORK_RE = re.compile(
    r"\bI (?:wrote|built|ran|measured|made|created|coded|benchmarked)\b"
    r"|\bmy (?:own )?(?:script|simulator|code|lab|benchmark|run|measurement)s?\b")


def claims_his_work(markdown: str) -> list[str]:
    """Sentences that say he made or ran something. From a lesson these are
    never his: the lesson's code was written for him, and nothing records
    that he ran it. Only a field note can carry them."""
    return [s for s in first_person(markdown) if _HIS_WORK_RE.search(s)]


def speaks_as_him(markdown: str) -> str:
    """Why a post from a field note is refused for not saying what he did, or
    "". The note is the reason the post exists; a post that hides it in the
    third person reads like every other retelling."""
    if first_person(markdown):
        return ""
    return ("the post never says what he did. The field note records it: say it"
            ' with "I", in the situation or in its own section')


# --- the week's shortlist --------------------------------------------------------

SHORTLIST_SIZE = 5
FRESH_DAYS = 14
WORTH_SHARING_PATH = "projects/content/worth-sharing.md"
SHORTLIST_PATH = "projects/content/post-shortlist.md"

# What each reason adds. His own mark outweighs everything the system can
# infer, because he is the one who knows what changed his mind.
POINTS: Mapping[str, int] = {
    # A post with his own number is the one a stranger cannot get from the
    # source, so it outranks everything else, his mark included.
    "own_result": 7,    # there is a lab or a number of his behind it
    "his_words": 3,     # he wrote a field note: what he did, in his words
    "marked": 6,        # he wrote it into worth-sharing.md
    "in_demand": 4,     # it is a topic readers look for now, from topics.md
    "hard_for_him": 2,  # he tapped "lost me": hard for him is hard for others
    "read": 2,          # he read it to the end
    "rated_high": 1,    # the reader who found it scored it 8 or more
    "fresh": 1,         # found in the last two weeks
}
REASON_WORDS: Mapping[str, str] = {
    "marked": "you marked it worth sharing",
    "own_result": "you have your own result for it",
    "his_words": "you wrote down what you did",
    "in_demand": "readers look for this topic now",
    "hard_for_him": "it was hard for you, so it is hard for others",
    "read": "you read it",
    "rated_high": "it was rated 8 or more when found",
    "fresh": "found in the last two weeks",
}
_URL_IN_LINE_RE = re.compile(r"https?://[^\s)>\]]+")
_PATH_IN_LINE_RE = re.compile(r"[\w./-]+\.md\b")


@dataclass(frozen=True)
class Candidate:
    """One thing he could write about: an article he read or a lesson."""

    key: str                     # its url, or the lesson's path
    title: str
    kind: str                    # reading | lesson | field_note
    why: str = ""                # what it adds, as recorded when it was found
    score: float = 0.0           # the finder's score, 0 to 10
    read: bool = False
    lost_me: int = 0
    own_result: bool = False
    first_seen: datetime | None = None


@dataclass(frozen=True)
class Ranked:
    candidate: Candidate
    points: int
    reasons: tuple[str, ...]


def marks(text: str) -> set[str]:
    """The urls and lesson paths he wrote into worth-sharing.md. One per
    line, anything after it on the line is his own note."""
    found: set[str] = set()
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        found.update(u.rstrip(".,;:") for u in _URL_IN_LINE_RE.findall(line))
        found.update(_PATH_IN_LINE_RE.findall(line))
    return found


TOPICS_PATH = "projects/content/topics.md"


def demand_topics(text: str) -> list[str]:
    """The topics in topics.md, one per list line. Anything after a colon is
    his own note on the line."""
    topics: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith(("-", "*")):
            continue
        topic = line.lstrip("-* ").split(":", 1)[0].strip().casefold()
        if topic:
            topics.append(topic)
    return topics


def in_demand(candidate: Candidate, topics: Sequence[str]) -> str:
    """The first topic whose every word is in the candidate's title or what
    it adds, or "". Whole words: "rag" is not "storage"."""
    words = set(re.findall(r"[a-z0-9]+", f"{candidate.title} {candidate.why}".casefold()))
    for topic in topics:
        wanted = re.findall(r"[a-z0-9]+", topic)
        if wanted and all(w in words for w in wanted):
            return topic
    return ""


def score(candidate: Candidate, marked: set[str], now: datetime,
          topics: Sequence[str] = ()) -> Ranked:
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    reasons = []
    if candidate.key in marked:
        reasons.append("marked")
    if candidate.own_result:
        reasons.append("own_result")
    if candidate.kind == "field_note":
        reasons.append("his_words")
    if in_demand(candidate, topics):
        reasons.append("in_demand")
    if candidate.lost_me > 0:
        reasons.append("hard_for_him")
    if candidate.read:
        reasons.append("read")
    if candidate.score >= 8:
        reasons.append("rated_high")
    seen = candidate.first_seen
    if seen is not None:
        if seen.tzinfo is None:
            seen = seen.replace(tzinfo=UTC)
        if now - seen <= timedelta(days=FRESH_DAYS):
            reasons.append("fresh")
    return Ranked(candidate, sum(POINTS[r] for r in reasons), tuple(reasons))


def shortlist(candidates: Iterable[Candidate], marked: set[str], posted: set[str],
              now: datetime | None = None, size: int = SHORTLIST_SIZE,
              topics: Sequence[str] = ()) -> list[Ranked]:
    """The best few, most points first. A thing already on his site is left
    out, and so is one with nothing behind it: a post needs a reason.

    ``posted`` holds what has been written already, in every form it is known
    by: the lesson path or url a post was drafted from, the file name of a
    post on his site, and the slug of its title."""
    now = now or datetime.now(UTC)
    ranked = [score(c, marked, now, topics) for c in candidates
              if c.key not in posted and _name(c) not in posted]
    ranked = [r for r in ranked if r.points > 0]
    ranked.sort(key=lambda r: (-r.points, -r.candidate.score, r.candidate.title.casefold()))
    seen: set[str] = set()
    out: list[Ranked] = []
    for r in ranked:
        name = _name(r.candidate)
        if name in seen:
            continue
        seen.add(name)
        out.append(r)
        if len(out) == size:
            break
    return out


def _slug_words(title: str) -> str:
    return "-".join(re.findall(r"[a-z0-9]+", title.casefold()))


def _name(candidate: Candidate) -> str:
    """What two candidates share when they are the same thing. A title with
    no latin letters has no slug, so it is known by its key."""
    return _slug_words(candidate.title) or candidate.key


def shortlist_markdown(ranked: Sequence[Ranked], week: str) -> str:
    """The shortlist as he reads it: five lines, each with its reasons and
    the sentence he has to finish before it becomes a post."""
    lines = [f"## {week}", ""]
    if not ranked:
        nothing = ("Nothing read this week has a reason behind it yet. Mark what is worth"
                   f" sharing in `{WORTH_SHARING_PATH}`, one url or lesson path per line.")
        return "\n".join([*lines, nothing, ""])
    ask = ("Pick two. For each, finish this sentence first:"
           ' "After reading this, you can ___." If it cannot be finished, skip it.')
    lines += [ask, ""]
    for n, r in enumerate(ranked, 1):
        c = r.candidate
        lines.append(f"{n}. **{c.title}** ({r.points} points)")
        lines.append(f"   - {c.key}")
        lines.append("   - Why: " + "; ".join(REASON_WORDS[x] for x in r.reasons))
        if c.why:
            lines.append(f"   - What it adds: {' '.join(c.why.split())[:240]}")
    lines.append("")
    return "\n".join(lines)


_TITLE_FIELD_RE = re.compile(r"^title:\s*[\"']?(.+?)[\"']?\s*$", re.MULTILINE)


def posted_titles(portfolio: Path) -> set[str]:
    """What is already on his site, drafts included: each file's name and
    the slug of its title. The name is the writer's own slug, so a lesson
    and the post made from it rarely share it; the title slug is closer."""
    found: set[str] = set()
    for folder in sorted(set(SITE_FOLDER.values())):
        for path in (portfolio / "content" / folder).glob("*.md"):
            found.add(path.stem)
            front = _FRONT_RE.match(path.read_text())
            title = _TITLE_FIELD_RE.search(front.group(0)) if front else None
            if title and _slug_words(title.group(1)):
                found.add(_slug_words(title.group(1)))
    return found


async def posted_sources() -> set[str]:
    """The lesson paths posts were drafted from, as the system recorded them.
    Kept on this side: his site is public and carries no private path."""
    from hq import db

    rows = await db.fetch(
        "SELECT DISTINCT payload->>'source' AS source FROM hq.events"
        " WHERE kind = 'post.drafted' AND coalesce(payload->>'source', '') <> ''")
    sources = {str(r["source"]) for r in rows}
    # The article a drafted lesson was written from is written about too.
    read = await db.fetch(
        "SELECT r.url FROM hq.readings r JOIN hq.lessons l ON l.id = r.lesson_id"
        " WHERE l.md_path = ANY(%s)", (sorted(sources),))
    return sources | {str(r["url"]) for r in read}


async def gather_candidates(days: int = 21) -> list[Candidate]:
    """What he could write about, read from what the system already records.
    Reads only: the articles found for him, and his lessons with their taps."""
    from hq import db

    out: list[Candidate] = []
    readings = await db.fetch(
        "SELECT r.url, r.title, r.why, r.adds, r.score, r.first_seen,"
        "       l.read_at IS NOT NULL AS read"
        "  FROM hq.readings r LEFT JOIN hq.lessons l ON l.id = r.lesson_id"
        " WHERE r.status <> 'skipped' AND r.last_seen > now() - make_interval(days => %s)",
        (days,))
    for row in readings:
        out.append(Candidate(
            key=str(row["url"]), title=str(row["title"] or row["url"]), kind="reading",
            why=str(row.get("adds") or row.get("why") or ""),
            score=float(row["score"] or 0), read=bool(row["read"]),
            first_seen=row.get("first_seen")))
    lessons = await db.fetch(
        "SELECT l.md_path, l.title, l.one_liner, l.kind, l.read_at, l.lesson_date,"
        "       (SELECT count(*) FROM hq.concept_signals s"
        "         WHERE s.lesson_id = l.id AND s.verdict = 'lost_me') AS lost_me"
        "  FROM hq.lessons l"
        " WHERE l.lesson_date > current_date - %s",
        (days,))
    for row in lessons:
        seen = row.get("lesson_date")
        out.append(Candidate(
            key=str(row["md_path"]), title=str(row["title"]), kind="lesson",
            why=str(row.get("one_liner") or ""), read=row.get("read_at") is not None,
            lost_me=int(row.get("lost_me") or 0), own_result=row.get("kind") == "lab",
            first_seen=datetime(seen.year, seen.month, seen.day, tzinfo=UTC) if seen else None))
    return out


def iso_week(now: datetime | None = None) -> str:
    """The week as he counts it: his Monday starts hours before UTC's."""
    year, week, _ = (now or datetime.now(ZoneInfo(settings().cron_tz))).isocalendar()
    return f"{year}-W{week:02d}"


# --- from the terminal -----------------------------------------------------------


def _check(argv: Sequence[str]) -> int:
    if not argv:
        print("usage: python -m hq.site_posts check <file.md> [--shape " + "|".join(SHAPES) + "]")
        return 2
    shape = DEFAULT_SHAPE
    if "--shape" in argv:
        shape = argv[argv.index("--shape") + 1]
    text = Path(argv[0]).read_text()
    print(measure(text).line())
    problems = reader_problems(text, shape)
    for p in problems:
        print(f"- {p}")
    print("passes" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


async def _shortlist() -> int:
    from hq import db

    await db.open_pool()
    try:
        candidates = await gather_candidates()
        posted = await posted_sources()
    finally:
        await db.close_pool()
    marked_file = settings().vault_dir / WORTH_SHARING_PATH
    marked = marks(marked_file.read_text()) if marked_file.is_file() else set()
    candidates += field_note_candidates(settings().vault_dir)
    topics_file = settings().vault_dir / TOPICS_PATH
    topics = demand_topics(topics_file.read_text()) if topics_file.is_file() else []
    ranked = shortlist(candidates, marked,
                       posted | posted_titles(settings().portfolio_dir), topics=topics)
    print(shortlist_markdown(ranked, iso_week()))
    return 0


def _new_field_note(argv: Sequence[str], vault: Path | None = None) -> int:
    if not argv:
        print("usage: python -m hq.site_posts field-note <name>")
        return 2
    try:
        rel = field_note_path(argv[0])
    except ValueError as exc:
        print(exc)
        return 2
    path = (vault or settings().vault_dir) / rel
    if path.exists():
        print(f"{path} exists already")
        return 1
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(FIELD_NOTE_TEMPLATE)
    print(f"wrote {path}. Fill it in, then draft the post from the console.")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    command = args[0] if args else ""
    if command == "check":
        return _check(args[1:])
    if command == "field-note":
        return _new_field_note(args[1:])
    if command == "shortlist":
        import asyncio

        return asyncio.run(_shortlist())
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
