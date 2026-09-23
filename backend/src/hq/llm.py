"""Model registry.

models.yaml is the only place a provider or model id is named. Code refers to
models by registry NAME (or role alias). Pricing from the yaml is the source of
truth for cost accounting; auto-pricing cannot price gateway-aliased ids.
"""

from __future__ import annotations

import asyncio
import contextlib
import contextvars
import json
import logging
import re
import time
import weakref
from collections.abc import AsyncIterator, Callable, Iterator
from dataclasses import dataclass
from typing import Any

import httpx
import openai
import yaml
from openai import AsyncOpenAI
from pydantic_ai.exceptions import ModelAPIError, ModelHTTPError
from pydantic_ai.messages import ModelMessage, ModelResponse, TextPart
from pydantic_ai.models import Model, ModelRequestParameters
from pydantic_ai.models.wrapper import WrapperModel
from pydantic_ai.settings import ModelSettings

from hq.config import settings

log = logging.getLogger(__name__)


# A 429 from the gateway means its five-request slot table is full, not that
# the model is broken. The right response is to wait for a slot. It used to be
# handled by DBOS step retries, which forced four attempts per model step; the
# same four attempts then made a HUNG request cost four full timeouts, about an
# hour of a silent run holding the only worker on its lane. Waiting for a slot
# here lets the step retry only what is worth retrying.
SLOT_WAITS_S = (5.0, 10.0, 20.0, 40.0)

# One slot limit per event loop. The backend has exactly one loop (DBOS
# adopts uvicorn's when it launches inside the FastAPI lifespan), so in
# production this is one semaphore for every chat, judge, reader, embedding
# and agent call on the key. Tests open a loop each; keying by loop keeps a
# semaphore from being used on a loop it was not created on.
_slot_limits: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = (
    weakref.WeakKeyDictionary()
)


def _slot_limit() -> asyncio.Semaphore:
    loop = asyncio.get_running_loop()
    sem = _slot_limits.get(loop)
    if sem is None:
        sem = _slot_limits[loop] = asyncio.Semaphore(max(1, settings().gateway_parallel))
    return sem


class _SlotHeldStream(httpx.AsyncByteStream):
    """A response body that keeps its gateway slot until it is read or closed.

    A streamed answer returns its headers at once and then sends tokens for
    minutes. Releasing the slot when the headers arrived would let the
    backend open far more requests than the key allows.
    """

    def __init__(self, inner: httpx.AsyncByteStream, release: Callable[[], None]) -> None:
        self._inner = inner
        self._release = release

    async def __aiter__(self) -> AsyncIterator[bytes]:
        try:
            async for chunk in self._inner:
                yield chunk
        finally:
            self._release()

    async def aclose(self) -> None:
        try:
            await self._inner.aclose()
        finally:
            self._release()


class GatewayCompatTransport(httpx.AsyncHTTPTransport):
    """Admits at most ``gateway_parallel`` requests at once, waits out a full
    slot table, and drops vendor extras the OpenAI schema rejects.

    Grid proxies several backends, and some (Kimi) attach a ``metadata`` object
    whose ``weight_versions`` is a list. The OpenAI SDK types ``metadata`` as
    ``dict[str, str]`` and raises on the whole response. The field carries
    nothing we use, so it is removed before parsing. Streaming responses pass
    through untouched, holding their slot until the body is closed.
    """

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        slots = _slot_limit()
        await slots.acquire()
        held = True

        def release() -> None:
            nonlocal held
            if held:
                held = False
                slots.release()

        try:
            return await self._send(request, release)
        except BaseException:
            release()
            raise

    async def _send(self, request: httpx.Request, release: Callable[[], None]) -> httpx.Response:
        response = await super().handle_async_request(request)
        for wait in SLOT_WAITS_S:
            if response.status_code != 429:
                break
            try:
                wait = max(wait, float(response.headers.get("retry-after", "")))
            except ValueError:
                pass
            await response.aclose()
            log.info("gateway slot table full (429); waiting %.0fs", wait)
            await asyncio.sleep(min(wait, 60.0))
            response = await super().handle_async_request(request)
        if "application/json" not in response.headers.get("content-type", ""):
            response.stream = _SlotHeldStream(response.stream, release)  # type: ignore[arg-type]
            return response
        try:
            await response.aread()
        finally:
            release()
        try:
            payload = json.loads(response.content)
        except ValueError:
            return response
        if not isinstance(payload, dict) or "metadata" not in payload:
            return response
        payload.pop("metadata", None)
        headers = {
            k: v
            for k, v in response.headers.items()
            if k.lower() not in {"content-length", "content-encoding"}
        }
        return httpx.Response(
            response.status_code,
            headers=headers,
            content=json.dumps(payload).encode(),
            request=request,
            extensions=response.extensions,
        )


