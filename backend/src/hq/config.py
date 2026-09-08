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
    grid_api_key: str = ""

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

    # --- claude runtime (agents with `runtime: claude` in job.md) -------------
    # Hands one task to the Claude Code CLI, which can drive the browser you
    # are signed into through the Claude in Chrome extension. Needs a desktop
    # session, so it is off unless a machine actually has that set up.
    claude_runtime_enabled: bool = False
    claude_cli_path: str = "claude"
    # Only these tools. Headless mode refuses anything unlisted rather than
    # asking, so this list is the whole permission model for that process.
    # Browser tools only: Claude reads, Mission HQ writes through its gates.
    claude_allowed_tools: str = "mcp__claude-in-chrome__*"
    claude_max_turns: int = 25
    # A hard ceiling in real dollars. A run that cannot reach a browser burns
    # money discovering that, so this is not optional.
    claude_max_budget_usd: float = 1.00
    claude_timeout_s: float = 600.0

    # --- codex runtime (agents with `runtime: codex` in job.md) ---------------
    # Same job as the claude runtime: reach a browser the owner is signed into.
    # Which CLI a machine can use is a per-machine fact, so both exist.
    codex_runtime_enabled: bool = False
    codex_cli_path: str = "codex"
    # Codex has no budget flag and no tool allowlist, so the timeout is the
    # only ceiling on one run and --sandbox read-only is the boundary.
    codex_timeout_s: float = 600.0
    # Optional. Codex reads ~/.codex/config.toml, and a machine whose default
    # provider only works inside the ChatGPT app cannot run it headlessly.
    # These override the model and any config key, e.g.
    # CODEX_CONFIG="model_provider=juspay,model=open-large".
    codex_model: str = ""
    codex_config: str = ""
    # Hours an approval of an external-runtime agent stays good for. The owner
    # asked to be able to say "go" once rather than per run, and this agent
    # only reads. 0 asks every time. It never covers acting on the world:
    # nothing in this system can do that at all.
    runtime_approval_hours: float = 12.0

    # Days a finished task stays on the board before the maintenance tick sets
    # it to `archived`. Nothing is deleted; archived tasks are simply left out
    # of the default list. 0 switches archiving off.
    board_archive_days: int = 14

    # --- headed browser (browser_read) --------------------------------------
    # Off by default: it opens a real window, so it must be a deliberate choice.
    browser_enabled: bool = False
    # A REAL Chrome, launched by us with a debug port and its own profile. Not
    # the one you browse in: your Chrome holds a lock on its own profile, and a
    # separate profile also means an agent can never see your other tabs.
    browser_chrome_path: str = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
    browser_debug_port: int = 9223
    browser_profile_dir: Path = REPO_DIR / "data" / "browser-profile"
    # Seconds between page loads. A burst of requests is what looks automated;
    # reading at human pace is both politer and safer.
    browser_min_interval_s: float = 3.0
    browser_page_timeout_s: float = 45.0

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
