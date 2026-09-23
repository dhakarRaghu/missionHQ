"""The model-call layer: streamed, bounded, classified, admitted, recorded."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import AsyncIterator
from datetime import datetime
from zoneinfo import ZoneInfo

import httpx
import pytest
from pydantic_ai import Agent
from pydantic_ai.exceptions import ModelHTTPError
from pydantic_ai.models.fallback import FallbackModel
from pydantic_ai.models.function import FunctionModel

from hq import llm


def _entry(name: str, timeout_s: float = 30.0) -> llm.ModelEntry:
    return llm.ModelEntry(name=name, provider="gateway", model_id=f"{name}-id",
                          input_per_mtok=1.0, output_per_mtok=2.0,
                          settings={"timeout_s": timeout_s})


def _streaming(name: str, stream_fn, timeout_s: float = 30.0) -> llm.StreamingModel:
    return llm.StreamingModel(FunctionModel(stream_function=stream_fn, model_name=name),
                              _entry(name, timeout_s))


@pytest.fixture
def calls(monkeypatch) -> list[dict]:
    seen: list[dict] = []

    async def record(**kw) -> None:
        seen.append(kw)

    monkeypatch.setattr(llm, "record_call", record)
    return seen


async def _answers(messages, info) -> AsyncIterator[str]:
    yield "fine"


def _run(model) -> str:
    return str(asyncio.run(Agent(model).run("hello")).output)


def test_every_registry_model_streams_and_classifies_its_failures() -> None:
    model = llm.registry().resolve("teacher")
    assert isinstance(model, FallbackModel)
    assert all(isinstance(m, llm.StreamingModel) for m in model.models)
    assert model.models[0].limit_s == 900.0


def test_a_stream_that_breaks_midway_goes_to_the_spare(calls) -> None:
    """The article run on 2026-09-23 died on a ReadError on every model.
    Streamed, a break after the first byte is a raw httpx error, which the
    fallback chain ignores unless it is rewritten."""
    async def breaks(messages, info) -> AsyncIterator[str]:
        yield "half an answer"
        raise httpx.ReadError("connection dropped")

    out = _run(FallbackModel(_streaming("primary", breaks), _streaming("spare", _answers),
                             fallback_on=llm.moves_to_spare))
    assert out == "fine"
    assert [c["model"] for c in calls] == ["primary", "spare"]
    assert calls[0]["error_class"] == "ReadError" and calls[1]["error_class"] is None
    # Each attempt is priced at the model that made it.
    spare = calls[1]
    assert spare["cost_usd"] == pytest.approx(
        (spare["input_tokens"] * 1.0 + spare["output_tokens"] * 2.0) / 1_000_000)


def test_a_model_that_trickles_is_stopped_by_the_wall_clock(calls) -> None:
    """httpx's read timeout restarts on every byte, so only a wall clock
    stops a model that keeps sending a little."""
    async def trickles(messages, info) -> AsyncIterator[str]:
        for _ in range(100):
            yield "."
            await asyncio.sleep(0.05)

    out = _run(FallbackModel(_streaming("slow", trickles, timeout_s=0.2),
                             _streaming("spare", _answers), fallback_on=llm.moves_to_spare))
    assert out == "fine"
    assert calls[0]["model"] == "slow" and calls[0]["error_class"] == "TimeoutError"
    assert calls[0]["ms"] < 2000
    # It was sending, not silent: the first event arrived long before the
    # limit. That is what tells a slow model from a hung one.
    assert calls[0]["first_token_ms"] is not None and calls[0]["first_token_ms"] < 150


def test_a_context_overflow_is_not_handed_to_a_spare(calls) -> None:
    """A spare with a smaller window only fails again, slower."""
    async def overflows(messages, info) -> AsyncIterator[str]:
        raise ModelHTTPError(400, "primary",
                             body={"message": "maximum context length is 256000 tokens"})
        yield ""  # pragma: no cover

    spare_called = []

    async def spare(messages, info) -> AsyncIterator[str]:
        spare_called.append(1)
        yield "should not happen"

    with pytest.raises(ModelHTTPError):
        _run(FallbackModel(_streaming("primary", overflows), _streaming("spare", spare),
                           fallback_on=llm.moves_to_spare))
    assert not spare_called
    assert calls[0]["error_class"] == "HTTP400"


def test_a_server_error_still_moves_to_the_spare() -> None:
    assert llm.moves_to_spare(ModelHTTPError(503, "m", body="upstream unavailable"))
    assert not llm.moves_to_spare(ModelHTTPError(400, "m", body="prompt is too long"))
    assert not llm.moves_to_spare(ValueError("not a model error"))


def test_the_gateway_never_has_more_requests_open_than_the_key_allows(monkeypatch) -> None:
    """A streamed answer holds its slot until its body closes, not until the
    headers arrive; otherwise two workers and a chat turn overfill the key."""
    state = {"open": 0, "peak": 0}

    class Body(httpx.AsyncByteStream):
        async def __aiter__(self) -> AsyncIterator[bytes]:
            yield b"data: {}\n\n"

        async def aclose(self) -> None:
            state["open"] -= 1

    async def fake(self, request):
        state["open"] += 1
        state["peak"] = max(state["peak"], state["open"])
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
                              stream=Body(), request=request)

    monkeypatch.setattr(httpx.AsyncHTTPTransport, "handle_async_request", fake)

    async def one(transport: llm.GatewayCompatTransport) -> None:
        req = httpx.Request("POST", "https://gw.example/v1/chat/completions", json={})
        resp = await transport.handle_async_request(req)
        await asyncio.sleep(0.01)
        await resp.aclose()

    async def many() -> None:
        transport = llm.GatewayCompatTransport()
        await asyncio.gather(*(one(transport) for _ in range(12)))

    asyncio.run(many())
    assert state["peak"] == llm.settings().gateway_parallel == 5
    assert state["open"] == 0


def test_a_backfilled_cron_slot_is_skipped(monkeypatch) -> None:
    """After a restart DBOS fires every slot it missed at once. Only the
    newest slot of a schedule runs."""
    from hq import engine

    tz = ZoneInfo(llm.settings().cron_tz)
    newest = datetime(2026, 9, 23, 21, 0, tzinfo=tz)

    async def newest_slot(schedule: str) -> str:
        return newest.isoformat()

    dispatched: list[str] = []
    skipped: list[dict] = []

    async def dispatch(**kw) -> None:
        dispatched.append(kw["dedup_key"])

    async def emit(kind, **kw) -> None:
        skipped.append(kw["payload"])

    async def cron_brief(agent: str, prompt: str) -> str:
        return prompt

    monkeypatch.setattr(engine, "_cron_brief_step", cron_brief)
    monkeypatch.setattr(engine, "_newest_slot_step", newest_slot)
    monkeypatch.setattr(engine, "dispatch", dispatch)
    monkeypatch.setattr(engine.runner, "emit_step", emit)
    fire = engine._make_cron("hunter", 0, "Daily job sweep.", "0 21 * * *")
    asyncio.run(fire(datetime(2026, 9, 22, 21, 0, tzinfo=tz), None))
    asyncio.run(fire(newest, None))
    assert dispatched == ["cron:hunter:0:2026-09-23-2100"]
    assert skipped and skipped[0]["slot"] == "2026-09-22 21:00"


def test_runs_are_costed_from_their_calls() -> None:
    """A run answered by a spare, a failed run and an abandoned run all
    spent money; their cost is the sum of their recorded calls."""
    from hq import engine, runner, safety
    from hq.api import rest

    assert "CALLS_SUM" in inspect.getsource(engine._finish_run)
    assert "CALLS_COSTED" in inspect.getsource(engine._cap_overrunning_tasks)
    assert "CALLS_COSTED" in inspect.getsource(rest)
    assert "hq.model_calls" in inspect.getsource(safety.spend_today_usd)
    src = inspect.getsource(runner.execute)
    assert "call_context(" in src
    assert "call_context(" in inspect.getsource(runner.execute_external)
    assert "record_call(" in inspect.getsource(runner.codex_turn_step)


def test_a_silent_stream_is_hung_even_with_a_long_allowance(calls, monkeypatch) -> None:
    """A long total is for models that are sending. Silence is a hang."""
    monkeypatch.setattr(llm, "IDLE_LIMIT_S", 0.1)

    async def silent(messages, info) -> AsyncIterator[str]:
        yield "."
        await asyncio.sleep(5)
        yield "never"

    out = _run(FallbackModel(_streaming("stuck", silent, timeout_s=60),
                             _streaming("spare", _answers), fallback_on=llm.moves_to_spare))
    assert out == "fine"
    assert calls[0]["error_class"] == "StreamIdle" and calls[0]["ms"] < 2000


def test_a_caller_can_give_one_call_a_longer_total() -> None:
    model = _streaming("m", _answers, timeout_s=300)
    assert model.total_limit_s(None) == 300
    assert model.total_limit_s({"timeout": 900}) == 900


def test_a_failed_attempt_is_costed_at_its_prompt() -> None:
    from pydantic_ai.messages import ModelRequest, UserPromptPart

    from hq import llm

    msgs = [ModelRequest(parts=[UserPromptPart("x" * 4000)])]
    sent, got = llm._estimated_tokens(msgs, None)
    assert sent >= 1000 and got == 0
