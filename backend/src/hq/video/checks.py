"""What code can settle about a plan and a narration, before any model judges it.

Every rule here is in `agents/tutor/video/rules.md`, and each came from a
finished video that broke it. A model is not asked what a regular expression
can answer.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from hq.video.models import Line, PartPlan, SeriesPlan, VideoPlan

WORDS_PER_MINUTE = 150          # Kokoro af_heart at speed 0.94, measured on twelve episodes
LONG_WORDS = 26                 # a heard sentence past this needs a second listen (episodes reached 25)
SHORT_WORDS = 5
SHORT_SHARE = 0.20              # more short sentences than this reads as a list of facts
                                # (the approved episodes ran 13 to 16%)
# Every concept of the lesson, in full, but told as parts of about ten
# minutes: the 20- to 49-minute single videos were not watched to the end
# (2026-10-14). The series holds every concept; one part holds 1 to 4.
SERIES_CONCEPTS = {"course": (1, 12), "article": (1, 6)}
PART_CONCEPTS = (1, 4)
MAX_PARTS = 5
PER_CONCEPT = (1.2, 4.5)
MINUTES = {"course": (4.0, 14.0), "article": (3.0, 14.0)}

# Situation, question, thinking it through, picture, mechanism, number,
# takeaway, bridge: the question before the answer, the claim said once.
STEP_ORDER = "sqtpmnkh"
CONCEPT_BEAT = re.compile(r"^c\d+$")
KEY_RE = re.compile(r"^([a-z]{1,2})(\d+)([a-z]?)$")

BANNED = [
    "simply", "just", "easily", "delve", "leverage", "robust", "seamless", "crucial",
    "landscape", "under the hood", "boils down", "it is worth noting", "spin up",
    "kick off", "chew through", "game changer", "in this module", "pause and think",
    "take a moment",
]
PART_NAME = re.compile(r"\b(?:Phase|Part)\s+(?:\d+[A-Z]?|[A-Z])\b|\bConcept\s+\d+\b"
                       r"|\bmodule\b", re.IGNORECASE)
NEEDS_SAY = re.compile(r"\d|[%$→×÷≈±<>=/+−]|\b[A-Z]{2,}\b|_")
SAY_FORBIDS = re.compile(r"\d|[%$→×÷≈<>=_]")
SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(])")

# The fixed phrases of the first form. Said in every concept, eight times in
# a 36-minute video, they made each concept predictable from its first line.
STOCK = re.compile(r"Here is the question|Let's think it through|A first thought is"
                   r"|That is reasonable|So the real question|Remember:|The trap:|Try this:"
                   r"|^Step \d+\.", re.IGNORECASE)


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def sentences(text: str) -> list[str]:
    return [s for s in SENTENCE_END.split(_flat(text)) if s]


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9$%.,'-]+", text))


def minutes(beats: Mapping[str, Sequence[Line]]) -> float:
    words = sum(word_count(ln.say or ln.text) for lines in beats.values() for ln in lines)
    return words / WORDS_PER_MINUTE


def found_in(quote: str, material: str) -> bool:
    q = _flat(quote).lower().strip(" .\"'")
    return len(q) >= 12 and q in _flat(material).lower()


# --- the plan -----------------------------------------------------------------

def plan_problems(plan: VideoPlan, mode: str, material: str,
                  part: PartPlan | None = None) -> list[str]:
    out: list[str] = []
    if part is not None:
        if len(plan.concepts) != len(part.concepts):
            out.append(f"this part teaches {len(part.concepts)} concepts ({part.concepts});"
                       f" the plan has {len(plan.concepts)}")
    else:
        low, high = PART_CONCEPTS
        if not low <= len(plan.concepts) <= high:
            out.append(f"a video has {low} to {high} concepts; this plan has {len(plan.concepts)}")
    if not plan.question.strip().endswith("?"):
        out.append("`question` must be one question ending with ?")
    if len(plan.title) > 70:
        out.append("`title` is the problem in the viewer's words, max 70 characters")
    if PART_NAME.search(plan.title):
        out.append("`title` names a part or phase")
    seen: set[str] = set()
    news: set[str] = set()
    for i, c in enumerate(plan.concepts, 1):
        tag = f"concept {c.id}"
        if c.id != f"c{i}":
            out.append(f"{tag}: ids run c1, c2, ... in order; expected c{i}")
        if len(c.heading) > 60:
            out.append(f"{tag}: heading is {len(c.heading)} characters, max 60")
        if c.heading.lower() in seen:
            out.append(f"{tag}: heading repeats an earlier one")
        seen.add(c.heading.lower())
        if not c.question.strip().endswith("?"):
            out.append(f"{tag}: `question` must end with ?")
        if not c.takeaway.strip():
            out.append(f"{tag}: `takeaway` is the concept's claim, said once at the end")
        if not 2 <= len(c.steps) <= 6:
            out.append(f"{tag}: the mechanism has 2 to 6 steps; it has {len(c.steps)}")
        if not found_in(c.evidence_quote, material):
            out.append(f"{tag}: `evidence_quote` is not in the material word for word:"
                       f" {c.evidence_quote[:120]!r}. Copy it exactly or choose another.")
        if PART_NAME.search(c.heading):
            out.append(f"{tag}: the heading names a part or phase")
        new = re.sub(r"\W+", " ", c.new_here.lower()).strip()
        if len(new) < 15:
            out.append(f"{tag}: `new_here` must say, in a sentence, what this concept adds that"
                       " no earlier one did; if it adds nothing, merge it into that concept")
        elif new in news:
            out.append(f"{tag}: `new_here` repeats an earlier concept's; merge the two concepts")
        news.add(new)
    return out


def series_problems(series: SeriesPlan, mode: str) -> list[str]:
    """A series holds every concept of the lesson, in parts of about ten minutes."""
    out: list[str] = []
    total = sum(len(p.concepts) for p in series.parts)
    low, high = SERIES_CONCEPTS[mode]
    if not low <= total <= high:
        out.append(f"a {mode} lesson is taught in {low} to {high} concepts; this series has {total}")
    if not 1 <= len(series.parts) <= MAX_PARTS:
        out.append(f"a series has 1 to {MAX_PARTS} parts; this one has {len(series.parts)}")
    # About ten minutes a part: no part of one concept when two fit, and none
    # of five. Fewest parts first: ceil(total / 4) to ceil(total / 2).
    fewest, most = -(-total // PART_CONCEPTS[1]), max(1, -(-total // 2))
    if total and not fewest <= len(series.parts) <= most:
        out.append(f"{total} concepts make {fewest} to {most} parts of 2 to 4 concepts;"
                   f" this series has {len(series.parts)}")
    if len(series.title) > 70 or PART_NAME.search(series.title):
        out.append("`title` is the lesson's problem in the viewer's words, max 70 characters,"
                   " with no part or phase name")
    seen: set[str] = set()
    for n, part in enumerate(series.parts, 1):
        tag = f"part {n}"
        if not PART_CONCEPTS[0] <= len(part.concepts) <= PART_CONCEPTS[1]:
            out.append(f"{tag}: a part has {PART_CONCEPTS[0]} to {PART_CONCEPTS[1]} concepts;"
                       f" it has {len(part.concepts)}")
        if len(part.title) > 70 or PART_NAME.search(part.title):
            out.append(f"{tag}: `title` is the problem in the viewer's words, max 70 characters,"
                       " with no part or phase name")
        if not part.question.strip().endswith("?"):
            out.append(f"{tag}: `question` must be one question ending with ?")
        last = n == len(series.parts)
        if last and part.leads_to.strip():
            out.append(f"{tag}: the last part answers the series; `leads_to` is empty")
        if not last and not part.leads_to.strip().endswith("?"):
            out.append(f"{tag}: `leads_to` is the question the next part answers, ending with ?")
        for heading in part.concepts:
            if len(heading) > 60:
                out.append(f"{tag}: concept {heading!r} is {len(heading)} characters, max 60")
            if heading.lower() in seen:
                out.append(f"{tag}: concept {heading!r} is taught in an earlier part too")
            seen.add(heading.lower())
    return out


# --- the narration --------------------------------------------------------------

def beat_order(n_concepts: int) -> list[str]:
    """Every video ends its story: the payoff answers the cold open's question."""
    return ["cold", "title", *[f"c{i}" for i in range(1, n_concepts + 1)],
            "payoff", "recap", "end"]


