"""Settings. Everything environment-specific comes from .env; nothing is hard-coded."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent


class Caps(BaseModel):
    cost_per_run_usd: float = 0.50
    tool_calls: int = 40
    daily_usd: float = 2.00


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str = "postgresql://localhost:5432/missionhq"

    gateway_base_url: str = ""
    gateway_api_key: str = ""
    openai_api_key: str = ""

    telegram_bot_token: str = ""
    owner_chat_id: int = 0

    # and never reaches prompts, tool args, results, or the vault.  # comma-separated owner/repo list, e.g. "me/app,me/site"

    cron_tz: str = "Asia/Kolkata"
    daily_spend_cap_usd: float = 5.00
    notifications_per_day: int = 5
    api_bearer_token: str = ""
    # Tailscale Serve identity that may skip the bearer token. Empty = never.
    tailscale_owner_login: str = ""
    healthchecks_ping_url: str = ""
    # Comma-separated exact origins allowed by CORS, e.g. "https://hq.vercel.app".
    # Empty = CORS middleware off (same-origin console behind Caddy/Tailscale).
    cors_origins: str = ""
    # Listen address. Keep 127.0.0.1 behind Caddy; Caddy owns the public port.
    bind_host: str = "127.0.0.1"
    bind_port: int = 8000

    # Paths (relative to the repo root; overridable for tests)
    agents_dir: Path = REPO_DIR / "agents"
    vault_dir: Path = REPO_DIR / "vault"
    halt_file: Path = REPO_DIR / "HALT"
    models_file: Path = BACKEND_DIR / "models.yaml"

    # Defaults applied when an agent manifest omits caps
    default_caps: Caps = Caps()


@lru_cache
def settings() -> Settings:
    return Settings()
