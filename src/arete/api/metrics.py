"""Metrics API endpoints.

Exposes training metrics computed from features module.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from arete.dataio.db import connect
from arete.features.cardio import (
    ZONE_DEFINITIONS,
    Sex,
    calculate_hr_ratio,
    calculate_trimp,
    get_hr_zone,
)
from arete.features.fitness import (
    DailyTSS,
    compute_performance_model,
)
from arete.features.recommendations import (
    RecommendationReport,
    generate_recommendations,
)
from arete.features.strength import (
    calculate_inol,
    estimate_1rm_average,
    estimate_1rm_brzycki,
    estimate_1rm_epley,
    estimate_1rm_rpe,
    get_strength_zone,
)
from arete.features.workload import (
    ACWRZone,
    DailyLoad,
    compute_workload_metrics,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metrics", tags=["metrics"])


# ---------- Schemas ----------
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


class TRIMPRequest(BaseModel):
    """TRIMP calculation request."""

    duration_min: int = Field(gt=0, description="Session duration in minutes")
    avg_hr: int = Field(gt=0, description="Average heart rate")
    hr_rest: int = Field(gt=0, description="Resting heart rate")
    hr_max: int = Field(gt=0, description="Maximum heart rate")
    gender: Literal["male", "female"] = Field(description="Gender for weighting")


class TRIMPResponse(BaseModel):
    """TRIMP calculation response."""

    trimp: float = Field(description="Training Impulse value")
    hr_reserve_pct: float = Field(description="Heart rate reserve percentage")
    hr_zone: int = Field(description="Heart rate zone (1-5)")
    zone_name: str = Field(description="Zone name in French")
    intensity: str = Field(description="Intensity description")


class OneRMRequest(BaseModel):
    """1RM estimation request."""

    weight: float = Field(gt=0, description="Weight lifted (kg)")
    reps: int = Field(gt=0, le=30, description="Number of repetitions")
    rpe: float | None = Field(
        None, ge=6, le=10, description="Rate of Perceived Exertion (optional)"
    )


class OneRMResponse(BaseModel):
    """1RM estimation response."""

    estimated_1rm: float = Field(description="Estimated 1RM (average of formulas)")
    epley: float = Field(description="Epley formula estimate")
    brzycki: float = Field(description="Brzycki formula estimate")
    rpe_based: float | None = Field(description="RPE-based estimate (if RPE provided)")
    strength_zone: str = Field(description="Training zone for given weight")
    intensity_pct: float = Field(description="Intensity as % of estimated 1RM")


class INOLRequest(BaseModel):
    """INOL calculation request."""

    reps: int = Field(gt=0, description="Total repetitions")
    intensity_pct: float = Field(gt=0, lt=100, description="Intensity as % of 1RM")


class INOLResponse(BaseModel):
    """INOL calculation response."""

    inol: float = Field(description="Intensity Number of Lifts")
    classification: str = Field(description="INOL classification")


class StatBar(BaseModel):
    """A single stat bar (HP/MP/XP)."""

    current: float = Field(description="Current value")
    max: float = Field(description="Maximum value")
    label: str = Field(description="Human-readable label")


class PlayerStats(BaseModel):
    """Player stats response (RPG-style HP/MP/XP/Level)."""

    hp: StatBar = Field(description="Health Points (Recovery/Readiness)")
    mp: StatBar = Field(description="Mana Points (Fitness/CTL)")
    xp: StatBar = Field(description="Experience Points (Weekly Volume/TSS)")
    level: int = Field(description="Player level (completed weeks at goal)")


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


# ---------- Helper Functions ----------
def _get_training_loads(days: int = 28) -> list[DailyLoad]:
    """Fetch daily training loads from actual_sessions.

    Returns list of DailyLoad objects for the last N days.
    Uses RPE * duration as load metric.
    """
    con = connect(read_only=True)
    try:
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        # Get daily aggregated loads
        rows = con.execute(
            """
            SELECT date,
                   SUM(COALESCE(duration_sec, 0)) / 60.0 as total_duration,
                   AVG(COALESCE(rpe, 5)) as avg_rpe
            FROM app.actual_sessions
            WHERE date >= ? AND date <= ?
              AND user_id = 1
            GROUP BY date
            ORDER BY date ASC
            """,
            [start_date, end_date],
        ).fetchall()

        # Create a dict of date -> (duration, rpe)
        data_by_date = {row[0]: (int(row[1]), float(row[2])) for row in rows}

        # Build DailyLoad list for all days (zeros for missing)
        loads = []
        current = start_date
        while current <= end_date:
            if current in data_by_date:
                duration, rpe = data_by_date[current]
                loads.append(DailyLoad(date=current, duration_min=duration, rpe=rpe))
            else:
                loads.append(DailyLoad(date=current, duration_min=0, rpe=0))
            current += timedelta(days=1)

        return loads
    finally:
        con.close()


def _get_tss_history(days: int = 42) -> list[DailyTSS]:
    """Fetch daily TSS-like values from actual_sessions.

    Uses TSS fallback chain: RPE → suffer_score → HR-based → default (RPE 5).
    TSS estimation: (duration * intensity^2) / 0.36
    where intensity = RPE / 10. This approximates 100 TSS for 1 hour at RPE 6.
    """
    con = connect(read_only=True)
    try:
        end_date = date.today()
        start_date = end_date - timedelta(days=days)

        rows = con.execute(
            """
            SELECT date,
                   SUM(
                     CASE
                       WHEN rpe IS NOT NULL THEN
                         (COALESCE(duration_sec, 0) / 60.0) * POWER(rpe / 10.0, 2) / 0.36
                       WHEN suffer_score IS NOT NULL THEN
                         suffer_score * 0.8
                       WHEN avg_hr IS NOT NULL THEN
                         (COALESCE(duration_sec, 0) / 60.0) * POWER(LEAST(avg_hr, 200) / 180.0, 2) / 0.36
                       ELSE
                         (COALESCE(duration_sec, 0) / 60.0) * 0.25 / 0.36
                     END
                   ) as daily_tss
            FROM app.actual_sessions
            WHERE date >= ? AND date <= ?
              AND user_id = 1
            GROUP BY date
            ORDER BY date ASC
            """,
            [start_date, end_date],
        ).fetchall()

        tss_by_date = {row[0]: float(row[1]) for row in rows}

        tss_list = []
        current = start_date
        while current <= end_date:
            tss = tss_by_date.get(current, 0.0)
            tss_list.append(DailyTSS(date=current, tss=tss))
            current += timedelta(days=1)

        return tss_list
    finally:
        con.close()


# ---------- Endpoints ----------


def _get_user_settings() -> dict:
    """Fetch user settings or return defaults."""
    con = connect(read_only=True)
    try:
        row = con.execute(
            "SELECT * FROM app.user_settings WHERE user_id = 1"
        ).fetchone()
        if row:
            columns = [desc[0] for desc in con.description]
            return dict(zip(columns, row, strict=True))
        return {}
    except Exception:
        return {}
    finally:
        con.close()


def _compute_weekly_tss(start_monday: date, end_date: date) -> float:
    """Sum TSS from start_monday to end_date (inclusive)."""
    con = connect(read_only=True)
    try:
        row = con.execute(
            """
            SELECT COALESCE(SUM(
              CASE
                WHEN rpe IS NOT NULL THEN
                  (COALESCE(duration_sec, 0) / 60.0) * POWER(rpe / 10.0, 2) / 0.36
                WHEN suffer_score IS NOT NULL THEN
                  suffer_score * 0.8
                WHEN avg_hr IS NOT NULL THEN
                  (COALESCE(duration_sec, 0) / 60.0) * POWER(LEAST(avg_hr, 200) / 180.0, 2) / 0.36
                ELSE
                  (COALESCE(duration_sec, 0) / 60.0) * 0.25 / 0.36
              END
            ), 0)
            FROM app.actual_sessions
            WHERE date >= ? AND date <= ?
              AND user_id = 1
            """,
            [start_monday, end_date],
        ).fetchone()
        return float(row[0]) if row else 0.0
    except Exception:
        return 0.0
    finally:
        con.close()


def _compute_level(weekly_tss_goal: float) -> int:
    """Count completed past weeks where weekly TSS >= goal."""
    con = connect(read_only=True)
    try:
        today = date.today()
        # Get the Monday of the current week
        current_monday = today - timedelta(days=today.weekday())

        # Get earliest training date
        row = con.execute(
            "SELECT MIN(date) FROM app.actual_sessions WHERE user_id = 1"
        ).fetchone()
        if not row or not row[0]:
            return 0

        earliest = row[0]
        # Align to Monday
        start_monday = earliest - timedelta(days=earliest.weekday())

        level = 0
        week_start = start_monday
        while week_start < current_monday:
            week_end = week_start + timedelta(days=6)
            week_tss = _compute_weekly_tss(week_start, week_end)
            if week_tss >= weekly_tss_goal:
                level += 1
            week_start += timedelta(days=7)

        return level
    except Exception:
        return 0
    finally:
        con.close()


@router.get("/player-stats", response_model=PlayerStats)
def get_player_stats():
    """Get RPG-style player stats (HP/MP/XP/Level).

    - HP = Readiness score (0-100) from fitness-fatigue model
    - MP = CTL progress toward target (0-100)
    - XP = Weekly TSS accumulated this week
    - Level = Count of past weeks where weekly TSS >= goal
    """
    today = date.today()

    # --- Settings ---
    settings = _get_user_settings()
    target_ctl = float(settings.get("desired_training_load", 0) or 0) or 50.0
    weekly_tss_goal = 300.0  # Default; not in user_settings schema

    # --- HP: Readiness ---
    tss_history = _get_tss_history(days=42)
    has_data = any(tss.tss > 0 for tss in tss_history)
    if has_data:
        model = compute_performance_model(tss_history, today)
        hp_current = round(model.readiness_score, 1)
        ctl_value = model.ctl
    else:
        hp_current = 50.0
        ctl_value = 0.0

    # --- MP: Fitness (CTL / target) ---
    mp_current = round(min(100.0, ctl_value / target_ctl * 100), 1)

    # --- XP: Weekly TSS ---
    monday = today - timedelta(days=today.weekday())
    xp_current = round(_compute_weekly_tss(monday, today), 1)

    # --- Level ---
    level = _compute_level(weekly_tss_goal)

    return PlayerStats(
        hp=StatBar(current=hp_current, max=100, label="Recovery"),
        mp=StatBar(current=mp_current, max=100, label="Fitness"),
        xp=StatBar(current=xp_current, max=weekly_tss_goal, label="Weekly Volume"),
        level=level,
    )


@router.get("/workload", response_model=WorkloadMetricsOut)
def get_workload_metrics(
    days: int = Query(28, ge=7, le=90, description="Days to analyze"),
):
    """Get workload metrics (ACWR, Monotony, Strain) from training history.

    Analyzes the last N days of training data and computes:
    - ACWR: Acute:Chronic Workload Ratio (injury risk indicator)
    - Monotony: Training load variability
    - Strain: Accumulated fatigue
    """
    loads = _get_training_loads(days=days)
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


@router.get("/fitness", response_model=FitnessMetricsOut)
def get_fitness_metrics(
    days: int = Query(42, ge=14, le=120, description="Days to analyze"),
):
    """Get Fitness-Fatigue model metrics (CTL/ATL/TSB).

    Computes the Banister model:
    - CTL: Chronic Training Load (42-day EWMA) = Fitness
    - ATL: Acute Training Load (7-day EWMA) = Fatigue
    - TSB: Training Stress Balance = Form (CTL - ATL)
    """
    tss_history = _get_tss_history(days=days)
    target_date = date.today()

    # Check for data
    has_data = any(tss.tss > 0 for tss in tss_history)
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

    model = compute_performance_model(tss_history, target_date)

    return FitnessMetricsOut(
        ctl=round(model.ctl, 1),
        atl=round(model.atl, 1),
        tsb=round(model.tsb, 1),
        form_zone=model.form_zone.value,
        readiness_score=round(model.readiness_score, 1),
        readiness_level=model.readiness_level.value,
        ramp_rate=round(model.ramp_rate, 2) if model.ramp_rate else None,
        days_analyzed=len([tss for tss in tss_history if tss.tss > 0]),
    )


@router.post("/cardio/trimp", response_model=TRIMPResponse)
def calculate_trimp_endpoint(request: TRIMPRequest):
    """Calculate TRIMP (Training Impulse) for a cardio session.

    TRIMP quantifies training load based on duration and heart rate intensity.
    Uses gender-specific weighting (Banister method).
    """
    sex = Sex.MALE if request.gender == "male" else Sex.FEMALE

    trimp = calculate_trimp(
        duration_min=request.duration_min,
        hr_avg=request.avg_hr,
        hr_max=request.hr_max,
        hr_rest=request.hr_rest,
        sex=sex,
    )

    hr_reserve_pct = calculate_hr_ratio(request.avg_hr, request.hr_max, request.hr_rest)
    hr_zone = get_hr_zone(request.avg_hr, request.hr_max)
    zone_info = ZONE_DEFINITIONS[hr_zone]

    return TRIMPResponse(
        trimp=round(trimp, 1),
        hr_reserve_pct=round(hr_reserve_pct * 100, 1),
        hr_zone=hr_zone.value,
        zone_name=zone_info.name,
        intensity=zone_info.description,
    )


@router.post("/strength/1rm", response_model=OneRMResponse)
def estimate_1rm_endpoint(request: OneRMRequest):
    """Estimate 1RM (one-rep max) from submaximal lift.

    Uses multiple formulas (Epley, Brzycki) and provides average.
    Optionally uses RPE for more accurate estimation.
    """
    epley = estimate_1rm_epley(request.weight, request.reps)
    brzycki = estimate_1rm_brzycki(request.weight, request.reps)
    average = estimate_1rm_average(request.weight, request.reps)

    rpe_estimate = None
    if request.rpe is not None:
        rpe_estimate = estimate_1rm_rpe(request.weight, request.reps, request.rpe)

    # Use RPE estimate if available, otherwise use average
    best_estimate = rpe_estimate if rpe_estimate else average

    # Calculate intensity and zone
    intensity_pct = (request.weight / best_estimate) * 100 if best_estimate > 0 else 0
    zone = get_strength_zone(intensity_pct / 100)  # Function expects decimal

    return OneRMResponse(
        estimated_1rm=round(best_estimate, 1),
        epley=round(epley, 1),
        brzycki=round(brzycki, 1),
        rpe_based=round(rpe_estimate, 1) if rpe_estimate else None,
        strength_zone=zone.name,
        intensity_pct=round(intensity_pct, 1),
    )


@router.post("/strength/inol", response_model=INOLResponse)
def calculate_inol_endpoint(request: INOLRequest):
    """Calculate INOL (Intensity Number of Lifts) for a strength session.

    INOL = reps / (100 - intensity%)
    Helps manage training volume and fatigue.
    """
    inol = calculate_inol(request.reps, request.intensity_pct)

    # Classify INOL
    if inol < 0.5:
        classification = "Léger (récupération)"
    elif inol < 1.0:
        classification = "Modéré (développement)"
    elif inol < 2.0:
        classification = "Élevé (surcharge)"
    else:
        classification = "Très élevé (risque de surentraînement)"

    return INOLResponse(
        inol=round(inol, 2),
        classification=classification,
    )


@router.get("/recommendations", response_model=RecommendationsResponse)
def get_recommendations(
    sport_type: Literal["cardio", "strength", "mixed"] = Query(
        "mixed", description="Sport type for specific recommendations"
    ),
):
    """Get intelligent training recommendations based on current status.

    Analyzes workload and fitness metrics to provide actionable advice.
    """
    target_date = date.today()

    # Get current metrics
    workload = None
    loads = None
    try:
        loads = _get_training_loads(days=28)
        if any(load.duration_min > 0 for load in loads):
            workload = compute_workload_metrics(loads, target_date)
    except Exception:
        logger.warning("Failed to compute workload metrics", exc_info=True)

    fitness = None
    tss = None
    try:
        tss = _get_tss_history(days=42)
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
