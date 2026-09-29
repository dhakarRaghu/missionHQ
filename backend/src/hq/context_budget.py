"""Keep every agent's conversation inside its model's context window.

An agent run re-sends its whole conversation on every model request: the
task, every tool call, and every page a tool returned. Nothing bounded that
total. On 2026-09-28 hunter studied Phase 2B, read page after page, and its
request reached 222,886 input tokens. The model's window is 262,144 and
64,000 of it is kept for the answer, so the gateway answered HTTP 400 and the
study was lost after eleven minutes of reading.

So before each model request this module measures the conversation, and when
it would not fit, it shortens the oldest tool results first. The task, the
agent's own words and the newest results are never shortened.

Nothing is lost. Before a result leaves the conversation, its whole text is
saved for the run (`store`), and the conversation keeps two things in its
place: an extract of its facts (its start, its headings, and every sentence
with a number, a unit or a comparison) and a reference. The agent reads the
whole text again with `recall_text`, in parts that fit the window, when it
writes its final note and needs the exact words. He asked for exactly this
on 2026-09-28: "do in-memory store and then in final use that full ... so
that we don't lose anything". Before this module a run that reached the
window lost everything it had read.

The measure is calibrated on the model's own count: the last response
reports how many input tokens its request had, and only what was added after
it is estimated from its length.
"""

from __future__ import annotations

import dataclasses
import hashlib
import logging
import os
import re
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic_ai import RunContext
from pydantic_ai.capabilities import ProcessHistory
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolReturnPart,
)

log = logging.getLogger(__name__)

# Characters per token for text the model has not counted yet. Web pages and
# JSON run near 3; prose near 4. The lower number errs on the side of room.
CHARS_PER_TOKEN = 3.0
# The instructions and the tool schemas are sent with every request but are
# not in the message list. This is room for them before any response exists.
INSTRUCTIONS_TOKENS = 12_000
KEEP_RECENT = 2              # the newest tool results are never shortened
EXTRACT_CHARS = 6_000        # what a shortened result keeps: about 2,000 tokens
SHORT_MIN = 2 * EXTRACT_CHARS  # a result shorter than this is left whole

RECALL_CHARS = 60_000         # one part of a recalled text: about 20,000 tokens
KEEP_DAYS = 7                 # a run's saved results are removed after this
# A chat keeps its shortened history for as long as it is open, and he may
# come back to one after weeks: its saved texts are kept longer.
SESSION_KEEP_DAYS = 90
_REF_RE = re.compile(r"^[0-9a-f]{16}$")

_SENTENCE_RE = re.compile(r"[^.!?\n]+[.!?]?")
# A fact a note is built from: a number with or without a unit, a version, a
# percentage, a comparison word.
_FACT_RE = re.compile(
    r"\d|\bv\d|\b(?:faster|slower|higher|lower|more|less|than|times|percent|ms|tokens?"
    r"|throughput|latency|p\d\d|bytes?|GB|MB|KB)\b", re.IGNORECASE)
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+.+$|^[A-Z][^.!?\n]{3,80}$", re.MULTILINE)


def _text(part: Any) -> str:
    for name in ("content", "args"):
        value = getattr(part, name, None)
        if value is not None:
            return value if isinstance(value, str) else str(value)
    return ""


def _chars(message: ModelMessage) -> int:
    return sum(len(_text(p)) for p in message.parts)


def estimate_tokens(messages: Sequence[ModelMessage]) -> int:
    """What the next request will carry. The newest response that reports
    its usage gives the count up to that point; the rest is estimated."""
    for at in range(len(messages) - 1, -1, -1):
        m = messages[at]
        used = getattr(getattr(m, "usage", None), "input_tokens", 0) or 0
        if isinstance(m, ModelResponse) and used:
            after = sum(_chars(x) for x in messages[at:])
            return int(used + after / CHARS_PER_TOKEN)
    return int(INSTRUCTIONS_TOKENS + sum(_chars(m) for m in messages) / CHARS_PER_TOKEN)


def extract(text: str, limit: int = EXTRACT_CHARS) -> str:
    """The facts of a long text, in their order: its first lines, its
    headings, and each sentence that carries a number or a comparison."""
    head = " ".join(text[:600].split())
    kept: list[str] = [head]
    size = len(head)
    seen = {head}
    marks = {m.start() for m in _HEADING_RE.finditer(text)}
    for m in _SENTENCE_RE.finditer(text):
        sentence = " ".join(m.group(0).split())
        if len(sentence) < 20 or sentence in seen:
            continue
        if m.start() in marks or _FACT_RE.search(sentence):
            if size + len(sentence) + 1 > limit:
                break
            kept.append(sentence)
            seen.add(sentence)
            size += len(sentence) + 1
    return " ".join(kept)


# --- the store: nothing that leaves the conversation is lost -------------------------

# A process with no run and no session (the CLI, the regression runner) gets
# a folder of its own, so one of them cannot read what another saved.
_PROCESS_SCOPE = f"proc-{os.getpid()}-{int(time.time())}"


