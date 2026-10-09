"""Training metrics shared by web and coaching surfaces."""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from arete.dataio.db import connect
from arete.dataio.queries import daily_tss_by_date, training_loads, tss_history
from arete.dataio.settings import get_user_settings
from arete.features.fitness import (
    DailyTSS,
    PerformanceModel,
    compute_performance_model,
)
from arete.features.recommendations import (
    RecommendationReport,
    generate_recommendations,
)
from arete.features.workload import (
    ACWRZone,
    compute_workload_metrics,
)
from arete.garmin.readiness import compute_readiness, fetch_window

logger = logging.getLogger(__name__)
TSS_PER_SESSION = 50.0
READINESS_LOOKBACK_DAYS = 1
FORM_HISTORY_DAYS = 42


class WorkloadMetricsOut(BaseModel):
    """Workload metrics response."""

    acwr: float | None = Field(description="Acute:Chronic Workload Ratio")
    acwr_zone: str | None = Field(description="ACWR risk zone")
    acwr_ewma: float | None = Field(description="ACWR using EWMA method")
    monotony: float | None = Field(description="Training monotony (load variability)")
    monotony_zone: str | None = Field(description="Monotony zone")
    strain: float | None = Field(description="Training strain")
    strain_zone: str | None = Field(description="Strain zone")
    acute_load: float = Field(description="Acute load (7-day sum)")
    chronic_load: float | None = Field(description="Chronic load (28-day average)")
    days_analyzed: int = Field(description="Number of days with data")


class FitnessMetricsOut(BaseModel):
    """Fitness-Fatigue model response."""

    ctl: float = Field(description="Chronic Training Load (fitness)")
    atl: float = Field(description="Acute Training Load (fatigue)")
    tsb: float = Field(description="Training Stress Balance (form)")
    form_zone: str = Field(description="Current form zone")
    readiness_score: float = Field(description="Readiness score 0-100")
    readiness_level: str = Field(description="Readiness level")
    ramp_rate: float | None = Field(description="CTL ramp rate (weekly change)")
    days_analyzed: int = Field(description="Number of days with data")


class StatBar(BaseModel):
    """A single stat bar (HP/MP/XP)."""

    current: float = Field(description="Current value")
    max: float = Field(description="Maximum value")
    label: str = Field(description="Human-readable label (French)")
    detail: str | None = Field(default=None, description="Raw value behind the bar")
    source: str | None = Field(default=None, description="Where the value comes from")


class PlayerStats(BaseModel):
    """RPG-style bars over real training data."""

    hp: StatBar = Field(
        description="Récupération: Garmin readiness (today or yesterday), else the CTL/ATL model"
    )
    mp: StatBar = Field(description="Forme: TSB mapped to 0-100")
    xp: StatBar = Field(description="Charge de la semaine: TSS vs the weekly goal")
    level: int = Field(description="Consecutive finished weeks at or above the goal")
    weeks_at_goal: int = Field(default=0, description="All-time count of weeks at goal")
    weekly_goal_tss: float = Field(default=0.0, description="Weekly TSS goal in use")


class RecommendationOut(BaseModel):
    """Single recommendation."""

    priority: str
    category: str
    title: str
    message: str
    actions: list[str] = Field(default_factory=list)


class RecommendationsResponse(BaseModel):
    """Recommendations response."""

    risk_level: str = Field(description="Overall risk level")
    primary_concern: str | None = Field(description="Main area of concern")
    recommendations: list[RecommendationOut]
    workload_status: WorkloadMetricsOut | None = None
    fitness_status: FitnessMetricsOut | None = None


def _weekly_goal_tss(settings: dict) -> float:
    """Weekly TSS goal derived from the user's weekly session goal."""
    sessions = int(settings.get("weekly_training_goal") or 6)  # 0/None -> default
    return sessions * TSS_PER_SESSION


def _week_history(
    goal_tss: float, by_date: dict[date, float], today: date
) -> tuple[int, int]:
    """(consecutive finished weeks at goal, all-time count of such weeks)."""
    if not by_date:
        return 0, 0
    weekly: dict[date, float] = {}
    for day, tss in by_date.items():
        monday = day - timedelta(days=day.weekday())
        weekly[monday] = weekly.get(monday, 0.0) + tss

    current_monday = today - timedelta(days=today.weekday())
    earliest = min(by_date)
    week_start = earliest - timedelta(days=earliest.weekday())
    reached: list[bool] = []
    while week_start < current_monday:
        reached.append(weekly.get(week_start, 0.0) >= goal_tss)
        week_start += timedelta(days=7)

    streak = 0
    for ok in reversed(reached):  # most recent finished week first
        if not ok:
            break
        streak += 1
    return streak, sum(reached)


