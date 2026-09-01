"""FastAPI app. Our OWN lifespan is the single owner of the startup order."""

from __future__ import annotations

import logging
import subprocess
from contextlib import asynccontextmanager

from fastapi import FastAPI

import hq.dbos_app  # noqa: F401 — constructs DBOS before any decorated import
from hq import db, engine, llm, obs
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
    engine.bootstrap_pre_launch()   # agents + cron workflows, BEFORE launch
    await llm.verify_against_gateway()  # a retired model alias must fail loudly now,
                                        # not at 3am inside a cron run
    DBOS.launch()
    await engine.bootstrap_post_launch()  # queues need a launched executor
    await engine.reap()             # reconcile stale state from the last crash
    await telegram.start()
    log.info("mission hq up: agents=%s", sorted(engine.registered_agents()))
    yield
    await telegram.stop()
    DBOS.destroy()
    await db.close_pool()


app = FastAPI(title="Mission HQ", lifespan=lifespan)

from hq.api.events import router as events_router
from hq.api.rest import router as rest_router

app.include_router(rest_router, prefix="/api")
app.include_router(events_router, prefix="/api")
