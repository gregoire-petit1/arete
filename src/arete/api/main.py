import logging

from dotenv import load_dotenv
from fastapi import FastAPI

from arete.api.metrics import router as metrics_router
from arete.api.settings import router as settings_router

logger = logging.getLogger(__name__)

load_dotenv()
app = FastAPI(title="Arete API", version="0.1.0")


@app.on_event("startup")
def startup_init_db():
    """Initialize DuckDB schema on startup if needed."""
    try:
        from arete.dataio.init_duckdb import main as init_schema

        init_schema()
        logger.info("Database schema initialized")
    except Exception as e:
        logger.warning("Database init failed (non-fatal): %s", e)


@app.get("/health")
def health():
    """Health check endpoint with detailed status."""

    # Check DuckDB
    db_status = "connected"
    try:
        from arete.dataio.db import connect

        conn = connect(read_only=True)
        conn.execute("SELECT 1").fetchone()
        conn.close()
    except Exception as e:
        logger.warning("DuckDB health check failed: %s", e)
        db_status = "disconnected"

    return {
        "status": "ok",
        "database": db_status,
    }


# Routes user settings
app.include_router(settings_router)

# Routes metrics (workload/fitness/cardio/strength/recommendations)
app.include_router(metrics_router)

# Routes Garmin (planned/actual sessions, FIT upload, matching)
from arete.api.garmin import router as garmin_router

app.include_router(garmin_router)

# Routes Garmin Health (HRV, sleep, body battery, readiness)
from arete.api.garmin_health import router as garmin_health_router

app.include_router(garmin_health_router)

# Routes Strength (exercises, strength sessions, sets, PRs)
from arete.api.strength import router as strength_router

app.include_router(strength_router)

# Routes AI Tips (daily contextual tips)
from arete.api.ai_tips import router as ai_tips_router

app.include_router(ai_tips_router)

# Routes Strava
from arete.api.strava import router as strava_router

app.include_router(strava_router)

# Routes Analytics
from arete.api.analytics import router as analytics_router

app.include_router(analytics_router)
