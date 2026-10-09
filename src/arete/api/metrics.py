"""Metrics API endpoints.

Exposes training metrics computed from features module.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from arete.features.cardio import (
    ZONE_DEFINITIONS,
    Sex,
    calculate_hr_ratio,
    calculate_trimp,
    get_hr_zone,
)
from arete.features.strength import (
    calculate_inol,
    estimate_1rm_average,
    estimate_1rm_brzycki,
    estimate_1rm_epley,
    estimate_1rm_rpe,
    get_strength_zone,
)
from arete.services import metrics as service
from arete.services.metrics import (
    FitnessMetricsOut,
    PlayerStats,
    RecommendationsResponse,
    WorkloadMetricsOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/metrics", tags=["metrics"])


# ---------- Schemas ----------


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


@router.get("/player-stats", response_model=PlayerStats)
def get_player_stats():
    """RPG bars over real data.

    - HP = Garmin readiness (HRV, sleep, body battery), yesterday's when the
      night is not published yet, model-based only as a last resort
    - MP = form: TSB mapped from -30..+30 onto 0..100
    - XP = this week's TSS against the goal derived from Settings
    - Level = consecutive finished weeks at or above that goal
    """
    return service.get_player_stats()


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
    return service.get_workload_metrics(days=days)


@router.get("/paces")
def get_paces():
    """Daniels VDOT, training paces (s/km) and race equivalents (s)."""
    return service.get_paces()


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
    return service.get_fitness_metrics(days=days)


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
    return service.get_recommendations(sport_type=sport_type)
