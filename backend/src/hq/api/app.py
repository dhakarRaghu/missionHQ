"""FastAPI app. Our OWN lifespan is the single owner of the startup order."""

from __future__ import annotations

import logging
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


@asynccontextmanager
async def lifespan(app: FastAPI):
    try:
        obs.configure_tracing()
    except Exception as exc:  # noqa: BLE001 — tracing must never block startup
        log.warning("tracing disabled: %s", exc)
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


app = FastAPI(title="Mission HQ", lifespan=lifespan)

# CORS only when the console is served from another origin (e.g. Vercel).
# Exact origins, no credentials: the browser sends the bearer token itself.
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
from hq.api.rest import router as rest_router
from hq.api.vault import router as vault_router

app.include_router(rest_router, prefix="/api")
app.include_router(events_router, prefix="/api")
app.include_router(chat_router, prefix="/api")
app.include_router(vault_router, prefix="/api")
app.include_router(agents_admin_router, prefix="/api")