def _step_letter(key: str) -> str:
    m = KEY_RE.match(key)
    return m.group(1) if m else ""


def line_problems(beat: str, ln: Line) -> list[str]:
    """Rules one spoken line must keep, whatever beat it is in."""
    out: list[str] = []
    where = f"{beat}.{ln.key}"
    text = ln.text
    low = text.lower()
    for word in BANNED:
        if re.search(rf"\b{re.escape(word)}\b", low):
            out.append(f"{where}: remove {word!r}")
    if "—" in text or ";" in text:
        out.append(f"{where}: no em dash and no semicolon")
    if part := PART_NAME.search(text):
        out.append(f"{where}: names a part, phase or concept number: {part.group(0)!r}")
    concept = CONCEPT_BEAT.match(beat) is not None
    asks = beat in ("cold", "title", "end") or (concept and _step_letter(ln.key) == "q")
    if "?" in text and not asks:
        out.append(f"{where}: a question outside the cold open, the title, a q line and the end")
    if concept and (stock := STOCK.search(text)):
        out.append(f"{where}: {stock.group(0)!r} is a fixed phrase; say it in your own words")
    for s in sentences(text):
        if word_count(s) > LONG_WORDS:
            out.append(f"{where}: a sentence of {word_count(s)} words; split it: {s[:90]!r}")
    if NEEDS_SAY.search(text) and not ln.say.strip():
        out.append(f"{where}: `text` has digits, symbols, acronyms or code names; write `say`")
    if ln.say and SAY_FORBIDS.search(ln.say):
        out.append(f"{where}: `say` must spell out every digit and symbol: {ln.say[:90]!r}")
    return out