# --- model calls: streamed, bounded, classified, recorded ---------------------

# Who a model call belongs to. Set by the runner around a run; every call
# made inside it (the agent's, the judges', the web reader's) inherits it,
# because asyncio tasks copy the context they are created in.
CALL_CONTEXT: contextvars.ContextVar[dict[str, str | None] | None] = contextvars.ContextVar(
    "hq_call_context", default=None
)


@contextlib.contextmanager
def call_context(*, run_id: str | None, task_id: str | None, agent: str | None) -> Iterator[None]:
    token = CALL_CONTEXT.set({"run_id": run_id, "task_id": task_id, "agent": agent})
    try:
        yield
    finally:
        CALL_CONTEXT.reset(token)


# A prompt too long for the model's window. Handing it to a spare with a
# smaller window only fails again, slower, and hides the real problem.
_OVERFLOW_RE = re.compile(
    r"context[ _-]?(length|window)|maximum context|too many tokens|prompt is too long"
    r"|input is too long|ContextWindowExceeded",
    re.IGNORECASE,
)


def is_context_overflow(exc: BaseException) -> bool:
    if not isinstance(exc, ModelHTTPError) or exc.status_code not in (400, 413, 422):
        return False
    return bool(_OVERFLOW_RE.search(f"{exc.message} {exc.body}"))


def moves_to_spare(exc: Exception) -> bool:
    """Which failures hand the request to the next model in the chain.

    A timeout, a dropped stream, a gateway 5xx or a 429 that outlasted the
    slot waits: yes. A context overflow: no.
    """
    return isinstance(exc, ModelAPIError) and not is_context_overflow(exc)


def _estimated_tokens(messages: list[ModelMessage], response: ModelResponse | None) -> tuple[int, int]:
    """About four characters a token, for the rare stream that sends no usage."""
    sent = sum(len(str(m)) for m in messages) // 4
    got = 0
    if response is not None:
        got = sum(len(p.content) for p in response.parts if isinstance(p, TextPart)) // 4
    return sent, got