def scope(deps: Any) -> str:
    """Whose saved texts these are. A chat keeps its history across turns,
    and every turn is a new run, so a chat's texts belong to its session; a
    task's belong to its run."""
    session = getattr(deps, "session_id", None)
    if session:
        return f"s-{session}"
    run = getattr(deps, "run_id", None)
    return f"r-{run}" if run else _PROCESS_SCOPE


def _run_dir(scope: str) -> Path:
    from hq.config import settings

    safe = re.sub(r"[^A-Za-z0-9_-]", "_", scope)[:80]
    return settings().context_store_dir / safe


def store(scope: str, tool_name: str, text: str, recall_tool: str = "recall_text") -> str:
    """Save one result whole; returns its reference. The same text gets the
    same reference, so a replayed request saves nothing new. The text is
    saved with the recall tool that may read it back: web text comes back
    only through the web-trust tool, whoever else shares the scope."""
    ref = hashlib.sha256(f"{recall_tool}\n{text}".encode()).hexdigest()[:16]
    folder = _run_dir(scope)
    path = folder / f"{ref}.txt"
    if not path.exists():
        folder.mkdir(parents=True, exist_ok=True)
        path.write_text(f"{tool_name}\t{recall_tool}\n{text}")
        _prune(folder.parent)
    return ref


def _prune(root: Path) -> None:
    """Remove the saved results of runs older than KEEP_DAYS, and of chats
    with nothing saved for SESSION_KEEP_DAYS."""
    now = time.time()
    for folder in root.iterdir():
        days = SESSION_KEEP_DAYS if folder.name.startswith("s-") else KEEP_DAYS
        try:
            if folder.is_dir() and folder.stat().st_mtime < now - days * 86_400:
                for f in folder.iterdir():
                    f.unlink()
                folder.rmdir()
        except OSError:
            continue


def recall(scope: str, ref: str, part: int = 1,
           recall_tool: str = "recall_text") -> tuple[str, str, int, int]:
    """(tool name, this part's text, this part's number, how many parts).
    Raises KeyError when the reference is not one saved in this scope for
    this recall tool."""
    if not _REF_RE.match(ref):
        raise KeyError(ref)
    path = _run_dir(scope) / f"{ref}.txt"
    if not path.exists():
        raise KeyError(ref)
    head, _, text = path.read_text().partition("\n")
    tool, _, saved_for = head.partition("\t")
    if saved_for != recall_tool:
        raise KeyError(ref)
    parts = max(1, -(-len(text) // RECALL_CHARS))
    part = min(max(1, part), parts)
    return tool, text[(part - 1) * RECALL_CHARS: part * RECALL_CHARS], part, parts


def _shortened(part: ToolReturnPart, scope: str,
               recall_tool: str = "recall_text") -> ToolReturnPart:
    text = _text(part)
    ref = store(scope, part.tool_name, text, recall_tool)
    note = (f"[{part.tool_name} returned {len(text):,} characters here earlier. To keep this"
            " conversation inside the model's context window, they are saved whole and"
            " only an extract is shown: the start, the headings, and every sentence with a"
            f" number or a comparison. For the whole text call {recall_tool}(ref=\"{ref}\")."
            " Use it before you quote this page or write your final note from it.]\n")
    return dataclasses.replace(part, content=note + extract(text))


def fit(messages: list[ModelMessage], budget: int, scope: str = _PROCESS_SCOPE,
        recall_tool: str = "recall_text") -> list[ModelMessage]:
    """The conversation, with the oldest tool results saved and shortened
    until the estimate is under `budget`. Unchanged when it already fits or
    when `budget` is 0 (a model whose window is not stated)."""
    if budget <= 0:
        return messages
    over = estimate_tokens(messages) - budget
    if over <= 0:
        return messages
    places = [(i, j) for i, m in enumerate(messages) if isinstance(m, ModelRequest)
              for j, p in enumerate(m.parts)
              if isinstance(p, ToolReturnPart) and len(_text(p)) > SHORT_MIN]
    oldest = places[:-KEEP_RECENT] if len(places) > KEEP_RECENT else []
    out = list(messages)
    shortened = 0
    for i, j in oldest:
        if over <= 0:
            break
        request = out[i]
        assert isinstance(request, ModelRequest)
        part = request.parts[j]
        assert isinstance(part, ToolReturnPart)
        new = _shortened(part, scope, recall_tool)
        over -= int((len(_text(part)) - len(_text(new))) / CHARS_PER_TOKEN)
        parts = list(request.parts)
        parts[j] = new
        out[i] = dataclasses.replace(request, parts=parts)
        shortened += 1
    if shortened:
        log.info("context: %d old tool result(s) shortened to fit %d tokens%s", shortened,
                 budget, "" if over <= 0 else f"; still about {over} tokens over")
    return out


def capability(budget: int, recall_tool: str = "recall_text") -> ProcessHistory[Any]:
    """The processor for one agent, bound to its model's input budget and
    to the recall tool that agent holds."""
    def process(ctx: RunContext[Any], messages: list[ModelMessage]) -> list[ModelMessage]:
        return fit(messages, budget, scope(ctx.deps), recall_tool)
    return ProcessHistory(process)
