"""Settings. Everything environment-specific comes from .env; nothing is hard-coded."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import BaseModel, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
REPO_DIR = BACKEND_DIR.parent


class Caps(BaseModel):
    # Defaults tripled 2026-09-10; every job.md sets its own explicitly anyway.
    cost_per_run_usd: float = 1.50
    tool_calls: int = 80
    daily_usd: float = 6.00


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    database_url: str = "postgresql://localhost:5432/missionhq"

    gateway_base_url: str = ""
    gateway_api_key: str = ""
    # Requests the gateway key allows at once. Every chat, embedding and judge
    # call waits for one of these before it is sent, so the backend never
    # overfills the key's slot table and has to wait out 429s instead.
    gateway_parallel: int = 5
    openai_api_key: str = ""
    grid_api_key: str = ""

    telegram_bot_token: str = ""
    owner_chat_id: int = 0

    # and never reaches prompts, tool args, results, or the vault.  # comma-separated owner/repo list, e.g. "me/app,me/site"

    cron_tz: str = "Asia/Kolkata"
    # 5.00 while cost was the constraint; tripled 2026-09-10 when the owner said
    # value is ("don't care about the money for now"). The per-agent caps in
    # each job.md went up by the same factor.
    daily_spend_cap_usd: float = 60.00
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

    # --- codex runtime (agents with `runtime: codex` in job.md) ---------------
    # Reach a browser the owner is signed into.
    # Which CLI a machine can use is a per-machine fact, so both exist.
    codex_runtime_enabled: bool = False
    codex_cli_path: str = "codex"
    # Codex has no budget flag and no tool allowlist, so the timeout is the
    # only ceiling on one run and --sandbox read-only is the boundary.
    #
    # 900, not 600, since 2026-09-10: the broad discovery run was killed at
    # 600s and returned nothing, because a killed CLI has no partial result.
    # The brief now tells operator to finish inside ten minutes and report
    # what it has; this sits above that so the instruction, not the killer,
    # is what ends a healthy run. Raising it further would only let a browser
    # session grind on LinkedIn for half an hour, which is the pattern that
    # gets the owner's account restricted.
    codex_timeout_s: float = 900.0
    # Optional. Codex reads ~/.codex/config.toml, and a machine whose default
    # provider only works inside the ChatGPT app cannot run it headlessly.
    # These override the model and any config key, e.g.
    # CODEX_CONFIG="model_provider=juspay,model=open-large".
    codex_model: str = ""
    codex_config: str = ""
    # Codex's working directory (`--cd`) for operator. Codex reads AGENTS.md
    # from it, so the card is copied here before every run. Not the vault:
    # the vault indexes, lists and commits every .md in it.
    operator_workdir: Path = REPO_DIR / "data" / "operator"
    # Hours an approval of an external-runtime agent stays good for. The owner
    # asked to be able to say "go" once rather than per run, and this agent
    # only reads. 0 asks every time. It never covers acting on the world:
    # nothing in this system can do that at all.
    runtime_approval_hours: float = 12.0

    # Credentials Codex itself needs, forwarded to the child process.
    #
    # The backend runs under launchd, which does not read ~/.zshrc, so a key
    # that works in your terminal is simply absent here: every operator run
    # failed with "Missing environment variable: AZURE_OPENAI_API_KEY" until
    # this existed. Codex reads ~/.codex/config.toml to decide its provider;
    # whichever one it names, its key has to be set here too.
    azure_openai_api_key: str = ""
    openai_api_key_for_codex: str = ""

    # --- Bright Data (web search and social lookups) -------------------------
    # One key, two products. The SERP API answers "which page has this", and
    # the Web Scraper API reads a LinkedIn or X page as structured records.
    #
    # Both run on Bright Data's own infrastructure, never the owner's browser
    # or IP, which is the point: browser_read refuses LinkedIn in code because
    # automated access there risks the account that pays for it, and the
    # account at risk here is Bright Data's, not his.
    brightdata_api_key: str = ""
    # Zone name from the Bright Data console. A zone is the product
    # configuration a request runs under; SERP requests need a SERP zone.
    brightdata_serp_zone: str = "serp_api1"
    # The free tier is 5,000 credits a month, one credit per SERP request and
    # one per scraped record, and it stops dead when they run out. These are
    # the softer stops, deliberately far below the tier: 40 a day and 1,200 a
    # month leaves most of the allowance unspent, because these calls are the
    # last resort and not the first. A day of casual testing took 420.
    # The Scrapers product (LinkedIn and X records) is OFF. It bills per
    # record, not per request, so one jobs lookup matching forty postings
    # costs forty credits from a single call. Operator reads those hosts in
    # the owner's own browser for nothing, so this buys an unpredictable bill
    # for something already covered. The tool stays in the codebase behind
    # this flag; no agent is granted it.
    # Market for search, as Bing's mkt/cc pair. The owner works and job hunts
    # in India, and an unlocalised search answers a different question: the
    # same words return US postings and US salary pages. Set to the market you
    # actually hire and read in.
    brightdata_search_market: str = "en-IN"

    brightdata_scrapers_enabled: bool = False
    brightdata_daily_calls: int = 150
    brightdata_monthly_calls: int = 4000

    # Days a finished task stays on the board before the maintenance tick sets
    # it to `archived`. Nothing is deleted; archived tasks are simply left out
    # of the default list. 0 switches archiving off.
    board_archive_days: int = 14

    # --- job search -----------------------------------------------------------
    # Days a merely-decent find stays in the Found column. The owner reads that
    # column to decide what to act on today, so a role he has walked past for
    # two days is noise. The maintenance tick sets those to `closed`; nothing is
    # deleted, because the row is also the discovery memory that stops the same
    # role being researched again next week. A strong fit never ages out.
    job_found_days: int = 2
    # Minimum years of experience at which a posting stops being one the owner
    # can take. He is early-career, so a role whose floor is this high is a
    # waste of a run whatever else it offers. Enforced in record_job, not asked
    # for in a prompt, because "don't record senior roles" is exactly the kind
    # of instruction a model drops on a long run.
    job_max_min_years: float = 3.0
    # Target total compensation in lakhs per annum. Not a hard gate: most
    # postings publish no number at all, so refusing those would empty the
    # board. It steers the score and is shown on the card.
    job_target_ctc_lakh: float = 25.0

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
    # His own files for the learning journey — the roster and his interests.
    # In the repo, not the vault: the vault has no remote and is the agents'
    # memory layer, and these two are his to edit and worth git history.
    learning_dir: Path = REPO_DIR / "learning"
    # His own study platform. The catalogue at /api/study is public; the phase
    # pages are readable by slug. Tutor works through them one phase a day.
    study_api_base: str = "https://raghu-monitoring.vercel.app"
    # Optional, read-only, for the radar's issue trackers. Without it GitHub
    # allows 60 requests an hour, and the radar makes one a day per repo.
    github_token: str = ""
    # His current and former employers. Never named in anything an agent
    # loads, writes, searches or posts (``hq.privacy`` is the one gate). The
    # names live only in .env as PRIVATE_EMPLOYERS, comma-separated, so no
    # prompt, source line or test in this repo carries them.
    private_employers: Annotated[tuple[str, ...], NoDecode] = ()
    # His own site, beside this repo. Posts are written into its content
    # folder and never committed or pushed from here: publishing is his.
    portfolio_dir: Path = REPO_DIR.parent / "portfolio"
    halt_file: Path = REPO_DIR / "HALT"
    models_file: Path = BACKEND_DIR / "models.yaml"

    # Defaults applied when an agent manifest omits caps
    default_caps: Caps = Caps()


    @field_validator("private_employers", mode="before")
    @classmethod
    def _split_employers(cls, v: object) -> object:
        """``PRIVATE_EMPLOYERS=A Corp,B Inc`` in .env; blanks dropped. A JSON
        list (``["A Corp","B Inc"]``) is read too."""
        if isinstance(v, str):
            text = v.strip()
            if text.startswith("["):
                return tuple(str(n).strip() for n in json.loads(text) if str(n).strip())
            return tuple(n.strip() for n in text.split(",") if n.strip())
        return v

@lru_cache
def settings() -> Settings:
    return Settings()
