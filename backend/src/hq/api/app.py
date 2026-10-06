"""FastAPI app. Our OWN lifespan is the single owner of the startup order."""

from __future__ import annotations

import logging
import os
import subprocess
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

import hq.dbos_app  # noqa: F401 — constructs DBOS before any decorated import
from hq import db, engine, llm, memory, obs
from hq.channels import telegram
from hq.config import settings
from hq.dbos_app import DBOS

log = logging.getLogger(__name__)


def _ensure_vault_repo() -> None:
    vault = settings().vault_dir
    vault.mkdir(parents=True, exist_ok=True)
    if not (vault / ".git").exists():
        subprocess.run(["git", "init", "-b", "main"], cwd=vault, check=True, capture_output=True)


def _hold_awake() -> subprocess.Popen[bytes] | None:
    """Keep the machine awake for as long as this process lives.

    A laptop that sleeps at 02:00 does not run the 02:00 job: the process is
    suspended mid-run and the model request dies on wake, its timeout unable
    to fire because no timer advanced. Every scheduled run was failing this
    way, with durations of hours and no tokens spent.

    caffeinate is spawned as our CHILD with -w on our own pid, so it exits
    when we do. Wrapping the whole process in caffeinate instead looks
    simpler and is wrong: launchd would then be supervising caffeinate, and
    restarting the job would kill only the wrapper while the Python it
    started kept the port and kept polling Telegram.

    -s asserts on AC power only, so nothing changes on battery.
    """
    try:
        proc = subprocess.Popen(
            ["/usr/bin/caffeinate", "-s", "-w", str(os.getpid())],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError as exc:
        # Not being able to block sleep is not a reason to refuse to start.
        log.warning("could not hold the machine awake: %s", exc)
        return None
    log.info("holding the machine awake while this process runs")
    return proc


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        obs.configure_tracing()
    except Exception as exc:  # noqa: BLE001 — tracing must never block startup
        log.warning("tracing disabled: %s", exc)
    awake = _hold_awake()
    await db.open_pool()
    await db.migrate()
    _ensure_vault_repo()
    await memory.ensure_index()     # builds the search index on first boot only
    engine.bootstrap_pre_launch()   # agents + cron workflows, BEFORE launch
    await llm.verify_against_gateway()  # logs an error for each retired model alias;
                                        # startup continues so the console still works
    DBOS.launch()
    await engine.bootstrap_post_launch()  # queues + schedules need a launched executor
    await engine.reap()             # reconcile stale state from the last crash
    await telegram.start()
    log.info("mission hq up: agents=%s", sorted(engine.registered_agents()))
    yield
    await telegram.stop()
    DBOS.destroy()
    await db.close_pool()
    # -w already makes it exit with us; this closes it promptly on a clean stop.
    if awake and awake.poll() is None:
        awake.terminate()


app = FastAPI(title="Mission HQ", lifespan=lifespan)

# CORS only when a page on another origin calls this API: the console on
# Vercel, or the phone reader's /api/reader sync (its Vercel origin goes in
# CORS_ORIGINS; see docs/deploy.md §12). Exact origins, no credentials: the
# console sends the bearer token itself, the reader sends none (Tailscale
# identity authenticates it).
_cors_origins = [o.strip() for o in settings().cors_origins.split(",") if o.strip()]
if _cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        expose_headers=[],
    )

from hq.api.agents_admin import router as agents_admin_router
from hq.api.chat import router as chat_router
from hq.api.events import router as events_router
from hq.api.learning import router as learning_router
from hq.api.media import router as media_router
from hq.api.radar import router as radar_router
from hq.api.reader import router as reader_router
from hq.api.rest import router as rest_router
from hq.api.today import router as today_router
from hq.api.vault import router as vault_router
from hq.api.videos import router as videos_router

app.include_router(rest_router, prefix="/api")
app.include_router(events_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(vault_router, prefix="/api")
app.include_router(learning_router, prefix="/api")
app.include_router(media_router, prefix="/api")
app.include_router(videos_router, prefix="/api")
app.include_router(reader_router, prefix="/api")
app.include_router(agents_admin_router, prefix="/api")
app.include_router(today_router, prefix="/api")
app.include_router(radar_router, prefix="/api")
