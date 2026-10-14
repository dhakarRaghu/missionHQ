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

That was not enough on 2026-10-13: hunter studied Phase 1A twice and was
refused twice. It fetched three PyPI JSON pages for a version number each
(118k to 233k characters, nearly all of it every file of every release) in
one batch of calls. The newest results were never shortened, so nothing
could bring the first run under the window; in the second the estimate said
190,000 tokens and the gateway counted 199,874, because a flat three
characters a token is wrong for JSON, and the length was taken before the
result was serialized. The refusal was then retried unchanged, and the run
was lost. So now:

- tokens are counted with a real tokenizer on the text the model is sent:
  JSON runs 2.5 characters a token, Python 4.4, and one flat ratio either
  overflowed on the first or shortened good pages early on the second;
- nothing changes while the conversation fits. Content comes first: he
  said on 2026-10-13 "i don't want to compromise with content quality";
- when it does not fit, a result too long to send whole is cut to its
  first part (the biggest first, the newest too), with an outline of the
  rest; then results are shortened to extracts, oldest first;
- a refusal for length is recalibrated on the gateway's own count, fitted
  again and sent once more, instead of retried unchanged.
"""

from __future__ import annotations

import asyncio
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
from pydantic_ai.capabilities import AbstractCapability, WrapModelRequestHandler
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    ToolReturnPart,
)
from pydantic_ai.models import ModelRequestContext

log = logging.getLogger(__name__)

# Characters per token when the tokenizer cannot be loaded: JSON's ratio,
# the lowest of what agents read, so a guess errs on the side of room.
CHARS_PER_TOKEN = 2.5
# The instructions and the tool schemas are sent with every request but are
# not in the message list. This is room for them before any response exists.
INSTRUCTIONS_TOKENS = 12_000
EXTRACT_CHARS = 6_000        # what a shortened result keeps: about 2,000 tokens
SHORT_MIN = 2 * EXTRACT_CHARS  # a result shorter than this is left whole

RECALL_CHARS = 50_000         # one part of a recalled text: 12,000 to 20,000 tokens
# When the conversation does not fit, a result longer than this is cut to its
# first recall part before anything is shortened to an extract. Above
# RECALL_CHARS, so a recalled part, with its header, is never cut again.
RESULT_MAX_CHARS = 60_000
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
    if isinstance(part, ToolReturnPart):
        return part.model_response_str()  # what the model is sent: a dict as JSON
    for name in ("content", "args"):
        value = getattr(part, name, None)
        if value is not None:
            return value if isinstance(value, str) else str(value)
    return ""


# kimi's own tokenizer is not published for local use. o200k counted the
# 2026-10-13 batch (two PyPI JSON pages, two source files) at 135,989 tokens
# where kimi counted about 125,000: 8% over, which is room, not waste.
_ENCODING = "o200k_base"
_encoder: Any = None


def _tokens(text: str) -> int:
    global _encoder
    if _encoder is None:
        from hq.config import REPO_DIR

        # tiktoken downloads the encoding once (18 seconds); kept in data/,
        # not in a temp folder a reboot empties.
        os.environ.setdefault("TIKTOKEN_CACHE_DIR", str(REPO_DIR / "data" / "tiktoken"))
        try:
            import tiktoken

            _encoder = tiktoken.get_encoding(_ENCODING)
        except Exception as exc:  # noqa: BLE001 — no network: estimate from length
            log.warning("context: tokenizer %s unavailable (%s); estimating %.1f"
                        " characters a token", _ENCODING, exc, CHARS_PER_TOKEN)
            _encoder = False
    if _encoder is False:
        return int(len(text) / CHARS_PER_TOKEN)
    return len(_encoder.encode(text, disallowed_special=()))


def _part_tokens(message: ModelMessage) -> int:
    return sum(_tokens(_text(p)) for p in message.parts)


def _measure(messages: Sequence[ModelMessage]) -> tuple[int, int]:
    """(tokens the model counted, tokens added since, by the tokenizer). The
    newest response that reports its usage gives the count up to that point."""
    for at in range(len(messages) - 1, -1, -1):
        m = messages[at]
        used = getattr(getattr(m, "usage", None), "input_tokens", 0) or 0
        if isinstance(m, ModelResponse) and used:
            return used, sum(_part_tokens(x) for x in messages[at:])
    return INSTRUCTIONS_TOKENS, sum(_part_tokens(m) for m in messages)


def estimate_tokens(messages: Sequence[ModelMessage], scale: float = 1.0) -> int:
    """What the next request will carry: the model's last count, and what
    was added since, counted and multiplied by the run's `scale`."""
    used, after = _measure(messages)
    return int(used + after * scale)


@dataclasses.dataclass
class _Learned:
    """What a refusal for length taught one scope: how much more the gateway
    counts than the tokenizer, and the most input it takes (0: not known)."""

    scale: float = 1.0
    limit: int = 0


