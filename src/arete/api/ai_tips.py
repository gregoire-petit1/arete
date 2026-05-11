"""AI tips endpoints: daily tips and post-session feedback.

Generates contextual French training tips based on current metrics.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from arete.api.metrics import _get_training_loads, _get_tss_history
from arete.features.fitness import compute_performance_model
from arete.features.workload import ACWRZone, compute_workload_metrics
from arete.garmin.repository import GarminRepository
from arete.strength.repository import StrengthRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/tips", tags=["tips"])


# ---------- Schemas ----------
class DailyTipResponse(BaseModel):
    """Daily tip response."""

    tip: str = Field(description="Contextual training tip in French")
    priority: Literal["info", "warning", "alert"] = Field(
        description="Tip priority level"
    )
    generated_at: str = Field(description="ISO 8601 generation timestamp")


# ---------- Tip generation ----------
def generate_daily_tip(
    acwr: float | None,
    tsb: float | None,
    readiness_score: float | None,
) -> tuple[str, Literal["info", "warning", "alert"]]:
    """Generate a rule-based daily tip from current metrics.

    Priority rules (first match wins):
    1. ACWR > 1.5 → alert (injury danger)
    2. TSB < -25 → alert (exhaustion)
    3. ACWR > 1.3 → warning (overload)
    4. TSB < -10 → warning (fatigue accumulating)
    5. readiness >= 80 → info (good form)
    6. ACWR and 0.8-1.3 → info (optimal zone)
    7. fallback → info (generic)

    Returns:
        (tip_text, priority)
    """
    # Alert-level checks
    if acwr is not None and acwr > 1.5:
        return (
            f"Votre ratio de charge aiguë/chronique ({acwr:.2f}) est dangereux. "
            "Réduisez immédiatement le volume pour éviter une blessure.",
            "alert",
        )

    if tsb is not None and tsb < -25:
        return (
            f"Votre TSB ({tsb:.0f}) indique un état d'épuisement. "
            "Prenez une semaine de décharge pour récupérer.",
            "alert",
        )

    # Warning-level checks
    if acwr is not None and acwr > 1.3:
        return (
            f"Votre ACWR ({acwr:.2f}) est élevé. "
            "Stabilisez votre charge cette semaine et alternez séances intenses et légères.",
            "warning",
        )

    if tsb is not None and tsb < -10:
        return (
            f"La fatigue s'accumule (TSB {tsb:.0f}). "
            "Planifiez une semaine de récupération prochainement.",
            "warning",
        )

    # Info-level checks
    if readiness_score is not None and readiness_score >= 80:
        return (
            "Vous êtes en excellente forme ! "
            "C'est le moment idéal pour une séance intense ou un test de performance.",
            "info",
        )

    if acwr is not None and 0.8 <= acwr <= 1.3:
        return (
            f"Votre charge d'entraînement est optimale (ACWR {acwr:.2f}). "
            "Continuez sur cette lancée, vous pouvez progresser de 5-10% par semaine.",
            "info",
        )

    # Fallback
    return (
        "Enregistrez vos séances régulièrement pour obtenir des conseils personnalisés.",
        "info",
    )


# ---------- Endpoint ----------
@router.get("/daily", response_model=DailyTipResponse)
def get_daily_tip() -> DailyTipResponse:
    """Get a contextual daily training tip based on current metrics."""
    target_date = date.today()

    # Fetch workload metrics
    acwr: float | None = None
    try:
        loads = _get_training_loads(days=28)
        if any(load.duration_min > 0 for load in loads):
            workload = compute_workload_metrics(loads, target_date)
            acwr = workload.acwr
    except Exception:
        logger.warning("Failed to compute workload metrics for tip", exc_info=True)

    # Fetch fitness metrics
    tsb: float | None = None
    readiness_score: float | None = None
    try:
        tss = _get_tss_history(days=42)
        if any(t.tss > 0 for t in tss):
            model = compute_performance_model(tss, target_date)
            tsb = model.tsb
            readiness_score = model.readiness_score
    except Exception:
        logger.warning("Failed to compute fitness metrics for tip", exc_info=True)

    tip, priority = generate_daily_tip(acwr, tsb, readiness_score)

    return DailyTipResponse(
        tip=tip,
        priority=priority,
        generated_at=datetime.now(timezone.utc).isoformat(),
    )


# ==========================================================================
# POST /tips/post-session — Post-workout feedback
# ==========================================================================


class PostSessionRequest(BaseModel):
    """Request body for post-session feedback."""

    session_type: Literal["strength", "cardio"]
    session_id: int


class PostSessionResponse(BaseModel):
    """Post-session feedback response."""

    feedback: str = Field(description="Main feedback text in French")
    highlights: list[str] = Field(description="Key highlights in French")


# ── Muscle group French labels ──────────────────────────────────────────

_MUSCLE_FR: dict[str, str] = {
    "chest": "pectoraux",
    "shoulders": "épaules",
    "triceps": "triceps",
    "back": "dos",
    "biceps": "biceps",
    "forearms": "avant-bras",
    "abs": "abdominaux",
    "obliques": "obliques",
    "lower_back": "lombaires",
    "quads": "quadriceps",
    "hamstrings": "ischio-jambiers",
    "glutes": "fessiers",
    "calves": "mollets",
    "adductors": "adducteurs",
    "full_body": "corps entier",
}


def _muscle_label(key: str) -> str:
    return _MUSCLE_FR.get(key, key)


# ── HR zone helper ──────────────────────────────────────────────────────


def _hr_zone_label(avg_hr: int) -> tuple[int, str]:
    """Return (zone_number, zone_description) for a given avg HR.

    Simplified Karvonen-style zones assuming max HR ~190.
    """
    if avg_hr < 120:
        return 1, "récupération active"
    if avg_hr < 140:
        return 2, "endurance fondamentale"
    if avg_hr < 155:
        return 3, "aérobie"
    if avg_hr < 170:
        return 4, "seuil"
    return 5, "VO2max"


def _pace_str(sec_per_km: float) -> str:
    """Convert seconds/km to mm:ss string."""
    minutes = int(sec_per_km) // 60
    seconds = int(sec_per_km) % 60
    return f"{minutes}:{seconds:02d}"


# ── Strength feedback ───────────────────────────────────────────────────


def _generate_strength_feedback(session_id: int) -> PostSessionResponse:
    repo = StrengthRepository()
    session = repo.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Strength session not found")

    # Compute volume per muscle for this session
    session_volume: dict[str, float] = {}
    for ex in session.exercises:
        if ex.exercise is None:
            continue
        muscle = ex.exercise.primary_muscle.value
        for s in ex.sets:
            if s.is_warmup:
                continue
            vol = (s.reps or 0) * (s.weight_kg or 0)
            session_volume[muscle] = session_volume.get(muscle, 0) + vol

    if not session_volume:
        return PostSessionResponse(
            feedback="Séance enregistrée ! Continuez à vous entraîner régulièrement.",
            highlights=["Séance complétée"],
        )

    # Compare vs last 4 weeks average
    session_date = session.date if isinstance(session.date, date) else date.today()
    end_ref = session_date - timedelta(days=1)
    start_ref = end_ref - timedelta(days=28)
    ref_volume = repo.get_volume_by_muscle(
        start_date=start_ref, end_date=end_ref, include_secondary=False
    )

    # Weeks in reference period (4)
    highlights: list[str] = []
    feedback_parts: list[str] = []

    for muscle, vol in sorted(session_volume.items(), key=lambda x: -x[1]):
        label = _muscle_label(muscle)
        ref_weekly = ref_volume.get(muscle, 0) / 4.0 if ref_volume.get(muscle) else 0

        if ref_weekly > 0:
            delta_pct = (vol - ref_weekly) / ref_weekly * 100
            if delta_pct > 5:
                highlights.append(
                    f"Volume {label} en hausse de {delta_pct:.0f}% vs les 4 dernières semaines"
                )
            elif delta_pct < -15:
                highlights.append(
                    f"Volume {label} en baisse de {abs(delta_pct):.0f}% — pensez à progresser"
                )
        else:
            highlights.append(
                f"{label.capitalize()} travaillé ({vol:.0f} kg de volume)"
            )

    total_vol = sum(session_volume.values())
    muscles_worked = [_muscle_label(m) for m in session_volume]
    feedback_parts.append(
        f"Séance musculation terminée — {total_vol:.0f} kg de volume total "
        f"sur {', '.join(muscles_worked)}."
    )

    if session.overall_rpe:
        feedback_parts.append(f"RPE ressenti : {session.overall_rpe}/10.")

    if not highlights:
        highlights.append("Séance complétée avec succès")

    return PostSessionResponse(
        feedback=" ".join(feedback_parts),
        highlights=highlights[:5],
    )


# ── Cardio feedback ─────────────────────────────────────────────────────


def _generate_cardio_feedback(session_id: int) -> PostSessionResponse:
    repo = GarminRepository()
    session = repo.get_actual_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Cardio session not found")

    highlights: list[str] = []
    feedback_parts: list[str] = []

    sport = session.sport or "activité"
    duration_min = (session.duration_sec or 0) // 60

    feedback_parts.append(f"Séance de {sport} terminée ({duration_min} min).")

    # HR feedback
    if session.avg_hr and session.max_hr:
        zone_num, zone_desc = _hr_zone_label(int(session.avg_hr))
        highlights.append(
            f"FC moyenne à {session.avg_hr:.0f} bpm, zone {zone_num} {zone_desc}"
        )
        highlights.append(f"FC max à {session.max_hr:.0f} bpm")

        if zone_num <= 2:
            feedback_parts.append("Bon travail de fond, intensité bien maîtrisée.")
        elif zone_num == 3:
            feedback_parts.append("Bon travail de fond en zone aérobie.")
        elif zone_num >= 4:
            feedback_parts.append("Séance intense — prévoyez une récupération adaptée.")

    # Pace feedback
    if session.avg_pace_sec_km and session.avg_pace_sec_km > 0:
        pace = _pace_str(session.avg_pace_sec_km)
        highlights.append(f"Allure moyenne : {pace} /km")

    # Distance
    if session.distance_m and session.distance_m > 0:
        km = session.distance_m / 1000
        highlights.append(f"Distance : {km:.1f} km")

    # Calories
    if session.calories and session.calories > 0:
        highlights.append(f"{session.calories} kcal dépensées")

    if not highlights:
        feedback_parts.append("Continuez à vous entraîner régulièrement.")
        highlights.append("Séance complétée")

    return PostSessionResponse(
        feedback=" ".join(feedback_parts),
        highlights=highlights[:5],
    )


# ── Endpoint ────────────────────────────────────────────────────────────


@router.post("/post-session", response_model=PostSessionResponse)
def post_session_feedback(body: PostSessionRequest) -> PostSessionResponse:
    """Generate rule-based post-workout feedback in French."""
    if body.session_type == "strength":
        return _generate_strength_feedback(body.session_id)
    else:
        return _generate_cardio_feedback(body.session_id)