async def record_call(
    *, model: str, model_id: str, ms: int, input_tokens: int, output_tokens: int,
    cache_read_tokens: int = 0, cost_usd: float, error_class: str | None,
    usage_source: str = "reported", first_token_ms: int | None = None,
) -> None:
    """One row in hq.model_calls. Never raises: a failed write must not turn
    a good answer into a failed step."""
    ctx = CALL_CONTEXT.get() or {}
    try:
        from hq import db

        # started_at is when the attempt began, not when this row is written.
        await db.execute(
            "INSERT INTO hq.model_calls (run_id, task_id, agent, model, model_id,"
            " started_at, ms, first_token_ms, input_tokens, output_tokens,"
            " cache_read_tokens, cost_usd, error_class, usage_source)"
            " VALUES (%s,%s,%s,%s,%s, now() - make_interval(secs => %s),"
            " %s,%s,%s,%s,%s,%s,%s,%s)",
            (ctx.get("run_id"), ctx.get("task_id"), ctx.get("agent"), model, model_id,
             ms / 1000.0, ms, first_token_ms, input_tokens, output_tokens,
             cache_read_tokens, cost_usd, error_class, usage_source),
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("could not record a model call for %s: %s", model, exc)


# A streamed answer sends reasoning and text as it goes. Silence this long
# means the request is hung, whatever its total allowance: fail it and let
# the spare try, instead of waiting out the whole limit. Just under the
# gateway's own 300-second cut: a model writing tool-call arguments sends
# nothing while it writes, and that silence is legitimate until then.
IDLE_LIMIT_S = 290.0


class StreamIdle(Exception):
    """The stream sent nothing for IDLE_LIMIT_S."""


class StreamingModel(WrapperModel):
    """Every request streamed, bounded by wall clock, and recorded.

    Why streamed: the gateway closes a connection that has sent nothing for
    300 seconds. A long-reasoning answer sent in one piece arrives after that
    and dies as ``ReadError`` on every model in the chain; the same request
    streamed sends its first byte in seconds (measured 2026-09-23: 303s
    failed plain, 377s finished streamed).

    Why a wall clock: httpx's read timeout restarts on every byte, so a model
    that trickles tokens would never trip it. ``timeout_s`` from models.yaml
    is the whole attempt's allowance.

    Why the errors are rewritten: a failure after the first byte surfaces as
    a raw httpx or SDK error, and ``FallbackModel`` only moves to a spare on
    ``ModelAPIError``. Rewritten, a stream that breaks halfway goes to the
    spare instead of failing the step.
    """

    def __init__(self, wrapped: Model, entry: ModelEntry) -> None:
        super().__init__(wrapped)
        self.entry = entry

    @property
    def limit_s(self) -> float:
        return float((self.entry.settings or {}).get("timeout_s", 300.0))

    def total_limit_s(self, model_settings: ModelSettings | None) -> float:
        """The attempt's whole allowance: the entry's own, or longer when the
        caller asks for it (a planning call that reasons for minutes)."""
        asked = (model_settings or {}).get("timeout")
        return max(self.limit_s, float(asked) if isinstance(asked, int | float) else 0.0)

    async def request(
        self,
        messages: list[ModelMessage],
        model_settings: ModelSettings | None,
        model_request_parameters: ModelRequestParameters,
    ) -> ModelResponse:
        started = time.monotonic()
        first: float | None = None
        response: ModelResponse | None = None
        live: Any = None
        error_class: str | None = None
        total = self.total_limit_s(model_settings)
        try:
            try:
                async with asyncio.timeout(total):
                    async with self.wrapped.request_stream(
                        messages, model_settings, model_request_parameters
                    ) as stream:
                        live = stream
                        events = stream.__aiter__()
                        while True:
                            try:
                                await asyncio.wait_for(anext(events), IDLE_LIMIT_S)
                            except StopAsyncIteration:
                                break
                            except TimeoutError as exc:
                                raise StreamIdle(f"nothing streamed for {IDLE_LIMIT_S:.0f}s") from exc
                            if first is None:
                                first = time.monotonic()
                    response = stream.get()
            except ModelAPIError:
                raise
            except StreamIdle as exc:
                raise ModelAPIError(self.model_name, str(exc)) from exc
            except TimeoutError as exc:
                raise ModelAPIError(
                    self.model_name, f"no complete answer within {total:.0f}s"
                ) from exc
            except (httpx.HTTPError, openai.APIError, OSError) as exc:
                raise ModelAPIError(
                    self.model_name, f"the stream broke: {type(exc).__name__}: {exc}"
                ) from exc
            return response
        except BaseException as exc:
            cause = exc.__cause__ if isinstance(exc, ModelAPIError) and exc.__cause__ else exc
            error_class = type(cause).__name__
            if isinstance(exc, ModelHTTPError):
                error_class = f"HTTP{exc.status_code}"
            raise
        finally:
            partial = None
            if response is None and live is not None:
                try:
                    partial = live.get()
                except Exception:  # noqa: BLE001 — cost is best effort
                    partial = None
            await self._record(messages, response, error_class, started, first, partial)

    async def _record(
        self, messages: list[ModelMessage], response: ModelResponse | None,
        error_class: str | None, started: float, first: float | None,
        partial: ModelResponse | None = None,
    ) -> None:
        usage = response.usage if response is not None else None
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
        source = "reported"
        if response is None:
            # A timeout, an idle cut or a broken stream still cost the whole
            # prompt and whatever had streamed; recording $0 hid that spend.
            input_tokens, output_tokens = _estimated_tokens(messages, partial)
            source = "estimated"
        elif input_tokens == 0 and output_tokens == 0:
            input_tokens, output_tokens = _estimated_tokens(messages, response)
            source = "estimated"
            log.warning("model %s answered with no usage; estimated %d/%d tokens",
                        self.entry.name, input_tokens, output_tokens)
        cost = (input_tokens * self.entry.input_per_mtok
                + output_tokens * self.entry.output_per_mtok) / 1_000_000
        await record_call(
            model=self.entry.name, model_id=self.entry.model_id,
            ms=int((time.monotonic() - started) * 1000),
            input_tokens=input_tokens, output_tokens=output_tokens,
            cache_read_tokens=int(getattr(usage, "cache_read_tokens", 0) or 0),
            cost_usd=cost, error_class=error_class, usage_source=source,
            first_token_ms=None if first is None else int((first - started) * 1000),
        )


@dataclass(frozen=True)
class ModelEntry:
    name: str
    provider: str
    model_id: str
    input_per_mtok: float
    output_per_mtok: float
    settings: dict | None = None  # optional per-model request settings from models.yaml
    # Other entry names to try, in order, when this one answers with a
    # ModelAPIError (a timeout, a connection drop, a gateway 5xx). One flaky
    # gateway model must not be able to stop the whole system.
    fallback: tuple[str, ...] = ()


@dataclass(frozen=True)
class EmbeddingEntry:
    """The ``embeddings:`` section of models.yaml. ``dimensions`` is sent as
    the OpenAI ``dimensions`` parameter when set; the gateway truncates the
    native vector (Matryoshka) so smaller vectors fit a pgvector HNSW index
    (max 2000 dims). Embedding calls are not priced: no price entry exists."""
    provider: str
    model_id: str
    dimensions: int | None


# Native width of gemini-embedding-001 when models.yaml sets no ``dimensions``.
_DEFAULT_EMBED_DIMS = 3072
# The OpenAI embeddings endpoint accepts many inputs per call; 64 keeps each
# request well under the gateway's body limits for 1500-char chunks.
EMBED_BATCH = 64


def _gateway_client() -> AsyncOpenAI:
    """One AsyncOpenAI for the Grid gateway; chat and embeddings share it.
    max_retries=0: DBOS steps own retries, so the SDK must not stack its own."""
    s = settings()
    if not s.gateway_base_url or not s.gateway_api_key:
        raise RuntimeError("GATEWAY_BASE_URL/GATEWAY_API_KEY not set")
    return AsyncOpenAI(
        base_url=s.gateway_base_url,
        api_key=s.gateway_api_key,
        max_retries=0,
        http_client=httpx.AsyncClient(  # type: ignore[arg-type]  # SDK stubs name httpx2
            transport=GatewayCompatTransport(), timeout=180  # overridden per model by timeout_s
        ),
    )


class ModelRegistry:
    def __init__(self) -> None:
        raw = yaml.safe_load(settings().models_file.read_text())
        self.entries: dict[str, ModelEntry] = {
            name: ModelEntry(
                name=name,
                provider=cfg["provider"],
                model_id=cfg["model"],
                input_per_mtok=float(cfg["input_per_mtok"]),
                output_per_mtok=float(cfg["output_per_mtok"]),
                settings=cfg.get("settings"),
                fallback=tuple(cfg.get("fallback", ())),
            )
            for name, cfg in raw["models"].items()
        }
        self.roles: dict[str, str] = dict(raw.get("roles", {}))
        self._instances: dict[str, Model] = {}
        emb = raw.get("embeddings")
        self.embeddings: EmbeddingEntry | None = (
            EmbeddingEntry(
                provider=emb.get("provider", "gateway"),
                model_id=emb["model"],
                dimensions=int(emb["dimensions"]) if emb.get("dimensions") else None,
            )
            if emb
            else None
        )
        self._embed_client: AsyncOpenAI | None = None
        # Runtimes that are not models on the gateway but still spend tokens
        # (Codex). Priced here so their runs are costed like every other run.
        self.external: dict[str, dict[str, Any]] = dict(raw.get("external") or {})

    def external_cost(self, name: str, input_tokens: int, output_tokens: int) -> float:
        cfg = self.external.get(name) or {}
        return (input_tokens * float(cfg.get("input_per_mtok", 0))
                + output_tokens * float(cfg.get("output_per_mtok", 0))) / 1_000_000

    def embed_client(self) -> AsyncOpenAI:
        """Lazily built client for ``embeddings.provider``; cached for reuse."""
        if self.embeddings is None:
            raise RuntimeError("models.yaml has no `embeddings:` section")
        if self._embed_client is None:
            if self.embeddings.provider == "gateway":
                self._embed_client = _gateway_client()
            elif self.embeddings.provider == "openai":
                if not settings().openai_api_key:
                    raise RuntimeError("OPENAI_API_KEY not set")
                self._embed_client = AsyncOpenAI(
                    api_key=settings().openai_api_key, max_retries=0
                )
            else:
                raise ValueError(
                    f"embeddings provider {self.embeddings.provider!r} not wired yet"
                )
        return self._embed_client

    def canonical(self, name_or_role: str) -> str:
        """Role alias -> registry name; registry names pass through."""
        name = self.roles.get(name_or_role, name_or_role)
        if name not in self.entries:
            known = sorted([*self.entries, *self.roles])
            raise KeyError(f"unknown model {name_or_role!r}; known: {known}")
        return name

    def resolve(self, name_or_role: str) -> Model:
        """Return a constructed Pydantic AI Model for a registry name or role."""
        name = self.canonical(name_or_role)
        if name not in self._instances:
            self._instances[name] = self._build(self.entries[name])
        return self._instances[name]

    def all_instances(self) -> dict[str, Model]:
        """Every usable entry, pre-registered into DBOSDurability(models=...).

        Entries whose provider credentials are absent are skipped with a warning
        rather than breaking startup: models.yaml may list providers this
        deployment has not configured.
        """
        out: dict[str, Model] = {}
        for name in self.entries:
            try:
                out[name] = self.resolve(name)
            except Exception as exc:  # noqa: BLE001
                log.warning("model %r unavailable, skipping: %s", name, exc)
        if not out:
            raise RuntimeError("no usable models in models.yaml — check credentials in .env")
        return out

    def chain_timeout_s(self, name_or_role: str, default: float = 300.0) -> float:
        """How long one model step may need when every model in the entry's
        fallback chain times out in turn: its own timeout plus each spare's.

        The step's wall-clock limit must cover this, or the spares never get
        their turn. It used to be the longest single timeout plus a minute, so
        a hung primary used the whole step, the spares got sixty seconds, and
        the step was cancelled and retried on the same hung primary.
        """
        e = self.entries[self.canonical(name_or_role)]
        own = float((e.settings or {}).get("timeout_s", default))
        spares = sum(float((self.entries[f].settings or {}).get("timeout_s", default))
                     for f in (e.fallback or []) if f in self.entries and f != e.name)
        return own + spares

    def longest_chain_timeout_s(self) -> float:
        """The longest `chain_timeout_s` of any entry: the model step's limit."""
        return max((self.chain_timeout_s(n) for n in self.entries), default=300.0)

    def longest_timeout_s(self, default: float = 300.0) -> float:
        """The longest per-request timeout any entry declares in models.yaml."""
        found = [float((e.settings or {})["timeout_s"]) for e in self.entries.values()
                 if "timeout_s" in (e.settings or {})]
        return max(found, default=default)

    def model_settings_for(self, name_or_role: str):
        """Pydantic AI model settings for a registry entry: reasoning effort,
        output cap and request timeout come from models.yaml, not code."""
        from pydantic_ai.models.openai import OpenAIChatModelSettings

        cfg = self.entries[self.canonical(name_or_role)].settings or {}
        out: dict = {}
        if "reasoning_effort" in cfg:
            out["openai_reasoning_effort"] = cfg["reasoning_effort"]
        if "max_tokens" in cfg:
            out["max_tokens"] = int(cfg["max_tokens"])
        if "timeout_s" in cfg:
            out["timeout"] = float(cfg["timeout_s"])
        return OpenAIChatModelSettings(**out) if out else None

    def cost_usd(self, name_or_role: str, input_tokens: int, output_tokens: int) -> float:
        e = self.entries[self.canonical(name_or_role)]
        return (
            input_tokens * e.input_per_mtok + output_tokens * e.output_per_mtok
        ) / 1_000_000

    # Agent runs are almost all input: the instructions and the growing message
    # history are re-sent every round, and the model answers in a few hundred
    # tokens. Measured on a real scout run, 209,592 tokens were input by a wide
    # margin. Pricing every one of them at the output rate was 4x too harsh —
    # that run had spent about $0.13 of a $0.50 cap when it was killed for
    # "exceeding" it. A 90/10 blend is close to what runs actually cost.
    INPUT_SHARE = 0.9

    def token_budget(self, name_or_role: str, cap_usd: float) -> int | None:
        """Total tokens a run may spend before ``cap_usd`` is exceeded, priced at
        a 90% input / 10% output blend. None when the model is unpriced (0)."""
        e = self.entries[self.canonical(name_or_role)]
        price = self.INPUT_SHARE * e.input_per_mtok + (1 - self.INPUT_SHARE) * e.output_per_mtok
        if price <= 0:
            return None
        return int(cap_usd / price * 1_000_000)

    def _build(self, entry: ModelEntry) -> Model:
        """The entry's model, wrapped in its fallback chain when it declares one."""
        primary = self._build_one(entry)
        if not entry.fallback:
            return primary
        from pydantic_ai.models.fallback import FallbackModel

        spares: list[Model] = []
        for name in entry.fallback:
            if name == entry.name or name not in self.entries:
                log.warning("model %r: bad fallback %r, skipping", entry.name, name)
                continue
            try:
                # _build_one, not _build: a fallback never carries its own
                # chain, so a cycle in models.yaml cannot recurse.
                spares.append(self._build_one(self.entries[name]))
            except Exception as exc:  # noqa: BLE001 — a missing spare is not fatal
                log.warning("model %r: fallback %r unavailable: %s", entry.name, name, exc)
        if not spares:
            return primary
        log.info("model %r falls back to %s", entry.name, list(entry.fallback))
        return FallbackModel(primary, *spares, fallback_on=moves_to_spare)

    def _build_one(self, entry: ModelEntry) -> Model:
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        s = settings()
        if entry.provider == "gateway":
            client = _gateway_client()
        elif entry.provider == "openai":
            if not s.openai_api_key:
                raise RuntimeError("OPENAI_API_KEY not set")
            client = AsyncOpenAI(api_key=s.openai_api_key, max_retries=0)
        else:
            raise ValueError(
                f"provider {entry.provider!r} not wired yet; add it in llm._build"
            )
        return StreamingModel(
            OpenAIChatModel(entry.model_id, provider=OpenAIProvider(openai_client=client)), entry
        )


_registry: ModelRegistry | None = None


def registry() -> ModelRegistry:
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry


def embedding_dims() -> int:
    """Width of the vectors ``embed()`` returns. Must match the
    ``vector(N)`` column in migration 005; a mismatch fails the UPDATE, which
    memory.py logs and ignores."""
    emb = registry().embeddings
    if emb is None:
        raise RuntimeError("models.yaml has no `embeddings:` section")
    return emb.dimensions or _DEFAULT_EMBED_DIMS


async def embed(texts: list[str]) -> list[list[float]]:
    """Embed ``texts`` with the ``embeddings.model`` from models.yaml, at most
    EMBED_BATCH inputs per gateway call. Output order matches input order.
    Raises on any gateway error; callers decide whether that matters (the
    vault index treats it as best-effort)."""
    if not texts:
        return []
    reg = registry()
    client = reg.embed_client()
    assert reg.embeddings is not None  # embed_client() raised otherwise
    out: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH):
        batch = texts[start:start + EMBED_BATCH]
        kwargs: dict[str, int] = {}
        if reg.embeddings.dimensions:
            kwargs["dimensions"] = reg.embeddings.dimensions
        resp = await client.embeddings.create(
            model=reg.embeddings.model_id, input=batch, **kwargs  # type: ignore[arg-type]
        )
        vectors = sorted(resp.data, key=lambda d: d.index)
        if len(vectors) != len(batch):
            raise RuntimeError(
                f"embeddings: sent {len(batch)} inputs, got {len(vectors)} vectors"
            )
        out.extend([list(v.embedding) for v in vectors])
    return out