# Kept for the life of the process; a chat that comes back after a restart
# starts afresh, which costs it at most one refusal.
_LEARNED: dict[str, _Learned] = {}
_LEARNED_MAX = 512
# A request refused for length when it already looked inside every limit we
# know is sent again at most this share of its size: the refusal proves a
# limit we do not know.
REFUSED_SHARE = 0.85
# Kept under a window the refusal stated, for the tokenizer's error.
LIMIT_MARGIN = 0.96


def scale(scope: str) -> float:
    learned = _LEARNED.get(scope)
    return learned.scale if learned else 1.0


def _budget(scope: str, budget: int) -> int:
    """`budget`, or less where a refusal taught `scope` a lower limit."""
    learned = _LEARNED.get(scope)
    return min(budget, learned.limit) if learned and learned.limit else budget


def learn(scope: str, messages: Sequence[ModelMessage], counted: int | None,
          budget: int, limit: int | None = None) -> _Learned:
    """Recalibrate `scope` on a refusal of `messages` for length, so that
    they, and every request after them, are fitted to what the gateway takes.

    The scale becomes the gateway's `counted` tokens over our count, and 5%
    more (a quarter more without a count); never less than before. The limit
    becomes the `limit` the refusal stated, less LIMIT_MARGIN. If the refused
    request still looks inside both, a resend would go unchanged and be
    refused again, so the limit becomes REFUSED_SHARE of its size."""
    used, after = _measure(messages)
    learned = _LEARNED.pop(scope, None) or _Learned()
    if counted and counted > used and after:
        learned.scale = max(learned.scale, (counted - used) / after * 1.05)
    else:
        learned.scale *= 1.25
    if limit:
        learned.limit = min(learned.limit or limit, int(limit * LIMIT_MARGIN))
    refused = int(used + after * learned.scale)
    if refused <= (min(budget, learned.limit) if learned.limit else budget):
        learned.limit = int(refused * REFUSED_SHARE)
    _LEARNED[scope] = learned
    while len(_LEARNED) > _LEARNED_MAX:
        _LEARNED.pop(next(iter(_LEARNED)))
    return learned


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


# A result already cut to its first part names the saved whole; shortening it
# further points at that whole, not at the cut copy.
_CUT_RE = re.compile(r'^\[(?P<tool>\S+) returned (?P<n>[\d,]+) characters, more than one'
                     r'.*?ref="(?P<ref>[0-9a-f]{16})"', re.DOTALL)


def _outline(text: str, part: int) -> str:
    """One line for one later part: how it begins and the headings in it."""
    body = text[(part - 1) * RECALL_CHARS: part * RECALL_CHARS]
    start = " ".join(body[:120].split())
    heads = [" ".join(m.group(0).split()) for m in _HEADING_RE.finditer(body)][:4]
    return f"part {part}: starts \"{start}\"" + (f"; headings: {' | '.join(heads)}" if heads else "")


