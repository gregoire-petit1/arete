import asyncio
import hmac
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Header, HTTPException

from arete import scheduler
from arete.api.agent import router as agent_router
from arete.api.ai_tips import router as ai_tips_router
from arete.api.analytics import router as analytics_router
from arete.api.garmin import router as garmin_router
from arete.api.garmin_health import router as garmin_health_router
from arete.api.garmin_sync import router as garmin_sync_router
from arete.api.metrics import router as metrics_router
from arete.api.plan import router as plan_router
from arete.api.settings import router as settings_router
from arete.api.strava import router as strava_router
from arete.api.strength import router as strength_router
from arete.config import config
from arete.dataio.db import db_connection
from arete.dataio.init_duckdb import main as init_schema
from arete.dataio.mirror import MirrorMiddleware

logger = logging.getLogger(__name__)


def configure_logging() -> None:
    """Root logger to stderr; level from ARETE_LOG_LEVEL (default INFO)."""
    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        force=False,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    configure_logging()
    if config.langsmith_tracing:
        # LangSmith loads only when tracing is on; this rejects a missing key.
        from arete.observability.tracing import get_tracing_client

        get_tracing_client()
    try:
        init_schema()
        logger.info("Database schema initialized")
    except Exception as e:
        logger.warning("Database init failed (non-fatal): %s", e)
    task = scheduler.start()
    try:
        yield
    finally:
        if task is not None:
            task.cancel()
        if "arete.observability.tracing" in sys.modules:
            from arete.observability.tracing import close_tracing

            await asyncio.to_thread(close_tracing)


app = FastAPI(title="Arete API", version="0.1.0", lifespan=lifespan)
app.add_middleware(MirrorMiddleware)


@app.get("/health")
def health():
    """Health check endpoint with database status.

    Reads a real table rather than ``SELECT 1``, which DuckDB answers locally:
    the probe must reach (and so keep awake) the remote database.
    """
    db_status = "connected"
    schema_version = None
    try:
        with db_connection() as con:
            row = con.execute(
                "SELECT COALESCE(MAX(version), 0) FROM app.schema_version"
            ).fetchone()
            schema_version = row[0] if row else None
    except Exception as e:
        logger.warning("DuckDB health check failed: %s", e)
        db_status = "disconnected"
    return {"status": "ok", "database": db_status, "schema_version": schema_version}


@app.get("/sync/status")
def sync_status():
    """State of the daily background sync.

    ``last_run`` is the durable marker beside the database (so it survives a
    restart); ``sources`` is the per-source outcome of the last run THIS
    process did, empty when it has not run one yet. The coaching agent reads
    this before briefing on the day: a briefing written on data that never
    landed is worse than no briefing.
    """
    last_run = scheduler.last_run_date()
    return {
        "scheduled_hour": config.auto_sync_hour,
        "last_run": last_run.isoformat() if last_run else None,
        "sources": scheduler.last_status(),
    }


@app.get("/cron/daily-sync")
def cron_daily_sync(authorization: str | None = Header(default=None)):
    """The daily sync, triggered by Vercel Cron where no process stays up.

    Vercel sends ``Authorization: Bearer $CRON_SECRET``; without a configured
    secret the endpoint stays closed rather than open to anyone.
    """
    secret = config.cron_secret
    expected = f"Bearer {secret}"
    if not secret or not hmac.compare_digest(authorization or "", expected):
        raise HTTPException(status_code=401, detail="Non autorisé")
    status = scheduler.daily_sync()
    scheduler.record_run(datetime.now())
    status["briefing"] = scheduler.write_daily_briefing()
    return status


for router in (
    settings_router,
    metrics_router,
    garmin_router,
    garmin_health_router,
    garmin_sync_router,
    strength_router,
    ai_tips_router,
    strava_router,
    analytics_router,
    agent_router,
    plan_router,
):
    app.include_router(router)