def _recovery_bar(today: date, window: list[tuple], model: PerformanceModel) -> StatBar:
    """HP: Garmin's readiness for today, yesterday's if the night is not in yet,
    and the CTL/ATL model only when Garmin has nothing recent."""
    for offset in range(READINESS_LOOKBACK_DAYS + 1):
        day = today - timedelta(days=offset)
        score = compute_readiness(day, window=window)
        if score is None:
            continue
        detail = (
            "Garmin (VFC, sommeil, body battery)"
            if offset == 0
            else f"Garmin, mesure du {day.strftime('%d/%m')}"
        )
        return StatBar(
            current=float(score),
            max=100,
            label="Récupération",
            detail=detail,
            source="garmin" if offset == 0 else "garmin_previous",
        )

    return StatBar(
        current=round(model.readiness_score, 1),
        max=100,
        label="Récupération",
        detail="Estimée depuis la charge (aucune mesure Garmin récente)",
        source="model",
    )


def get_player_stats():
    """RPG bars over real data.

    - HP = Garmin readiness (HRV, sleep, body battery), yesterday's when the
      night is not published yet, model-based only as a last resort
    - MP = form: TSB mapped from -30..+30 onto 0..100
    - XP = this week's TSS against the goal derived from Settings
    - Level = consecutive finished weeks at or above that goal

    Four statements: settings, the readiness window, the daily TSS series
    (whole history, ~one row per training day) and the Banister coefficients.
    """
    today = date.today()
    settings = get_user_settings(user_id=1) or {}
    goal_tss = _weekly_goal_tss(settings)

    con = connect()
    try:
        window = fetch_window(con, today)
        by_date = daily_tss_by_date(con)
    finally:
        con.close()

    days = (today - timedelta(days=n) for n in range(FORM_HISTORY_DAYS, -1, -1))
    history = [DailyTSS(date=d, tss=by_date.get(d, 0.0)) for d in days]
    model = compute_performance_model(history, today)

    # --- HP: recovery ---
    hp = _recovery_bar(today, window, model)

    # --- MP: form (TSB) ---
    tsb = model.tsb
    mp_current = round(max(0.0, min(100.0, (tsb + 30) * (100 / 60))), 1)
    mp = StatBar(
        current=mp_current,
        max=100,
        label="Forme",
        detail=f"TSB {tsb:+.1f}",
        source="model",
    )

    # --- XP: this week's load ---
    monday = today - timedelta(days=today.weekday())
    xp_current = round(sum(t for d, t in by_date.items() if monday <= d <= today), 1)
    goal_sessions = int(settings.get("weekly_training_goal") or 6)
    xp = StatBar(
        current=xp_current,
        max=goal_tss,
        label="Charge de la semaine",
        detail=f"Objectif {goal_sessions} séances",
        source="model",
    )

    streak, total_weeks = _week_history(goal_tss, by_date, today)
    return PlayerStats(
        hp=hp,
        mp=mp,
        xp=xp,
        level=streak,
        weeks_at_goal=total_weeks,
        weekly_goal_tss=goal_tss,
    )


def get_workload_metrics(
    days: int = 28,
):
    """Get workload metrics (ACWR, Monotony, Strain) from training history.

    Analyzes the last N days of training data and computes:
    - ACWR: Acute:Chronic Workload Ratio (injury risk indicator)
    - Monotony: Training load variability
    - Strain: Accumulated fatigue
    """
    loads = training_loads(days=days)
    target_date = date.today()

    # Check if there's any training data
    has_data = any(load.duration_min > 0 for load in loads)
    if not has_data:
        # Return default values when no data
        return WorkloadMetricsOut(
            acwr=None,
            acwr_zone="unknown",
            acwr_ewma=None,
            monotony=None,
            monotony_zone="unknown",
            strain=None,
            strain_zone="unknown",
            acute_load=0.0,
            chronic_load=None,
            days_analyzed=0,
        )

    metrics = compute_workload_metrics(loads, target_date)

    return WorkloadMetricsOut(
        acwr=round(metrics.acwr, 3) if metrics.acwr else None,
        acwr_zone=metrics.acwr_zone.value if metrics.acwr_zone else None,
        acwr_ewma=round(metrics.acwr_ewma, 3) if metrics.acwr_ewma else None,
        monotony=round(metrics.monotony, 2) if metrics.monotony else None,
        monotony_zone=metrics.monotony_zone.value if metrics.monotony_zone else None,
        strain=round(metrics.strain, 1) if metrics.strain else None,
        strain_zone=metrics.strain_zone.value if metrics.strain_zone else None,
        acute_load=round(metrics.acute_load, 1),
        chronic_load=round(metrics.chronic_load, 1) if metrics.chronic_load else None,
        days_analyzed=len([load for load in loads if load.duration_min > 0]),
    )