def concept_problems(beat: str, lines: Sequence[Line], last: bool = False) -> list[str]:
    out: list[str] = []
    keys = [ln.key for ln in lines]
    letters = [_step_letter(k) for k in keys]
    if any(not lt for lt in letters):
        out.append(f"{beat}: bad keys {[k for k, lt in zip(keys, letters) if not lt]}")
        return out
    ranks = [STEP_ORDER.index(lt) if lt in STEP_ORDER else -1 for lt in letters]
    if -1 in ranks:
        out.append(f"{beat}: keys must start with one of {list(STEP_ORDER)}")
    if ranks != sorted(ranks):
        out.append(f"{beat}: the steps are out of order; the order is situation s, question q,"
                   " thinking t, picture p, mechanism m, number n, takeaway k, bridge h")
    need = set("sqtmk") | ({"h"} if not last else set())  # the last one leads to the payoff
    for letter in sorted(need - set(letters)):
        out.append(f"{beat}: the step {letter!r} is missing")
    count = {lt: letters.count(lt) for lt in set(letters)}
    if "t" in count and not 2 <= count["t"] <= 4:
        out.append(f"{beat}: thinking it through takes 2 to 4 t lines (a first answer, why it is"
                   f" reasonable, what it misses); it has {count['t']}")
    if count.get("k", 0) > 2:
        out.append(f"{beat}: the takeaway is said once, in 1 or 2 k lines; it has {count['k']}")
    q = [ln for ln in lines if _step_letter(ln.key) == "q"]
    if q and not q[-1].text.strip().endswith("?"):
        out.append(f"{beat}.{q[-1].key}: the last q line is the question and ends with ?")
    misses = " ".join(ln.text for ln in lines if _step_letter(ln.key) == "t")
    if misses and not re.search(r"\bbut\b", misses, re.IGNORECASE):
        out.append(f"{beat}: the t lines give a first answer and why it is reasonable, then,"
                   " with 'but', what it misses")
    # The scene shows 2 to 6 mechanism items, each on its own m line.
    m = [ln for ln in lines if _step_letter(ln.key) == "m"]
    if m and len(m) < 2:
        out.append(f"{beat}: the mechanism takes at least 2 m lines, one per step")
    if len(m) > 8:
        out.append(f"{beat}: the mechanism runs {len(m)} m lines; keep it to its 2 to 6 steps")
    return out


