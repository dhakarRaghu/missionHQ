"""Model registry.

models.yaml is the only place a provider or model id is named. Code refers to
models by registry NAME (or role alias). Pricing from the yaml is the source of
truth for cost accounting; auto-pricing cannot price gateway-aliased ids.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

import httpx
import yaml
from openai import AsyncOpenAI
from pydantic_ai.models import Model

from hq.config import settings

log = logging.getLogger(__name__)


class GatewayCompatTransport(httpx.AsyncHTTPTransport):
    """Drops vendor extras the OpenAI schema rejects.

    Grid proxies several backends, and some (Kimi) attach a ``metadata`` object
    whose ``weight_versions`` is a list. The OpenAI SDK types ``metadata`` as
    ``dict[str, str]`` and raises on the whole response. The field carries
    nothing we use, so it is removed before parsing. Streaming responses pass
    through untouched.
    """

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        response = await super().handle_async_request(request)
        if "application/json" not in response.headers.get("content-type", ""):
            return response
        await response.aread()
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
            transport=GatewayCompatTransport(), timeout=180  # a hung request fails fast; DBOS retries once
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

    def token_budget(self, name_or_role: str, cap_usd: float) -> int | None:
        """Total tokens a run may spend before ``cap_usd`` is exceeded, priced at
        the dearer of input/output. None when the model is unpriced (0)."""
        e = self.entries[self.canonical(name_or_role)]
        price = max(e.input_per_mtok, e.output_per_mtok)
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
        return FallbackModel(primary, *spares)

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
        return OpenAIChatModel(entry.model_id, provider=OpenAIProvider(openai_client=client))


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