def get_fitness_metrics(
    days: int = 42,
):
    """Get Fitness-Fatigue model metrics (CTL/ATL/TSB).

    Computes the Banister model:
    - CTL: Chronic Training Load (42-day EWMA) = Fitness
    - ATL: Acute Training Load (7-day EWMA) = Fatigue
    - TSB: Training Stress Balance = Form (CTL - ATL)
    """
    history = tss_history(days=days)
    target_date = date.today()

    # Check for data
    has_data = any(tss.tss > 0 for tss in history)
    if not has_data:
        # Return default values when no data
        return FitnessMetricsOut(
            ctl=0.0,
            atl=0.0,
            tsb=0.0,
            form_zone="neutral",
            readiness_score=50.0,
            readiness_level="moderate",
            ramp_rate=None,
            days_analyzed=0,
        )

    model = compute_performance_model(history, target_date)

    return FitnessMetricsOut(
        ctl=round(model.ctl, 1),
        atl=round(model.atl, 1),
        tsb=round(model.tsb, 1),
        form_zone=model.form_zone.value,
        readiness_score=round(model.readiness_score, 1),
        readiness_level=model.readiness_level.value,
        ramp_rate=round(model.ramp_rate, 2) if model.ramp_rate else None,
        days_analyzed=len([tss for tss in history if tss.tss > 0]),
    )


def get_recommendations(
    sport_type: Literal["cardio", "strength", "mixed"] = "mixed",
):
    """Get intelligent training recommendations based on current status.

    Analyzes workload and fitness metrics to provide actionable advice.
    """
    target_date = date.today()

    # Get current metrics
    workload = None
    loads = None
    try:
        loads = training_loads(days=28)
        if any(load.duration_min > 0 for load in loads):
            workload = compute_workload_metrics(loads, target_date)
    except Exception:
        logger.warning("Failed to compute workload metrics", exc_info=True)

    fitness = None
    tss = None
    try:
        tss = tss_history(days=42)
        if any(t.tss > 0 for t in tss):
            fitness = compute_performance_model(tss, target_date)
    except Exception:
        logger.warning("Failed to compute fitness metrics", exc_info=True)

    # Generate recommendations even without data (will give default advice)
    report: RecommendationReport = generate_recommendations(
        acwr=workload.acwr if workload else None,
        acwr_zone=workload.acwr_zone if workload else ACWRZone.UNKNOWN,
        monotony=workload.monotony if workload else None,
        monotony_zone=workload.monotony_zone if workload else None,
        strain=workload.strain if workload else None,
        strain_zone=workload.strain_zone if workload else None,
        tsb=fitness.tsb if fitness else None,
        form_zone=fitness.form_zone if fitness else None,
        readiness=fitness.readiness_level if fitness else None,
        ramp_rate=fitness.ramp_rate if fitness else None,
        chronic_load=workload.chronic_load if workload and workload.chronic_load else 0,
        sport_type=sport_type,
    )

    # Determine risk level from report
    risk_level = report.risk_level

    # Primary concern
    primary_concern = report.primary_concern

    # Build response
    workload_out = None
    if workload and loads:
        workload_out = WorkloadMetricsOut(
            acwr=round(workload.acwr, 3) if workload.acwr else None,
            acwr_zone=workload.acwr_zone.value if workload.acwr_zone else None,
            acwr_ewma=round(workload.acwr_ewma, 3) if workload.acwr_ewma else None,
            monotony=round(workload.monotony, 2) if workload.monotony else None,
            monotony_zone=workload.monotony_zone.value
            if workload.monotony_zone
            else None,
            strain=round(workload.strain, 1) if workload.strain else None,
            strain_zone=workload.strain_zone.value if workload.strain_zone else None,
            acute_load=round(workload.acute_load, 1),
            chronic_load=round(workload.chronic_load, 1)
            if workload.chronic_load
            else None,
            days_analyzed=len([load for load in loads if load.duration_min > 0]),
        )

    fitness_out = None
    if fitness and tss:
        fitness_out = FitnessMetricsOut(
            ctl=round(fitness.ctl, 1),
            atl=round(fitness.atl, 1),
            tsb=round(fitness.tsb, 1),
            form_zone=fitness.form_zone.value,
            readiness_score=round(fitness.readiness_score, 1),
            readiness_level=fitness.readiness_level.value,
            ramp_rate=round(fitness.ramp_rate, 2) if fitness.ramp_rate else None,
            days_analyzed=len([t for t in tss if t.tss > 0]),
        )

    return RecommendationsResponse(
        risk_level=risk_level,
        primary_concern=primary_concern,
        recommendations=[
            RecommendationOut(
                priority=r.priority.value,
                category=r.category.value,
                title=r.title,
                message=r.message,
                actions=r.actions,
            )
            for r in report.recommendations
        ],
        workload_status=workload_out,
        fitness_status=fitness_out,
    )