async def gateway_models() -> list[dict]:
    """What the gateway actually serves, with real context windows.

    The gateway's catalog changes without notice (aliases get retired), so we
    read it rather than trusting a hard-coded list.
    """
    import httpx

    s = settings()
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(
            f"{s.gateway_base_url.rstrip('/')}/models",
            headers={"Authorization": f"Bearer {s.gateway_api_key}"},
        )
        resp.raise_for_status()
    return [
        {
            "id": m["id"],
            "context": m.get("max_input_tokens"),
            "max_output": m.get("max_output_tokens"),
        }
        for m in resp.json().get("data", [])
    ]


async def verify_against_gateway() -> list[str]:
    """Names in models.yaml the gateway no longer serves. Logged at startup so
    a retired alias surfaces immediately instead of at 3am inside a cron run."""
    try:
        served = {m["id"] for m in await gateway_models()}
    except Exception as exc:  # noqa: BLE001 — never block startup on this
        log.warning("could not verify models against the gateway: %s", exc)
        return []
    missing = [
        f"{name} -> {entry.model_id}"
        for name, entry in registry().entries.items()
        if entry.provider == "gateway" and entry.model_id not in served
    ]
    for item in missing:
        log.error("models.yaml references a model the gateway does not serve: %s", item)
    return missing
