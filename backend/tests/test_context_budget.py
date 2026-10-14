"""A run's conversation is kept inside its model's context window.

The case is the one that happened: hunter read page after page for Phase 2B,
its request reached 222,886 input tokens, and the gateway refused it."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from dbos._error import DBOSMaxStepRetriesExceeded
from pydantic_ai.exceptions import ModelHTTPError
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


# One page under the size any single result may be sent at: about 20,000 tokens.
SMALL = PAGE[:50_000]


def _read(n: int, used: int = 0, page: str = PAGE) -> list:
    call = ToolCallPart(tool_name="web_fetch", args={"url": f"https://a.dev/{n}"},
                        tool_call_id=f"c{n}")
    response = ModelResponse(parts=[call], usage=RequestUsage(input_tokens=used))
    back = ModelRequest(parts=[ToolReturnPart(tool_name="web_fetch", content=page,
                                              tool_call_id=f"c{n}")])
    return [response, back]


def _study(pages: int, page: str = PAGE) -> list:
    messages: list = [ModelRequest(parts=[UserPromptPart(content="Study Phase 2B.")])]
    for n in range(pages):
        messages += _read(n, page=page)
    return messages


def _returns(messages: list) -> list[ToolReturnPart]:
    return [p for m in messages if isinstance(m, ModelRequest) for p in m.parts
            if isinstance(p, ToolReturnPart)]


def test_a_conversation_that_fits_is_not_touched() -> None:
    messages = _study(2, SMALL)
    assert cb.fit(messages, 190_000) is messages


def test_the_oldest_pages_are_shortened_until_it_fits() -> None:
    messages = _study(18, SMALL)            # about 240,000 tokens: the refused size
    assert cb.estimate_tokens(messages) > 190_000
    out = cb.fit(messages, 190_000)
    assert cb.estimate_tokens(out) <= 190_000
    returns = _returns(out)
    assert "saved whole" in returns[0].content and "recall_text(ref=" in returns[0].content
    # What a note is built from survives the shortening.
    assert "820 ms to 310 ms" in returns[0].content
    assert "Chunked prefill in practice" in returns[0].content
    assert len(returns[0].content) < len(SMALL) / 5
    # The newest pages are whole, and every call still has its return.
    assert returns[-1].content == SMALL and returns[-2].content == SMALL
    assert len(returns) == 18 and [r.tool_call_id for r in returns] == [f"c{n}" for n in range(18)]
    # The task and the original list are left as they were.
    assert out[0] is messages[0]
    assert messages[2].parts[0].content == SMALL


def _batch(*pages: str) -> list:
    """A reply that calls several tools at once, and their results in one request."""
    calls = [ToolCallPart(tool_name="fetch_source", args={"url": f"https://p.dev/{n}"},
                          tool_call_id=f"b{n}") for n in range(len(pages))]
    backs = [ToolReturnPart(tool_name="fetch_source", tool_call_id=f"b{n}",
                            content={"url": f"https://p.dev/{n}", "text": page})
             for n, page in enumerate(pages)]
    return [ModelResponse(parts=calls, usage=RequestUsage(input_tokens=39_204)),
            ModelRequest(parts=backs)]


# A PyPI JSON page, as fetch_source returned it for a version number: almost
# all of it every file of every release.
PYPI = '{"info":{"name":"uvicorn","version":"0.37.0"},"releases":{' + ",".join(
    f'"0.{n}.0":[{{"filename":"uvicorn-0.{n}.0.tar.gz","sha256":"{n:064x}"}}]'
    for n in range(2_000)) + "}}"


def test_big_results_stay_whole_while_the_conversation_fits() -> None:
    # Content first: nothing is cut or shortened that the window can hold.
    messages = [ModelRequest(parts=[UserPromptPart(content="Study Phase 1A.")])]
    messages += _batch(PYPI, PAGE)
    assert cb.fit(messages, 190_000, "r-run-1") is messages


def test_a_batch_of_huge_new_results_is_cut_when_it_does_not_fit() -> None:
    # 2026-10-13: three PyPI pages in one batch. The newest results were never
    # shortened, so nothing could bring the request under the window.
    messages = [ModelRequest(parts=[UserPromptPart(content="Study Phase 1A.")])]
    messages += _batch(PYPI, PYPI + " ", PYPI + "  ")
    assert cb.estimate_tokens(messages) > 190_000
    out = cb.fit(messages, 190_000, "r-run-1", "recall_web_text")
    assert cb.estimate_tokens(out) <= 190_000
    returns = [r for r in _returns(out) if "part 1 of" in r.content]
    assert returns
    for r in returns:
        assert len(r.content) <= cb.RESULT_MAX_CHARS
        assert r.content.startswith("[fetch_source returned")
        # An outline of the rest says what each later part holds.
        assert "part 2: starts" in r.content
        # The version the agent fetched it for is in the part it keeps.
        assert '\\"version\\":\\"0.37.0\\"' in r.content
    # The whole page comes back in parts, exactly as the model would have seen it.
    sent = {p.tool_call_id: p.model_response_str() for p in _returns(messages)}
    for r in returns:
        ref = re.search(r'ref="([0-9a-f]{16})"', r.content).group(1)
        _tool, _text, _n, parts = cb.recall("r-run-1", ref, 1, "recall_web_text")
        whole = "".join(cb.recall("r-run-1", ref, n, "recall_web_text")[1]
                        for n in range(1, parts + 1))
        assert whole == sent[r.tool_call_id]
    # Cutting is done once: the next request sends the same text.
    assert cb.fit(out, 190_000, "r-run-1", "recall_web_text") is out


def test_the_newest_results_are_shortened_too_when_nothing_older_is_left() -> None:
    messages = [ModelRequest(parts=[UserPromptPart(content="Study Phase 1A.")])]
    messages += _batch(SMALL, SMALL + " ", SMALL + "  ", SMALL + "   ")
    out = cb.fit(messages, 40_000, "r-run-1")
    assert cb.estimate_tokens(out) <= 50_000
    assert any("saved whole" in r.content for r in _returns(out))


def test_a_cut_result_shortened_later_points_at_the_whole() -> None:
    messages = [ModelRequest(parts=[UserPromptPart(content="Study.")])] + _batch(PAGE * 2)
    first = cb.fit(messages, 39_204 + 30_000, "r-run-1")
    assert "part 1 of" in _returns(first)[0].content
    cut_ref = re.search(r'ref="([0-9a-f]{16})"', _returns(first)[0].content).group(1)
    later = cb.fit(first, 5_000, "r-run-1")
    stub = _returns(later)[0].content
    assert "here earlier" in stub and f'ref="{cut_ref}"' in stub
    assert f"returned {len(_returns(messages)[0].model_response_str()):,} characters" in stub


def test_length_is_what_the_model_is_sent() -> None:
    quoted = '{"a":"b"}' * 1_000
    part = _batch(quoted)[1].parts[0]
    assert cb._text(part) == part.model_response_str()
    assert len(cb._text(part)) > len(quoted) * 1.3      # every quote escaped


def _refusal(text: str) -> ModelHTTPError:
    return ModelHTTPError(400, "kimi-latest", {"message": f"litellm.ContextWindowExceededError: {text}"})


def test_the_gateways_count_is_read_from_either_wording() -> None:
    assert llm.overflow_input_tokens(_refusal(
        "The input (295561 tokens) is longer than the model's context length (262144 tokens)."
    )) == 295_561
    assert llm.overflow_input_tokens(_refusal(
        "You requested a total of 263874 tokens: 199874 tokens from the input messages and"
        " 64000 tokens for the completion.")) == 199_874
    wrapped = DBOSMaxStepRetriesExceeded("hq-hunter__model.request", 2, [_refusal(
        "The input (295561 tokens) is longer than the model's context length")])
    assert cb.overflow_count(wrapped) == 295_561
    assert cb.overflow_count(RuntimeError("connection reset")) is False


def test_a_refusal_for_length_recalibrates_and_is_sent_once_more() -> None:
    # The second 2026-10-13 run: we estimated under 190,144, the gateway
    # counted 199,874 and refused; it was retried unchanged and the run lost.
    messages = [ModelRequest(parts=[UserPromptPart(content="Study Phase 1A.")])]
    messages += _batch(SMALL, SMALL + " ", SMALL + "  ", SMALL + "   ")
    messages[1].usage = RequestUsage(input_tokens=165_000)
    deps = SimpleNamespace(session_id=None, run_id="run-refused")
    budget = cb.ContextBudget(190_000, "recall_web_text")
    sent: list[int] = []

    async def handler(request_context):  # the gateway, counting 25% more than the tokenizer
        used, after = cb._measure(request_context.messages)
        counted = int(used + after * 1.25)
        sent.append(counted)
        if counted > 190_000:
            raise _refusal(f"The input ({counted} tokens) is longer than the model's"
                           " context length (262144 tokens).")
        return ModelResponse(parts=[TextPart(content="ok")])

    ctx = SimpleNamespace(deps=deps)
    request = SimpleNamespace(messages=messages)
    request = asyncio.run(budget.before_model_request(ctx, request))
    response = asyncio.run(budget.wrap_model_request(ctx, request_context=request,
                                                     handler=handler))
    assert response.parts[0].content == "ok"
    assert len(sent) == 2 and sent[0] > 190_000 >= sent[1]
    # The run keeps the lesson: its next request is fitted to the gateway's count.
    assert cb.scale("r-run-refused") > 1.25
    assert cb.fit(messages, 190_000, "r-run-refused") is not messages


def test_a_refusal_with_an_exact_count_and_window_shortens_only_what_it_must() -> None:
    # The real refusal: 199,874 counted against 262,144 less 64,000 kept for the answer.
    messages = [ModelRequest(parts=[UserPromptPart(content="Study.")])]
    messages += _batch(SMALL, SMALL + " ", SMALL + "  ", SMALL + "   ")
    messages[1].usage = RequestUsage(input_tokens=150_000)
    used, after = cb._measure(messages)
    assert used + int(after * 1.2) > 198_144                     # what was refused
    learned = cb.learn("r-exact", messages, used + int(after * 1.2), 190_144, 198_144)
    assert 1.2 < learned.scale < 1.3
    assert learned.limit == int(198_144 * cb.LIMIT_MARGIN)      # not cut a further 15%
    assert cb._budget("r-exact", 190_144) == 190_144             # ours was already lower


def test_a_refusal_that_looked_inside_every_limit_is_sent_smaller() -> None:
    # No count, no window, and our estimate said it fitted: unchanged, it is refused again.
    messages = [ModelRequest(parts=[UserPromptPart(content="Study.")])] + _batch(SMALL)
    first = cb.estimate_tokens(messages)
    learned = cb.learn("r-blind", messages, None, 190_000)
    assert learned.scale == 1.25
    assert cb._budget("r-blind", 190_000) <= cb.estimate_tokens(messages, 1.25) * cb.REFUSED_SHARE
    assert cb._budget("r-blind", 190_000) < first * 1.25


def test_the_window_is_read_from_the_refusal() -> None:
    assert llm.overflow_input_limit(_refusal(
        "The input (295561 tokens) is longer than the model's context length (262144 tokens)."
    )) == 262_144
    assert llm.overflow_input_limit(_refusal(
        "Requested token count exceeds the model's maximum context length of 262144 tokens."
        " You requested a total of 263874 tokens: 199874 tokens from the input messages and"
        " 64000 tokens for the completion.")) == 198_144
    assert llm.overflow_input_limit(_refusal("prompt is too long")) is None


def test_any_other_failure_is_not_caught() -> None:
    budget = cb.ContextBudget(190_000)

    async def handler(_request_context):
        raise RuntimeError("connection reset")

    ctx = SimpleNamespace(deps=SimpleNamespace(session_id=None, run_id="r"))
    with pytest.raises(RuntimeError):
        asyncio.run(budget.wrap_model_request(
            ctx, request_context=SimpleNamespace(messages=[]), handler=handler))


def test_a_refusal_for_length_is_not_retried_by_the_step_nor_handed_to_a_spare() -> None:
    refused = _refusal("The input (295561 tokens) is longer than the model's context length")
    assert llm.is_context_overflow(refused) and not llm.moves_to_spare(refused)
    from hq.engine import friendly_error

    assert friendly_error(refused) == "the conversation outgrew the model's context window"


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
    from hq.loader import build_agent, scan

    class _Durability:  # stands in for DBOS; only the capability list is read
        pass

    for name, spec in scan().items():
        if spec.runtime != "hq":
            continue
        agent = build_agent(spec, _Durability())  # type: ignore[arg-type]
        caps = agent._root_capability.capabilities  # type: ignore[attr-defined]
        assert any(isinstance(c, cb.ContextBudget) and c.budget > 0 for c in caps), name


def test_the_extract_keeps_facts_and_drops_filler() -> None:
    text = cb.extract(PAGE)
    assert FACT.strip() in text
    # Filler survives only inside the opening lines that are always kept.
    assert text.count(FILLER.strip()) <= 600 // len(FILLER) + 1
    assert len(text) <= cb.EXTRACT_CHARS + 700


def test_nothing_is_lost_the_whole_page_comes_back_in_parts() -> None:
    out = cb.fit(_study(18, SMALL), 190_000, "r-run-1")
    stub = next(p for m in out if isinstance(m, ModelRequest) for p in m.parts
                if isinstance(p, ToolReturnPart) and "recall_text" in p.content)
    ref = re.search(r'ref="([0-9a-f]{16})"', stub.content).group(1)
    tool, _first, _n, parts = cb.recall("r-run-1", ref, 1)
    assert tool == "web_fetch" and parts == -(-len(SMALL) // cb.RECALL_CHARS)
    whole = "".join(cb.recall("r-run-1", ref, n)[1] for n in range(1, parts + 1))
    assert whole == SMALL                         # exactly what the tool returned


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
    out = cb.fit(_study(18, SMALL), 190_000, cb.scope(first))
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
    out = cb.fit(_study(18, SMALL), 190_000, "r-run-1", recall_tool="recall_web_text")
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
