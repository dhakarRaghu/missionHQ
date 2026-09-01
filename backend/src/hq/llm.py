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
            )
            for name, cfg in raw["models"].items()
        }
        self.roles: dict[str, str] = dict(raw.get("roles", {}))
        self._instances: dict[str, object] = {}

    def canonical(self, name_or_role: str) -> str:
        """Role alias -> registry name; registry names pass through."""
        name = self.roles.get(name_or_role, name_or_role)
        if name not in self.entries:
            known = sorted([*self.entries, *self.roles])
            raise KeyError(f"unknown model {name_or_role!r}; known: {known}")
        return name

    def resolve(self, name_or_role: str):
        """Return a constructed Pydantic AI Model for a registry name or role."""
        name = self.canonical(name_or_role)
        if name not in self._instances:
            self._instances[name] = self._build(self.entries[name])
        return self._instances[name]

    def all_instances(self) -> dict[str, object]:
        """Every usable entry, pre-registered into DBOSDurability(models=...).

        Entries whose provider credentials are absent are skipped with a warning
        rather than breaking startup: models.yaml may list providers this
        deployment has not configured.
        """
        out: dict[str, object] = {}
        for name in self.entries:
            try:
                out[name] = self.resolve(name)
            except Exception as exc:  # noqa: BLE001
                log.warning("model %r unavailable, skipping: %s", name, exc)
        if not out:
            raise RuntimeError("no usable models in models.yaml — check credentials in .env")
        return out

    def cost_usd(self, name_or_role: str, input_tokens: int, output_tokens: int) -> float:
        e = self.entries[self.canonical(name_or_role)]
        return (
            input_tokens * e.input_per_mtok + output_tokens * e.output_per_mtok
        ) / 1_000_000

    def _build(self, entry: ModelEntry):
        from openai import AsyncOpenAI
        from pydantic_ai.models.openai import OpenAIChatModel
        from pydantic_ai.providers.openai import OpenAIProvider

        s = settings()
        if entry.provider == "gateway":
            if not s.gateway_base_url or not s.gateway_api_key:
                raise RuntimeError("GATEWAY_BASE_URL/GATEWAY_API_KEY not set")
            # max_retries=0: DBOS steps own retries, so the SDK must not stack its own.
            client = AsyncOpenAI(
                base_url=s.gateway_base_url,
                api_key=s.gateway_api_key,
                max_retries=0,
                http_client=httpx.AsyncClient(
                    transport=GatewayCompatTransport(), timeout=600
                ),
            )
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
