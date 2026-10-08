"""What code can settle about a plan and a narration, before any model judges it.

Every rule here is in `agents/tutor/video/rules.md`, and each came from a
finished video that broke it. A model is not asked what a regular expression
can answer.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

from hq.video.models import Line, VideoPlan

WORDS_PER_MINUTE = 150          # Kokoro af_heart at speed 0.94, measured on twelve episodes
LONG_WORDS = 26                 # a heard sentence past this needs a second listen (episodes reached 25)
SHORT_WORDS = 5
SHORT_SHARE = 0.20              # more short sentences than this reads as a list of facts
                                # (the approved episodes ran 13 to 16%)
CONCEPTS = {"course": (1, 12), "article": (1, 6)}
# Long and detailed by design: every concept of the lesson, in full. The
# length follows from the concepts, so the check is per concept; the total
# limit only catches a runaway script. The first article run (6 concepts)
# measured 28.7 minutes, 4.5 a concept including the cold open and payoff.
PER_CONCEPT = (1.5, 7.0)
MINUTES = {"course": (4.0, 75.0), "article": (3.0, 60.0)}

STEP_ORDER = "kspqtmnrh"        # claim, situation, picture, question, think, mechanism, number, keys, bridge
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

FIXED = {
    "q0": ("Here is the question.", "starts"),
    "q1": ("Let's think it through.", "ends"),
    "t1": ("A first thought", "starts"),
    "r0": ("Remember:", "starts"),
    "r1": ("The trap:", "starts"),
    "r2": ("Try this:", "starts"),
}


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

def plan_problems(plan: VideoPlan, mode: str, material: str) -> list[str]:
    out: list[str] = []
    low, high = CONCEPTS[mode]
    if not low <= len(plan.concepts) <= high:
        out.append(f"a {mode} video has {low} to {high} concepts; this plan has {len(plan.concepts)}")
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
    if "?" in text and not (beat in ("cold", "title") or ln.key in ("q0", "q1")):
        out.append(f"{where}: a question outside the cold open and the think-it-through")
    # A key point is exactly one r line, so "split it" there made a fourth r
    # line, which the key-point rule then refused: the writer went back and
    # forth between the two rules until the rewrites ran out (2026-10-08).
    key_point = CONCEPT_BEAT.match(beat) is not None and _step_letter(ln.key) == "r"
    fix = (f"shorten it to {LONG_WORDS} words or fewer and keep it one {ln.key} line;"
           " a key point never gets a second line") if key_point else "split it"
    for s in sentences(text):
        if word_count(s) > LONG_WORDS:
            out.append(f"{where}: a sentence of {word_count(s)} words; {fix}: {s[:90]!r}")
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
        out.append(f"{beat}: the steps are out of order; the order is claim k, situation s,"
                   " picture p, question q, think t, mechanism m, number n, key points r, bridge h")
    need = set("kspqtmnr") | ({"h"} if not last else set())  # the last one leads to the payoff
    for letter in sorted(need - set(letters)):
        out.append(f"{beat}: the step {letter!r} is missing")
    for key in ("q0", "q1", "t1", "t2", "t3", "r0", "r1", "r2"):
        if key not in keys:
            out.append(f"{beat}: line {key} is missing")
    r_keys = [k for k in keys if _step_letter(k) == "r"]
    if len(r_keys) != 3:
        out.append(f"{beat}: the key points are exactly three lines, r0 Remember, r1 The trap,"
                   f" r2 Try this; this beat has {len(r_keys)}: {r_keys}")
    by_key = {ln.key: ln for ln in lines}
    for key, (phrase, how) in FIXED.items():
        ln = by_key.get(key)
        if not ln:
            continue
        t = ln.text.strip()
        ok = (t == phrase if how == "exact" else t.endswith(phrase) if how == "ends"
              else t.startswith(phrase))
        if not ok:
            out.append(f"{beat}.{key}: must {'be' if how == 'exact' else how + ' with'} {phrase!r}")
    if "?" not in by_key.get("q0", Line(key="", text="")).text + by_key.get("q1", Line(key="", text="")).text:
        out.append(f"{beat}.q1: the question itself must end with ?")
    # "What it misses" may be its own line (t2a, t2b, ...) after "That is
    # reasonable", so the rule reads every t2 line together.
    misses = " ".join(ln.text for ln in lines if re.match(r"^t2[a-z]?$", ln.key))
    if misses and not re.search(r"\bbut\b", misses, re.IGNORECASE):
        out.append(f"{beat}.t2: says why the first thought is reasonable, then, with 'but',"
                   " what it misses")
    real = " ".join(ln.text for ln in lines if re.match(r"^t3[a-z]?$", ln.key))
    if real and "real question" not in real.lower():
        out.append(f"{beat}.t3: states 'So the real question is …'")
    # Lines after the last step may carry the step's result without a number.
    steps = [ln for ln in lines if _step_letter(ln.key) == "m" and ln.text.startswith("Step ")]
    for n, ln in enumerate(steps, 1):
        if not ln.text.startswith(f"Step {n}."):
            out.append(f"{beat}.{ln.key}: must start with 'Step {n}.'")
    if not 2 <= len(steps) <= 6:
        out.append(f"{beat}: the mechanism has 2 to 6 steps; it has {len(steps)}")
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


def by_beat(problems: Sequence[str]) -> dict[str, list[str]]:
    """Group findings by the beat they name, so only those beats are rewritten."""
    out: dict[str, list[str]] = {}
    for p in problems:
        beat = re.split(r"[.:\s]", p, maxsplit=1)[0]
        out.setdefault(beat, []).append(p)
    return out
