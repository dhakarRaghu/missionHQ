"""The one gate for the owner's employers.

His current and former employers are never named in anything an agent
writes, searches, fetches or hands to another agent. The names live only in
``settings().private_employers`` (from .env); every check goes through
``employers_named`` so there is one matching rule, and every refusal says
what to do without repeating a name back into the run.

Matching is whole-word and case-insensitive: "Acme" is refused inside
"at Acme." or "acme.com/jobs" or "phase06_acme", but not inside "Acmeology".
Letters and digits are word characters; everything else (space, dot, slash,
underscore, hyphen) is a boundary, so a url or a file path is caught too.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from functools import lru_cache

from hq.config import settings

REFUSAL = (
    "refused: this names one of the owner's employers (current or former)."
    " They are never named, searched, fetched or written anywhere. Describe the"
    " work in general terms instead (for example \"a payments company\" or \"a"
    " B2B SaaS company\"), or leave it out, and call again."
)


@lru_cache(maxsize=64)
def _pattern(name: str) -> re.Pattern[str]:
    words = [re.escape(w) for w in name.lower().split()]
    return re.compile(r"(?<![a-z0-9])" + r"[\s_-]*".join(words) + r"(?![a-z0-9])")


def employers_named(text: str) -> list[str]:
    """The configured employer names that ``text`` contains, whole-word.

    For code that must know which (tests, a count). Never put the result in
    a message an agent reads; use ``REFUSAL`` for that."""
    if not text:
        return []
    lowered = text.lower()
    return [n for n in settings().private_employers
            if n.strip() and _pattern(n.strip()).search(lowered)]


def _squash(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.casefold())


def private_employer(company: str) -> bool:
    """True when this company is one of the owner's own employers.

    For a company field or a board slug, where the name is the whole value:
    compared with spaces and punctuation squeezed out, so "acmecorp" or
    "<Name> Technologies Pvt Ltd" still matches. Free text uses the
    whole-word ``employers_named`` instead."""
    key = _squash(company)
    return bool(key) and any(
        (name := _squash(employer)) and name in key
        for employer in settings().private_employers
    )


def where_named(text: str, *, width: int = 40) -> list[str]:
    """For each mention, the words just before it (or after it, at the start
    of a text), without the name. Lets a refusal point at the sentence to
    rewrite without putting the name back into the run."""
    out: list[str] = []
    lowered = text.lower()
    for name in settings().private_employers:
        if not name.strip():
            continue
        for m in _pattern(name.strip()).finditer(lowered):
            lo, hi = max(0, m.start() - width), min(len(text), m.end() + width)
            # Drop a word the window cut in half, never a whole one.
            before = text[lo:m.start()].split()[1 if lo else 0:]
            after = text[m.end():hi].split()
            after = after[:-1] if hi < len(text) else after
            snippet = " ".join(before) if len(" ".join(before)) >= 12 else " ".join(after)
            if snippet and snippet not in out and not employers_named(snippet):
                out.append(snippet)
    return out


def _texts(value: object) -> Iterable[str]:
    if isinstance(value, str):
        yield value
    elif isinstance(value, Mapping):
        for k, v in value.items():
            yield from _texts(k)
            yield from _texts(v)
    elif isinstance(value, (list, tuple, set, frozenset)):
        for v in value:
            yield from _texts(v)


def problem(*values: object) -> str | None:
    """``REFUSAL`` when any string in ``values`` (searched through lists,
    tuples and dict keys and values) names an employer, else None."""
    if not settings().private_employers:
        return None
    for text in (t for v in values for t in _texts(v)):
        if employers_named(text):
            return REFUSAL
    return None
