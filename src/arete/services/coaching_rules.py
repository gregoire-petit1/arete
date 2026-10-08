"""Tips endpoints: the daily briefing, and feedback on a finished session.

Both are the coaching agent's work now, and both keep the rule engine
underneath: the rules extract the facts and always produce a usable sentence,
the agent turns them into something worth reading and files what it learned in
its journal. When the agent is unavailable, the rule text is what ships.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta
from typing import Literal

from pydantic import BaseModel, Field

from arete.dataio.queries import training_loads, tss_history
from arete.dataio.settings import athlete_zone_model, get_user_settings
from arete.features.fitness import compute_performance_model
from arete.features.workload import compute_workload_metrics
from arete.garmin.repository import GarminRepository
from arete.strength.repository import StrengthRepository

logger = logging.getLogger(__name__)


GOAL_ADVICE: dict[str, str] = {
    "build": "Tu peux monter de 5 à 10 % de charge cette semaine.",
    "peak": "Garde du jus : qualité plutôt que volume d'ici l'objectif.",
    "maintenance": "Tiens ce niveau, inutile d'en rajouter.",
    "recovery": "Reste en dessous du seuil : la récupération est la priorité.",
}


DEFAULT_FATIGUE_THRESHOLD = 85


def generate_daily_tip(
    acwr: float | None,
    tsb: float | None,
    readiness_score: float | None,
    fatigue_threshold: int = DEFAULT_FATIGUE_THRESHOLD,
    fitness_goal: str = "build",
) -> tuple[str, Literal["info", "warning", "alert"]]:
    """Rule-based daily tip, read against the athlete's own settings.

    Priority rules (first match wins):
    1. ACWR > 1.5 -> alert (injury danger)
    2. TSB < -25 -> alert (exhaustion)
    3. ACWR > 1.3 -> warning (overload)
    4. TSB < -10 -> warning (fatigue accumulating)
    5. readiness >= the athlete's fatigue threshold -> info (good form)
    6. ACWR 0.8-1.3 -> info (optimal zone), closed by the goal advice
    7. ACWR < 0.8 -> info (room to build), closed by the goal advice
    8. no metric at all -> info (log your sessions)

    Returns:
        (tip_text, priority)
    """
    goal_advice = GOAL_ADVICE.get(fitness_goal, GOAL_ADVICE["build"])
    if acwr is not None and acwr > 1.5:
        return (
            f"Ta charge aiguë dépasse largement la chronique (ACWR {acwr:.2f}). "
            "Réduis le volume dès aujourd'hui pour éviter la blessure.",
            "alert",
        )

    if tsb is not None and tsb < -25:
        return (
            f"Fraîcheur à {tsb:.0f} : tu es en épuisement. "
            "Prends une semaine de décharge.",
            "alert",
        )

    if acwr is not None and acwr > 1.3:
        return (
            f"Ta charge monte vite (ACWR {acwr:.2f}). "
            "Stabilise cette semaine et alterne séances dures et légères.",
            "warning",
        )

    if tsb is not None and tsb < -10:
        return (
            f"La fatigue s'accumule (fraîcheur {tsb:.0f}). "
            "Prévois une semaine de récupération bientôt.",
            "warning",
        )

    if readiness_score is not None and readiness_score >= fatigue_threshold:
        return (
            f"Préparation à {readiness_score:.0f}/100, au-dessus de ton seuil de "
            f"{fatigue_threshold}. C'est le jour pour une séance dure ou un test.",
            "info",
        )

    if acwr is not None and 0.8 <= acwr <= 1.3:
        return (
            f"Charge équilibrée (ACWR {acwr:.2f}). {goal_advice}",
            "info",
        )

    if acwr is not None and acwr < 0.8:
        return (
            f"Charge basse par rapport à tes 4 dernières semaines (ACWR {acwr:.2f}). "
            f"{goal_advice}",
            "info",
        )

    return (
        "Enregistre tes séances régulièrement pour recevoir des conseils adaptés.",
        "info",
    )


def daily_rule_tip(
    target_date: date | None = None,
) -> tuple[str, Literal["info", "warning", "alert"]]:
    """Today's rule-based tip and its priority.

    The deterministic floor under everything the coach says: it always
    produces a concrete, numeric sentence, and it is what the dashboard shows
    when the agent is unavailable or its run fails. The priority it returns is
    the one used either way — it drives the card's colour and must not depend
    on a model.
    """
    target_date = target_date or date.today()

    acwr: float | None = None
    try:
        loads = training_loads(days=28)
        if any(load.duration_min > 0 for load in loads):
            acwr = compute_workload_metrics(loads, target_date).acwr
    except Exception:
        logger.warning("Failed to compute workload metrics for tip", exc_info=True)

    tsb: float | None = None
    readiness_score: float | None = None
    try:
        tss = tss_history(days=42)
        if any(t.tss > 0 for t in tss):
            model = compute_performance_model(tss, target_date)
            tsb = model.tsb
            readiness_score = model.readiness_score
    except Exception:
        logger.warning("Failed to compute fitness metrics for tip", exc_info=True)

    settings = get_user_settings(user_id=1) or {}
    return generate_daily_tip(
        acwr,
        tsb,
        readiness_score,
        fatigue_threshold=int(
            settings.get("fatigue_threshold") or DEFAULT_FATIGUE_THRESHOLD
        ),
        fitness_goal=str(settings.get("fitness_goal") or "build"),
    )


class PostSessionResponse(BaseModel):
    """Post-session feedback response."""

    feedback: str = Field(description="Main feedback text in French")
    highlights: list[str] = Field(description="Key highlights in French")
    source: Literal["agent", "rules"] = Field(
        default="rules",
        description="Whether the coaching agent wrote it, or the rule engine did",
    )


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


def _hr_zone_label(avg_hr: int) -> tuple[int, str]:
    """Zone number and French name for an average heart rate.

    Read against the athlete's own threshold, like every other zone in the
    app. The absolute bpm table this replaced was two zones off: at a
    threshold of 176, 155 bpm is endurance, and it was being reported as
    "zone 4 seuil".
    """
    return athlete_zone_model().labelled_zone_of(avg_hr)


def _pace_str(sec_per_km: float) -> str:
    """Convert seconds/km to mm:ss string."""
    minutes = int(sec_per_km) // 60
    seconds = int(sec_per_km) % 60
    return f"{minutes}:{seconds:02d}"


def _generate_strength_feedback(session_id: int) -> PostSessionResponse:
    repo = StrengthRepository()
    session = repo.get_session(session_id)
    if session is None:
        raise LookupError("Strength session not found")

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

    rule_feedback = " ".join(feedback_parts)
    rule_highlights = highlights[:5]

    return PostSessionResponse(
        feedback=rule_feedback,
        highlights=rule_highlights,
        source="rules",
    )


def _generate_cardio_feedback(session_id: int) -> PostSessionResponse:
    repo = GarminRepository()
    session = repo.get_actual_session(session_id)
    if session is None:
        raise LookupError("Cardio session not found")

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
            feedback_parts.append("Bon travail en tempo, au-dessus de l'endurance.")
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

    rule_feedback = " ".join(feedback_parts)
    rule_highlights = highlights[:5]

    return PostSessionResponse(
        feedback=rule_feedback,
        highlights=rule_highlights,
        source="rules",
    )
