"""The owner's register, as a gate on content drafts.

``agents/_shared/voice.yaml`` holds numbers measured from his own posts:
contractions, "I think", no em dashes, no furniture. A draft written in the
register of an essay (full forms, no "I think", even sentences) reads as
someone else, and batch after batch of them was rejected by hand. The counts
are cheap and exact, so they are checked here before a draft is written,
instead of being asked for in a prompt.

``register_problems`` returns what is wrong in plain words, or an empty list.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from hq.config import settings

DRAFTS_PREFIX = "projects/content/drafts/"

_APOSTROPHE_RE = re.compile(r"[A-Za-z]['’][A-Za-z]")
_EMOJI_RE = re.compile(
    "[\U0001f300-\U0001faff\U00002600-\U000027bf\U0001f000-\U0001f2ff\U0001f900-\U0001f9ff]"
)
_HASHTAG_RE = re.compile(r"(?<![\w&/])#[A-Za-z]\w*")
_BULLET_RE = re.compile(r"^\s*(?:[-*+•]\s+)", re.MULTILINE)
_NUMBERED_RE = re.compile(r"^\s*\d+[.)]\s+", re.MULTILINE)
# "1/" or "2/5" opening a line, "(1/5)" anywhere, or the thread emoji. Not
# "24/7" mid-sentence.
_THREAD_RE = re.compile(r"^\s*\d{1,2}/\d{0,2}(?:\s|$)|\(\d{1,2}/\d{1,2}\)|\U0001f9f5",
                        re.MULTILINE)
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")
_SENTENCE_RE = re.compile(r"[^.!?\n]+[.!?]*")


def voice_path() -> Path:
    return settings().agents_dir / "_shared" / "voice.yaml"


@lru_cache(maxsize=4)
def _load(path: str, mtime: float) -> dict[str, Any]:
    data = yaml.safe_load(Path(path).read_text()) or {}
    return data if isinstance(data, dict) else {}


def voice() -> dict[str, Any]:
    """The parsed voice.yaml, reloaded when the file changes. {} when absent."""
    path = voice_path()
    try:
        return _load(str(path), path.stat().st_mtime)
    except FileNotFoundError:
        return {}


def _body(text: str) -> str:
    """The prose of a draft: no frontmatter, no heading lines, no code."""
    text = text.lstrip()
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            text = text[end + 4:]
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    lines = [line for line in text.splitlines() if not _HEADING_RE.match(line)]
    return "\n".join(lines).strip()


def _count_phrases(text: str, phrases: list[str]) -> int:
    total = 0
    for phrase in phrases:
        words = [re.escape(w) for w in str(phrase).replace("’", "'").split()]
        if not words:
            continue
        total += len(re.findall(r"\b" + r"\s+".join(words) + r"\b", text, re.IGNORECASE))
    return total


def _contains(text: str, phrase: str) -> bool:
    return str(phrase).casefold() in text.casefold()


def register_problems(text: str) -> list[str]:
    """What keeps this draft out of his register, or [] when it passes.

    Every number comes from voice.yaml's ``gate``. A voice file that is
    missing or empty gates nothing: the check is data, not a second copy of
    the rules."""
    gate = voice().get("gate") or {}
    if not gate:
        return []
    body = _body(text)
    plain = body.replace("’", "'")
    problems: list[str] = []

    apostrophes = len(_APOSTROPHE_RE.findall(body))
    need = int(gate.get("min_apostrophes", 0))
    if apostrophes < need:
        problems.append(
            f"{apostrophes} contraction(s); he writes at least {need} (it's, don't, I've)"
        )
    written = _count_phrases(plain, list(gate.get("written_out_forms") or []))
    most = int(gate.get("max_written_out_forms", 99))
    if written > most:
        problems.append(
            f"{written} written-out forms (it is, do not, cannot); at most {most}, contract them"
        )
    thinks = _count_phrases(plain, list(gate.get("i_think_family") or []))
    least = int(gate.get("min_i_think_family", 0))
    if thinks < least:
        problems.append(
            'no "I think" family (I think, I don\'t think, I\'d rather, I suspect);'
            " he states a view as his"
        )
    dashes = body.count("—")
    if dashes > int(gate.get("max_em_dashes", 99)):
        problems.append(f"{dashes} em dash(es); he uses none, split the sentence")

    forbid = set(gate.get("forbid") or [])
    if "emoji" in forbid and _EMOJI_RE.search(body):
        problems.append("emoji; he uses none")
    if "hashtags" in forbid and _HASHTAG_RE.search(body):
        problems.append("hashtags; he uses none")
    if "bullets" in forbid and _BULLET_RE.search(body):
        problems.append("bullet lines; he writes short lines, not lists")
    if "numbered_lists" in forbid and _NUMBERED_RE.search(body):
        problems.append("a numbered list; he writes short lines, not lists")
    if "thread_markers" in forbid and _THREAD_RE.search(body):
        problems.append("thread markers (1/, 🧵); one post, no thread furniture")

    sentences = [s.strip() for s in _SENTENCE_RE.findall(body) if s.strip()]
    first = sentences[0] if sentences else ""
    last = " ".join(sentences[-2:]) if sentences else ""
    for opener in gate.get("banned_openers") or []:
        if opener == "rhetorical_question":
            if first.endswith("?"):
                problems.append("it opens on a rhetorical question")
        elif first.casefold().startswith(str(opener).casefold()):
            problems.append(f'it opens with "{opener}"')
    for closer in gate.get("banned_closers") or []:
        if closer == "engagement_request":
            asks = [p for p in gate.get("engagement_requests") or [] if _contains(last, p)]
            if asks:
                problems.append(f'it closes by asking for engagement ("{asks[0]}")')
        elif _contains(last, closer):
            problems.append(f'it closes with "{closer}"')
    planning = [w for w in gate.get("planning_words") or []
                if re.search(r"(?<!\w)" + re.escape(str(w)) + r"(?!\w)", body, re.IGNORECASE)]
    if planning:
        problems.append("planning words left in the draft: " + ", ".join(planning))
    return problems


def is_draft_path(rel: str) -> bool:
    return rel.startswith(DRAFTS_PREFIX)
