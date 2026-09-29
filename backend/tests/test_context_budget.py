"""A run's conversation is kept inside its model's context window.

The case is the one that happened: hunter read page after page for Phase 2B,
its request reached 222,886 input tokens, and the gateway refused it."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    ToolReturnPart,
    UserPromptPart,
)
from pydantic_ai.usage import RequestUsage

from hq import context_budget as cb
from hq import llm
from hq.config import settings


@pytest.fixture(autouse=True)
def _store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(settings(), "context_store_dir", tmp_path / "context")
    return tmp_path / "context"

FILLER = "The team wrote about how they run their service and what they like about it. "
FACT = "Chunked prefill cut p99 time to first token from 820 ms to 310 ms at 64 users. "
# One fetched page, about 40,000 tokens: mostly prose, with facts spread through it.
PAGE = ("# Chunked prefill in practice\n" + (FILLER * 40 + FACT) * 36)[:120_000]


def _read(n: int, used: int = 0) -> list:
    call = ToolCallPart(tool_name="web_fetch", args={"url": f"https://a.dev/{n}"},
                        tool_call_id=f"c{n}")
    response = ModelResponse(parts=[call], usage=RequestUsage(input_tokens=used))
    back = ModelRequest(parts=[ToolReturnPart(tool_name="web_fetch", content=PAGE,
                                              tool_call_id=f"c{n}")])
    return [response, back]


def _study(pages: int) -> list:
    messages: list = [ModelRequest(parts=[UserPromptPart(content="Study Phase 2B.")])]
    for n in range(pages):
        messages += _read(n)
    return messages


def test_a_conversation_that_fits_is_not_touched() -> None:
    messages = _study(2)
    assert cb.fit(messages, 190_000) is messages


def test_the_oldest_pages_are_shortened_until_it_fits() -> None:
    messages = _study(6)                    # about 240,000 tokens: the refused size
    assert cb.estimate_tokens(messages) > 190_000
    out = cb.fit(messages, 190_000)
    assert cb.estimate_tokens(out) <= 190_000
    returns = [p for m in out if isinstance(m, ModelRequest) for p in m.parts
               if isinstance(p, ToolReturnPart)]
    assert "saved whole" in returns[0].content and "recall_text(ref=" in returns[0].content
    # What a note is built from survives the shortening.
    assert "820 ms to 310 ms" in returns[0].content
    assert "Chunked prefill in practice" in returns[0].content
    assert len(returns[0].content) < len(PAGE) / 10
    # The newest pages are whole, and every call still has its return.
    assert all(r.content == PAGE for r in returns[-cb.KEEP_RECENT:])
    assert len(returns) == 6 and [r.tool_call_id for r in returns] == [f"c{n}" for n in range(6)]
    # The task and the original list are left as they were.
    assert out[0] is messages[0]
    assert messages[2].parts[0].content == PAGE


def test_the_models_own_count_is_used_when_a_response_gives_it() -> None:
    messages = _study(1)
    messages += [ModelResponse(parts=[TextPart(content="noted")],
                               usage=RequestUsage(input_tokens=150_000))]
    messages += [ModelRequest(parts=[UserPromptPart(content="y" * 3_000)])]
    assert 150_000 < cb.estimate_tokens(messages) < 152_000


def test_no_stated_window_means_no_change() -> None:
    messages = _study(8)
    assert cb.fit(messages, 0) is messages


def test_every_role_has_a_budget_that_leaves_room_for_the_longest_answer() -> None:
    reg = llm.registry()
    for role in ("default", "deep", "teacher", "cheap"):
        budget = reg.input_budget(role)
        assert 0 < budget <= 262_144 - 64_000
        # The refused request would now be shortened before it was sent.
        assert budget < 222_886


def test_every_agent_is_built_with_the_limit() -> None:
    from pydantic_ai.capabilities import ProcessHistory

    from hq.loader import build_agent, scan

    class _Durability:  # stands in for DBOS; only the capability list is read
        pass

    for name, spec in scan().items():
        if spec.runtime != "hq":
            continue
        agent = build_agent(spec, _Durability())  # type: ignore[arg-type]
        caps = agent._root_capability.capabilities  # type: ignore[attr-defined]
        assert any(isinstance(c, ProcessHistory) for c in caps), name


def test_the_extract_keeps_facts_and_drops_filler() -> None:
    text = cb.extract(PAGE)
    assert FACT.strip() in text
    # Filler survives only inside the opening lines that are always kept.
    assert text.count(FILLER.strip()) <= 600 // len(FILLER) + 1
    assert len(text) <= cb.EXTRACT_CHARS + 700


def test_nothing_is_lost_the_whole_page_comes_back_in_parts() -> None:
    out = cb.fit(_study(6), 190_000, "r-run-1")
    stub = next(p for m in out if isinstance(m, ModelRequest) for p in m.parts
                if isinstance(p, ToolReturnPart) and "recall_text" in p.content)
    ref = re.search(r'ref="([0-9a-f]{16})"', stub.content).group(1)
    tool, _first, _n, parts = cb.recall("r-run-1", ref, 1)
    assert tool == "web_fetch" and parts == -(-len(PAGE) // cb.RECALL_CHARS)
    whole = "".join(cb.recall("r-run-1", ref, n)[1] for n in range(1, parts + 1))
    assert whole == PAGE                          # exactly what the tool returned


def test_a_reference_from_another_run_or_a_made_up_one_is_refused() -> None:
    ref = cb.store("r-run-1", "web_fetch", PAGE)
    with pytest.raises(KeyError):
        cb.recall("r-run-2", ref)
    with pytest.raises(KeyError):
        cb.recall("r-run-1", "../../etc/passwd")


def test_web_text_never_comes_back_through_the_vault_tool() -> None:
    # A chat's session is shared with the tasks it delegates, hunter among them.
    ref = cb.store("s-chat", "web_fetch", PAGE, "recall_web_text")
    with pytest.raises(KeyError):
        cb.recall("s-chat", ref, 1, "recall_text")
    assert cb.recall("s-chat", ref, 1, "recall_web_text")[0] == "web_fetch"


def test_a_chat_recalls_in_a_later_turn_what_an_earlier_turn_saved() -> None:
    # Each chat turn is a new run; the shortened history is kept across turns.
    first = SimpleNamespace(session_id="chat-1", run_id="turn-1")
    later = SimpleNamespace(session_id="chat-1", run_id="turn-2")
    out = cb.fit(_study(6), 190_000, cb.scope(first))
    stub = next(p for m in out if isinstance(m, ModelRequest) for p in m.parts
                if isinstance(p, ToolReturnPart) and "recall_text" in p.content)
    ref = re.search(r'ref="([0-9a-f]{16})"', stub.content).group(1)
    assert cb.recall(cb.scope(later), ref)[0] == "web_fetch"
    # A task's run, and a process with neither, each keep their own.
    assert cb.scope(SimpleNamespace(session_id=None, run_id="x")) == "r-x"
    assert cb.scope(SimpleNamespace()).startswith("proc-")


def test_a_replayed_request_saves_the_same_reference() -> None:
    assert cb.store("r-run-1", "web_fetch", PAGE) == cb.store("r-run-1", "web_fetch", PAGE)


def test_the_shortened_page_names_the_tool_the_agent_holds() -> None:
    out = cb.fit(_study(6), 190_000, "r-run-1", recall_tool="recall_web_text")
    stubs = [p.content for m in out if isinstance(m, ModelRequest) for p in m.parts
             if isinstance(p, ToolReturnPart) and "saved whole" in p.content]
    assert stubs and all("recall_web_text(ref=" in c for c in stubs)


def test_the_recall_tool_returns_the_part_and_says_what_is_left() -> None:
    import inspect

    from hq.tools import context_tools as ct

    ref = cb.store("r-run-1", "web_fetch", PAGE, "recall_web_text")
    ctx = SimpleNamespace(deps=SimpleNamespace(run_id="run-1"))
    raw = inspect.unwrap(ct.recall_web_text.fn) if hasattr(ct.recall_web_text, "fn") \
        else inspect.unwrap(ct.recall_web_text)
    text = asyncio.run(raw(ctx, ref, 1))
    assert text.startswith("[web_fetch, saved text") and "part=2" in text
    # part=0 is read as part 1, and the hint names part 2 as the next.
    text = asyncio.run(raw(ctx, ref, 0))
    assert "part 1 of" in text and "part=2" in text


def test_a_web_reader_gets_the_web_recall_and_others_the_vault_one() -> None:
    from hq.loader import build_agent, scan

    class _Durability:
        pass

    for name in ("hunter", "sage", "tutor"):
        agent = build_agent(scan()[name], _Durability())  # type: ignore[arg-type]
        names = set(agent._function_toolset.tools)  # type: ignore[attr-defined]
        if name == "hunter":
            assert "recall_web_text" in names and "recall_text" not in names
        else:
            assert "recall_text" in names and "recall_web_text" not in names