def _cut(part: ToolReturnPart, scope: str, recall_tool: str = "recall_text") -> ToolReturnPart:
    """A result too long to keep whole: saved, its first part kept, and an
    outline of the rest so the agent can read the parts it needs."""
    text = _text(part)
    ref = store(scope, part.tool_name, text, recall_tool)
    parts = -(-len(text) // RECALL_CHARS)
    rest = "\n".join(_outline(text, n) for n in range(2, parts + 1))
    note = (f"[{part.tool_name} returned {len(text):,} characters, more than one result may"
            f" carry. They are saved whole; this is part 1 of {parts}. Read any other part"
            f" with {recall_tool}(ref=\"{ref}\", part=N), and read every part you quote"
            f" or take a number from. The rest:\n{rest}]\n")
    return dataclasses.replace(part, content=note + text[:RECALL_CHARS])


def _shortened(part: ToolReturnPart, scope: str,
               recall_tool: str = "recall_text") -> ToolReturnPart:
    text = _text(part)
    cut = _CUT_RE.match(text[:1_000])
    if cut:
        ref, size = cut["ref"], int(cut["n"].replace(",", ""))
        text = text.partition("]\n")[2]
    else:
        ref, size = store(scope, part.tool_name, text, recall_tool), len(text)
    note = (f"[{part.tool_name} returned {size:,} characters here earlier. To keep this"
            " conversation inside the model's context window, they are saved whole and"
            " only an extract is shown: the start, the headings, and every sentence with a"
            f" number or a comparison. For the whole text call {recall_tool}(ref=\"{ref}\")."
            " Use it before you quote this page or write your final note from it.]\n")
    return dataclasses.replace(part, content=note + extract(text))


def _replace(out: list[ModelMessage], i: int, j: int, new: ToolReturnPart) -> None:
    request = out[i]
    assert isinstance(request, ModelRequest)
    parts = list(request.parts)
    parts[j] = new
    out[i] = dataclasses.replace(request, parts=parts)


def fit(messages: list[ModelMessage], budget: int, scope: str = _PROCESS_SCOPE,
        recall_tool: str = "recall_text") -> list[ModelMessage]:
    """The conversation, unchanged while it fits `budget` (and when `budget`
    is 0: a model whose window is not stated). Otherwise, until it fits:
    results over RESULT_MAX_CHARS are cut to their first part, the biggest
    first; then results are shortened to extracts, oldest first and the
    newest last."""
    if budget <= 0:
        return messages
    budget = _budget(scope, budget)
    ratio = scale(scope)
    over = estimate_tokens(messages, ratio) - budget
    if over <= 0:
        return messages
    returns = [(i, j) for i, m in enumerate(messages) if isinstance(m, ModelRequest)
               for j, p in enumerate(m.parts) if isinstance(p, ToolReturnPart)]
    out = list(messages)

    def part_at(i: int, j: int) -> ToolReturnPart:
        part = out[i].parts[j]
        assert isinstance(part, ToolReturnPart)
        return part

    def swap(i: int, j: int, new: ToolReturnPart) -> None:
        nonlocal over
        over -= int((_tokens(_text(part_at(i, j))) - _tokens(_text(new))) * ratio)
        _replace(out, i, j, new)

    biggest = sorted((ij for ij in returns if len(_text(part_at(*ij))) > RESULT_MAX_CHARS),
                     key=lambda ij: -len(_text(part_at(*ij))))
    cut = shortened = 0
    for i, j in biggest:
        if over <= 0:
            break
        swap(i, j, _cut(part_at(i, j), scope, recall_tool))
        cut += 1
    for i, j in returns:
        if over <= 0:
            break
        if len(_text(part_at(i, j))) > SHORT_MIN:
            swap(i, j, _shortened(part_at(i, j), scope, recall_tool))
            shortened += 1
    log.info("context: %d result(s) cut to their first part and %d shortened to fit %d"
             " tokens%s", cut, shortened, budget,
             "" if over <= 0 else f"; still about {over} tokens over")
    return out


def overflow_count(exc: BaseException) -> int | bool:
    """For a refusal for length anywhere in `exc` (a fallback chain or a step
    wraps it): the input tokens the gateway counted, or True when it did not
    say. False for any other failure."""
    refusal = _refusal(exc)
    if refusal is None:
        return False
    from hq import llm

    return llm.overflow_input_tokens(refusal) or True


def _refusal(exc: BaseException) -> BaseException | None:
    from hq import llm

    seen: list[BaseException] = [exc]
    while seen:
        e = seen.pop()
        if llm.is_context_overflow(e):
            return e
        seen += [x for x in (e.__cause__, e.__context__) if x is not None]
        seen += [x for x in getattr(e, "exceptions", ()) or getattr(e, "errors", ())
                 if isinstance(x, BaseException)]
    return None


@dataclasses.dataclass
class ContextBudget(AbstractCapability[Any]):
    """Keeps one agent's requests inside its model's window. Before each
    request the conversation is fitted (`fit`); a request refused for length
    anyway recalibrates the run (`learn`) and is fitted and sent once more."""

    budget: int
    recall_tool: str = "recall_text"

    async def before_model_request(self, ctx: RunContext[Any],
                                   request_context: ModelRequestContext) -> ModelRequestContext:
        # Off the event loop: counting and saving a long conversation takes
        # a moment, and the first count may download the tokenizer.
        request_context.messages = await asyncio.to_thread(
            fit, request_context.messages, self.budget, scope(ctx.deps), self.recall_tool)
        return request_context

    async def wrap_model_request(self, ctx: RunContext[Any], *,
                                 request_context: ModelRequestContext,
                                 handler: WrapModelRequestHandler) -> ModelResponse:
        try:
            return await handler(request_context)
        except Exception as exc:
            counted = overflow_count(exc)
            if counted is False or self.budget <= 0:
                raise
            from hq import llm

            where = scope(ctx.deps)
            before = estimate_tokens(request_context.messages, scale(where))
            refusal = _refusal(exc) or exc
            learned = learn(where, request_context.messages,
                            None if counted is True else int(counted), self.budget,
                            llm.overflow_input_limit(refusal))
            request_context.messages = await asyncio.to_thread(
                fit, request_context.messages, self.budget, where, self.recall_tool)
            log.warning("context: refused for length (we estimated %d, the gateway counted %s);"
                        " counting %.2fx and fitting to %d tokens from now, sending %d once"
                        " more", before, "?" if counted is True else counted, learned.scale,
                        _budget(where, self.budget),
                        estimate_tokens(request_context.messages, learned.scale))
            return await handler(request_context)


def capability(budget: int, recall_tool: str = "recall_text") -> ContextBudget:
    """The capability for one agent, bound to its model's input budget and
    to the recall tool that agent holds."""
    return ContextBudget(budget, recall_tool)
