import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from arete import scheduler
from arete.api.agent import router as agent_router
from arete.api.ai_tips import router as ai_tips_router
from arete.api.analytics import router as analytics_router
from arete.api.garmin import router as garmin_router
from arete.api.garmin_health import router as garmin_health_router
from arete.api.garmin_sync import router as garmin_sync_router
from arete.api.metrics import router as metrics_router
from arete.api.settings import router as settings_router
from arete.api.strava import router as strava_router
from arete.api.strength import router as strength_router
from arete.config import config
from arete.dataio.db import db_connection
from arete.dataio.init_duckdb import main as init_schema
from arete.observability.tracing import close_tracing, get_tracing_client

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
        await asyncio.to_thread(close_tracing)


app = FastAPI(title="Arete API", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health():
    """Health check endpoint with database status."""
    db_status = "connected"
    try:
        with db_connection() as con:
            con.execute("SELECT 1").fetchone()
    except Exception as e:
        logger.warning("DuckDB health check failed: %s", e)
        db_status = "disconnected"
    return {"status": "ok", "database": db_status}


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
):
    app.include_router(router)