def narration_problems(beats: Mapping[str, Sequence[Line]], *, mode: str,
                       n_concepts: int) -> list[str]:
    out: list[str] = []
    want = beat_order(n_concepts)
    if list(beats) != want:
        out.append(f"beats must be {want}; got {list(beats)}")
    all_sentences: list[str] = []
    for beat, lines in beats.items():
        if not lines:
            out.append(f"{beat}: no lines")
            continue
        keys = [ln.key for ln in lines]
        if len(set(keys)) != len(keys):
            out.append(f"{beat}: duplicate keys")
        for ln in lines:
            out += line_problems(beat, ln)
            all_sentences += sentences(ln.text)
        if CONCEPT_BEAT.match(beat):
            out += concept_problems(beat, lines, last=beat == f"c{n_concepts}")
        if beat == "cold" and not lines[-1].text.strip().endswith("?"):
            out.append("cold: the last line is the one question, ending with ?")
        if beat == "recap":
            m = re.search(r"in (\w+) lines\.?$", lines[0].text)
            if not m:
                out.append("recap: the first line is '<Subject>, in <N> lines.'")
    if all_sentences:
        short = sum(1 for s in all_sentences if word_count(s) <= SHORT_WORDS)
        if short / len(all_sentences) > SHORT_SHARE:
            out.append(f"{short} of {len(all_sentences)} sentences have five words or fewer;"
                       " join them into sentences that keep their reason")
    low, high = MINUTES[mode]
    mins = minutes(beats)
    if not low <= mins <= high:
        out.append(f"the narration runs about {mins:.1f} minutes; a {mode} video runs {low:g}"
                   f" to {high:g}")
    for beat, lines in beats.items():
        if CONCEPT_BEAT.match(beat):
            each = minutes({beat: lines})
            if not PER_CONCEPT[0] <= each <= PER_CONCEPT[1]:
                out.append(f"{beat}: this concept runs {each:.1f} minutes; a concept runs"
                           f" {PER_CONCEPT[0]:g} to {PER_CONCEPT[1]:g}")
    return out


LENGTH_MARGIN = 0.25             # minutes under the limit a cut aims for, so a rewrite that runs a little long still fits


def length_cuts(beats: Mapping[str, Sequence[Line]], *, mode: str) -> dict[str, list[str]]:
    """When the whole narration runs past its limit, a finding for each of the
    longest concept beats with how many words to cut there. The total-length
    finding names no beat, so ``by_beat`` cannot send it anywhere: on
    2026-10-17 a 14.6-minute script was only noted, never cut, and stopped
    before the voice. The cut levels the longest concepts down to one length,
    never below a concept's minimum."""
    high = MINUTES[mode][1]
    mins = minutes(beats)
    if mins <= high:
        return {}
    excess = round((mins - high + LENGTH_MARGIN) * WORDS_PER_MINUTE)
    floor = round(PER_CONCEPT[0] * WORDS_PER_MINUTE)
    words = {b: minutes({b: lines}) * WORDS_PER_MINUTE
             for b, lines in beats.items() if CONCEPT_BEAT.match(b)}
    # Lower one level across the longest beats until the cut covers the excess.
    level = max(words.values(), default=0.0)
    while level > floor and sum(max(0.0, w - level) for w in words.values()) < excess:
        level -= 1
    out: dict[str, list[str]] = {}
    for beat, w in sorted(words.items(), key=lambda kv: -kv[1]):
        cut = round(w - level)
        if cut <= 0:
            break
        out[beat] = [(f"{beat}: the whole narration runs about {mins:.1f} minutes; a {mode}"
                      f" video runs at most {high:g}, and this is one of its longest concepts."
                      f" Cut about {cut} words here, from about {round(w)} to {round(w) - cut}."
                      " Keep every step, number and term; drop repeats, side remarks and"
                      " sentences that say a point twice")]
    return out


def by_beat(problems: Sequence[str]) -> dict[str, list[str]]:
    """Group findings by the beat they name, so only those beats are rewritten."""
    out: dict[str, list[str]] = {}
    for p in problems:
        beat = re.split(r"[.:\s]", p, maxsplit=1)[0]
        out.setdefault(beat, []).append(p)
    return out
