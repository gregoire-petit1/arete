from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel, Field

from arete.api.metrics import router as metrics_router
from arete.api.routes import router as api_router
from arete.dataio.db import connect
from arete.llm.client import TrainingContext, generate_plan

load_dotenv()
app = FastAPI(title="Arete API", version="0.1.0")


class SessionRequest(BaseModel):
    """Request for daily training plan generation."""

    date: str = Field(description="Date for the plan (YYYY-MM-DD)")
    objectif: str = Field(description="Training objective (e.g., 'marathon', 'forme')")
    dispo_min: int = Field(gt=0, le=300, description="Available time in minutes")
    fatigue: int = Field(ge=1, le=10, description="Perceived fatigue (1-10)")
    rpe_moy7j: float | None = Field(None, ge=1, le=10, description="7-day average RPE")


@app.get("/health")
def health():
    return {"ok": True}


@app.post("/plan/jour")
def plan_jour(req: SessionRequest):
    """Generate personalized training plan for the day.

    Uses current fitness/workload metrics + LLM to create adaptive plan.
    Falls back to rule-based generation if LLM unavailable.
    """
    from datetime import date as dt_date
    from datetime import timedelta

    from arete.features.fitness import DailyTSS, compute_performance_model
    from arete.features.workload import DailyLoad, compute_workload_metrics

    # Build context from request
    ctx = TrainingContext(
        date=req.date,
        objectif=req.objectif,
        dispo_min=req.dispo_min,
        fatigue=req.fatigue,
        rpe_moy7j=req.rpe_moy7j,
    )

    # Try to enrich with current metrics from DB
    target_date = dt_date.today()
    con = connect(read_only=True)
    try:
        # Get workload metrics
        start_date = target_date - timedelta(days=28)
        rows = con.execute(
            """
            SELECT date, SUM(duree_min) as duration, AVG(rpe) as avg_rpe
            FROM app.training_log
            WHERE date >= ? AND date <= ?
            GROUP BY date
            ORDER BY date ASC
            """,
            [start_date, target_date],
        ).fetchall()

        if rows:
            data_by_date = {row[0]: (int(row[1]), float(row[2])) for row in rows}
            loads = []
            current = start_date
            while current <= target_date:
                if current in data_by_date:
                    dur, rpe = data_by_date[current]
                    loads.append(DailyLoad(date=current, duration_min=dur, rpe=rpe))
                else:
                    loads.append(DailyLoad(date=current, duration_min=0, rpe=0))
                current += timedelta(days=1)

            workload = compute_workload_metrics(loads, target_date)
            ctx.acwr = workload.acwr
            ctx.acwr_zone = workload.acwr_zone.value if workload.acwr_zone else None
            ctx.monotony = workload.monotony
            ctx.strain = workload.strain

        # Get fitness metrics
        start_date = target_date - timedelta(days=42)
        rows = con.execute(
            """
            SELECT date,
                   SUM(COALESCE(duree_min, 0) * POWER(COALESCE(rpe, 5) / 10.0, 2) / 0.36) as daily_tss
            FROM app.training_log
            WHERE date >= ? AND date <= ?
            GROUP BY date
            ORDER BY date ASC
            """,
            [start_date, target_date],
        ).fetchall()

        if rows:
            tss_by_date = {row[0]: float(row[1]) for row in rows}
            tss_list = []
            current = start_date
            while current <= target_date:
                tss = tss_by_date.get(current, 0.0)
                tss_list.append(DailyTSS(date=current, tss=tss))
                current += timedelta(days=1)

            fitness = compute_performance_model(tss_list, target_date)
            ctx.tsb = fitness.tsb
            ctx.form_zone = fitness.form_zone.value if fitness.form_zone else None
            ctx.ctl = fitness.ctl

    except Exception:
        pass  # Continue without metrics enrichment
    finally:
        con.close()

    # Generate plan using LLM (or fallback)
    plan = generate_plan(ctx)
    return plan


@app.get("/log/recent")
def log_recent(n: int = 5):
    if n < 1 or n > 100:
        n = 5  # Default to safe value
    con = connect(read_only=True)
    try:
        rows = con.execute(
            """
            SELECT date, sport, type, duree_min, distance_km, rpe
            FROM app.training_log
            ORDER BY date DESC
            LIMIT ?
            """,
            [n],
        ).fetchall()
        columns = ["date", "sport", "type", "duree_min", "distance_km", "rpe"]
        return {"rows": [dict(zip(columns, row, strict=True)) for row in rows]}
    finally:
        con.close()


# Routes CRUD (sessions/user/objectives/records)
app.include_router(api_router)

# Routes metrics (workload/fitness/cardio/strength/recommendations)
app.include_router(metrics_router)

# Routes RAG (knowledge-augmented recommendations)
from arete.api.rag import router as rag_router

app.include_router(rag_router)

# Routes Garmin (planned/actual sessions, FIT upload, matching)
from arete.api.garmin import router as garmin_router

app.include_router(garmin_router)
