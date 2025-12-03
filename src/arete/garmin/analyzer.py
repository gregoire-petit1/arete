"""Activity analysis using LLM.

Compares planned vs actual sessions and provides insights.
Token-optimized for Groq free tier.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from arete.garmin.models import ActualSession, PlannedSession
from arete.llm.client import get_client
from arete.llm.token_manager import get_token_manager

if TYPE_CHECKING:
    from arete.garmin.time_series import DerivedMetrics, WorkoutStructure

logger = logging.getLogger(__name__)

# Token budget for analysis (smaller than plan generation)
MAX_COMPLETION_TOKENS = 400
DEFAULT_MODEL = "llama-3.3-70b-versatile"


@dataclass
class ActivityAnalysis:
    """LLM-generated activity analysis."""

    actual_session_id: int
    analysis_type: str  # 'adherence', 'performance', 'summary'
    insights: dict  # Structured insights
    recommendations: str  # Text recommendations
    generated_by: str = "llm"  # 'llm', 'rules', 'fallback'
    created_at: datetime | None = None

    def to_dict(self) -> dict:
        """Convert to dict for DB."""
        return {
            "actual_session_id": self.actual_session_id,
            "analysis_type": self.analysis_type,
            "insights_json": json.dumps(self.insights),
            "recommendations": self.recommendations,
            "generated_by": self.generated_by,
        }


def _build_analysis_system_prompt(
    detailed: bool = False, is_interval: bool = False
) -> str:
    """Compact system prompt for activity analysis (~200 tokens)."""
    if is_interval:
        return """Coach course expert, spécialiste séances qualité. Analyse interval workout. JSON uniquement.

RÈGLES:
- Évalue cohérence des intervalles (pace, HR)
- Analyse progression/fatigue inter-répétitions
- Identifie récupérations (trop longues/courtes)
- Compare au workout planifié si fourni
- Conseils techniques spécifiques

FORMAT JSON:
{"execution":{"note":"A-F","respect_structure":"oui|partiel|non","regularite":"excellente|bonne|variable"},"intervalles":{"analyse":"...","progression":"positive|stable|fatigue","meilleur_intervalle":N,"pire_intervalle":N},"recuperations":{"analyse":"...","adequates":"oui|non"},"physiologie":{"hr_evolution":"...","recup_cardiaque":"bonne|moyenne|lente"},"recommendation_prioritaire":"Une action clé"}"""

    if detailed:
        return """Coach course à pied expert. Analyse détaillée avec métriques avancées. JSON uniquement.

RÈGLES:
- Analyse HR drift et découplage cardiaque
- Évalue running dynamics (stance, oscillation, foulée)
- Identifie patterns de fatigue et pacing
- Conseils techniques spécifiques
- Ton expert mais accessible

FORMAT JSON:
{"performance":{"note":"A-F","forces":["..."],"faiblesses":["..."]},"technique":{"analyse":"...","conseils":["..."]},"physiologie":{"hr_analysis":"...","fatigue_indicators":["..."]},"pacing":{"evaluation":"...","suggestion":"..."},"recommendation_prioritaire":"Une action clé"}"""

    return """Coach course à pied. Analyse séance réalisée vs planifiée. JSON uniquement.

RÈGLES:
- Évalue adhérence (durée, distance, intensité)
- Identifie écarts significatifs (>15%)
- Suggestions concrètes et courtes
- Ton encourageant mais précis

FORMAT JSON:
{"adherence":{"score":0-100,"durée":"ok|court|long","distance":"ok|court|long","intensité":"ok|facile|dur"},"points_positifs":["..."],"points_amelioration":["..."],"recommendation":"Une phrase actionable"}"""


def _build_analysis_user_prompt(
    planned: PlannedSession | None,
    actual: ActualSession,
) -> str:
    """Build compact user prompt with session data."""
    lines = ["RÉALISÉ:"]

    # Actual session data
    lines.append(f"- Sport: {actual.sport}")
    lines.append(f"- Durée: {actual.duration_min:.0f} min")
    if actual.distance_km:
        lines.append(f"- Distance: {actual.distance_km:.2f} km")
    if actual.avg_hr:
        lines.append(f"- FC moy: {actual.avg_hr} bpm")
    if actual.max_hr:
        lines.append(f"- FC max: {actual.max_hr} bpm")
    if actual.avg_pace_min_km:
        lines.append(f"- Allure: {actual.avg_pace_min_km}/km")
    if actual.calories:
        lines.append(f"- Calories: {actual.calories}")

    # Planned session data (if matched)
    if planned:
        lines.append("\nPLANIFIÉ:")
        lines.append(f"- Type: {planned.session_type.value}")
        if planned.target_duration_min:
            lines.append(f"- Durée cible: {planned.target_duration_min} min")
        if planned.target_distance_km:
            lines.append(f"- Distance cible: {planned.target_distance_km:.1f} km")
        if planned.target_hr_zone:
            lines.append(f"- Zone FC: {planned.target_hr_zone}")
        if planned.target_intensity:
            lines.append(f"- Intensité: {planned.target_intensity}")
        if planned.description:
            lines.append(f"- Consigne: {planned.description[:100]}")
    else:
        lines.append("\nPLANIFIÉ: Aucune séance planifiée")

    lines.append("\nAnalyse:")
    return "\n".join(lines)


def _build_detailed_user_prompt(
    actual: ActualSession,
    planned: PlannedSession | None,
    metrics_json: str,
    workout_json: str | None = None,
) -> str:
    """Build user prompt with detailed metrics for in-depth analysis."""
    lines = ["ACTIVITÉ:"]
    lines.append(f"- Sport: {actual.sport}")
    lines.append(f"- Durée: {actual.duration_min:.0f} min")
    if actual.distance_km:
        lines.append(f"- Distance: {actual.distance_km:.2f} km")

    if planned:
        lines.append(f"\nOBJECTIF: {planned.session_type.value}")
        if planned.description:
            lines.append(f"Consigne: {planned.description[:80]}")

    # Include workout structure if available (for interval workouts)
    if workout_json:
        lines.append(f"\nSTRUCTURE WORKOUT:\n{workout_json}")

    lines.append(f"\nMÉTRIQUES DÉTAILLÉES:\n{metrics_json}")
    lines.append("\nAnalyse technique approfondie:")

    return "\n".join(lines)


def analyze_activity(
    actual: ActualSession,
    planned: PlannedSession | None = None,
    model: str | None = None,
) -> ActivityAnalysis:
    """Analyze activity comparing planned vs actual.

    Args:
        actual: The actual session from FIT/Garmin
        planned: Optional matched planned session
        model: LLM model to use (auto-selected if None)

    Returns:
        ActivityAnalysis with insights and recommendations
    """
    client = get_client()

    if client is None:
        logger.warning("No LLM client, using fallback analysis")
        return _generate_fallback_analysis(actual, planned)

    token_manager = get_token_manager()

    if model is None:
        model = token_manager.get_best_model(estimated_tokens=800)

    can_proceed, reason = token_manager.can_make_request(model, estimated_tokens=800)
    if not can_proceed:
        logger.warning(f"Rate limit: {reason}, using fallback")
        return _generate_fallback_analysis(actual, planned)

    token_manager.wait_if_needed(model, estimated_tokens=800)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _build_analysis_system_prompt()},
                {
                    "role": "user",
                    "content": _build_analysis_user_prompt(planned, actual),
                },
            ],
            temperature=0.5,  # Lower for more consistent analysis
            max_tokens=MAX_COMPLETION_TOKENS,
            response_format={"type": "json_object"},
        )

        # Track usage
        if response.usage:
            token_manager.record_usage(
                model=model,
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
            )

        content = response.choices[0].message.content
        if content:
            insights = json.loads(content)
            return ActivityAnalysis(
                actual_session_id=actual.id or 0,
                analysis_type="adherence" if planned else "summary",
                insights=insights,
                recommendations=insights.get("recommendation", ""),
                generated_by="llm",
            )

        return _generate_fallback_analysis(actual, planned)

    except Exception as e:
        logger.error(f"LLM analysis failed: {e}")
        return _generate_fallback_analysis(actual, planned)


def _generate_fallback_analysis(
    actual: ActualSession,
    planned: PlannedSession | None,
) -> ActivityAnalysis:
    """Rule-based fallback when LLM unavailable."""
    insights = {
        "adherence": {
            "score": 0,
            "durée": "n/a",
            "distance": "n/a",
            "intensité": "n/a",
        },
        "points_positifs": [],
        "points_amelioration": [],
        "recommendation": "",
    }

    if planned is None:
        # No planned session - just summarize
        insights["points_positifs"].append("Séance réalisée")
        if actual.duration_min >= 30:
            insights["points_positifs"].append("Durée correcte")
        if actual.avg_hr and actual.avg_hr < 160:
            insights["points_positifs"].append("FC modérée")
        insights["recommendation"] = (
            "Continuez à planifier vos séances pour un meilleur suivi"
        )

        return ActivityAnalysis(
            actual_session_id=actual.id or 0,
            analysis_type="summary",
            insights=insights,
            recommendations=insights["recommendation"],
            generated_by="rules",
        )

    # Compare with planned session
    score = 100

    # Duration comparison
    if planned.target_duration_min:
        ratio = actual.duration_min / planned.target_duration_min
        if 0.85 <= ratio <= 1.15:
            insights["adherence"]["durée"] = "ok"
            insights["points_positifs"].append("Durée respectée")
        elif ratio < 0.85:
            insights["adherence"]["durée"] = "court"
            insights["points_amelioration"].append(
                f"Séance écourtée ({actual.duration_min:.0f}/{planned.target_duration_min} min)"
            )
            score -= 15
        else:
            insights["adherence"]["durée"] = "long"
            insights["points_positifs"].append("Séance plus longue que prévu")
            score -= 5

    # Distance comparison
    if planned.target_distance_km and actual.distance_km:
        ratio = actual.distance_km / planned.target_distance_km
        if 0.85 <= ratio <= 1.15:
            insights["adherence"]["distance"] = "ok"
            insights["points_positifs"].append("Distance respectée")
        elif ratio < 0.85:
            insights["adherence"]["distance"] = "court"
            score -= 15
        else:
            insights["adherence"]["distance"] = "long"
            score -= 5

    # Intensity (simplified based on HR if available)
    if actual.avg_hr:
        if actual.avg_hr < 140:
            insights["adherence"]["intensité"] = "facile"
        elif actual.avg_hr < 165:
            insights["adherence"]["intensité"] = "ok"
        else:
            insights["adherence"]["intensité"] = "dur"
            if planned.target_intensity == "easy":
                insights["points_amelioration"].append(
                    "Intensité plus élevée que prévu"
                )
                score -= 10

    insights["adherence"]["score"] = max(0, score)

    # Generate recommendation
    if score >= 85:
        insights["recommendation"] = "Excellent travail, continuez ainsi!"
    elif score >= 70:
        insights["recommendation"] = "Bonne séance, quelques ajustements possibles"
    else:
        insights["recommendation"] = "Revoyez la planification pour mieux vous y tenir"

    return ActivityAnalysis(
        actual_session_id=actual.id or 0,
        analysis_type="adherence",
        insights=insights,
        recommendations=insights["recommendation"],
        generated_by="rules",
    )


def analyze_activity_detailed(
    actual: ActualSession,
    planned: PlannedSession | None = None,
    fit_file_path: str | None = None,
    model: str | None = None,
) -> ActivityAnalysis:
    """In-depth activity analysis using time series metrics.

    Parses the FIT file for detailed metrics (HR drift, running dynamics, etc.)
    and provides expert-level analysis. Supports interval workout detection.

    Args:
        actual: The actual session from database
        planned: Optional matched planned session
        fit_file_path: Path to the original FIT file for re-parsing
        model: LLM model to use

    Returns:
        ActivityAnalysis with detailed insights
    """
    from arete.garmin.fit_parser import FITParser
    from arete.garmin.time_series import ActivityMetricsCalculator

    # Parse FIT file with detailed time series
    if not fit_file_path:
        logger.warning("No FIT file path provided, falling back to basic analysis")
        return analyze_activity(actual, planned, model)

    try:
        parser = FITParser()
        parsed = parser.parse_file(fit_file_path, detailed=True)

        if not parsed.time_series:
            logger.warning("No time series data extracted")
            return analyze_activity(actual, planned, model)

        # Calculate derived metrics
        calculator = ActivityMetricsCalculator()
        metrics = calculator.calculate(parsed.time_series)

        # Convert to compact JSON for LLM
        metrics_json = metrics.to_compact_json()
        logger.info(f"Detailed metrics: {len(metrics_json)} chars")

        # Get workout structure if available
        workout_json: str | None = None
        is_interval = False
        if parsed.workout_structure:
            is_interval = parsed.workout_structure.is_interval_workout
            workout_json = parsed.workout_structure.to_compact_json()
            logger.info(f"Workout structure: {workout_json[:200]}...")

    except Exception as e:
        logger.error(f"Failed to parse FIT file for detailed analysis: {e}")
        return analyze_activity(actual, planned, model)

    # Call LLM with detailed prompt
    client = get_client()
    if client is None:
        return _generate_fallback_detailed_analysis(
            actual, metrics, parsed.workout_structure
        )

    token_manager = get_token_manager()
    if model is None:
        model = token_manager.get_best_model(estimated_tokens=1200)

    can_proceed, reason = token_manager.can_make_request(model, estimated_tokens=1200)
    if not can_proceed:
        logger.warning(f"Rate limit: {reason}, using fallback")
        return _generate_fallback_detailed_analysis(
            actual, metrics, parsed.workout_structure
        )

    token_manager.wait_if_needed(model, estimated_tokens=1200)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": _build_analysis_system_prompt(
                        detailed=True, is_interval=is_interval
                    ),
                },
                {
                    "role": "user",
                    "content": _build_detailed_user_prompt(
                        actual, planned, metrics_json, workout_json
                    ),
                },
            ],
            temperature=0.5,
            max_tokens=600,  # Slightly more for detailed analysis
            response_format={"type": "json_object"},
        )

        if response.usage:
            token_manager.record_usage(
                model=model,
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
            )

        content = response.choices[0].message.content
        if content:
            insights = json.loads(content)
            # Add raw metrics to insights
            insights["_metrics"] = json.loads(metrics_json)
            insights["_anomalies"] = metrics.anomalies
            # Add workout structure if available
            if workout_json:
                insights["_workout_structure"] = json.loads(workout_json)
                insights["_is_interval_workout"] = is_interval

            return ActivityAnalysis(
                actual_session_id=actual.id or 0,
                analysis_type="detailed" if not is_interval else "interval",
                insights=insights,
                recommendations=insights.get("recommendation_prioritaire", ""),
                generated_by="llm",
            )

    except Exception as e:
        logger.error(f"Detailed LLM analysis failed: {e}")

    return _generate_fallback_detailed_analysis(
        actual, metrics, parsed.workout_structure
    )


def _generate_fallback_detailed_analysis(
    actual: ActualSession,
    metrics: DerivedMetrics,
    workout_structure: WorkoutStructure | None = None,
) -> ActivityAnalysis:
    """Generate rule-based detailed analysis when LLM unavailable."""

    is_interval = workout_structure and workout_structure.is_interval_workout

    if is_interval and workout_structure:
        return _generate_fallback_interval_analysis(actual, metrics, workout_structure)

    insights = {
        "performance": {"note": "B", "forces": [], "faiblesses": []},
        "technique": {"analyse": "", "conseils": []},
        "physiologie": {"hr_analysis": "", "fatigue_indicators": []},
        "pacing": {"evaluation": "", "suggestion": ""},
        "recommendation_prioritaire": "",
        "_metrics": json.loads(metrics.to_compact_json()),
        "_anomalies": metrics.anomalies,
    }

    # Analyze based on metrics
    if metrics.hr_drift_pct:
        if metrics.hr_drift_pct < 5:
            insights["physiologie"]["hr_analysis"] = "Excellent contrôle cardiaque"
            insights["performance"]["forces"].append("Stabilité FC")
        elif metrics.hr_drift_pct < 10:
            insights["physiologie"]["hr_analysis"] = "Dérive cardiaque acceptable"
        else:
            insights["physiologie"]["hr_analysis"] = (
                f"Dérive cardiaque importante ({metrics.hr_drift_pct:.0f}%)"
            )
            insights["physiologie"]["fatigue_indicators"].append("HR drift élevé")

    if metrics.hr_decoupling_pct and metrics.hr_decoupling_pct > 5:
        insights["physiologie"]["fatigue_indicators"].append(
            f"Découplage {metrics.hr_decoupling_pct:.0f}% - efficacité aérobie réduite"
        )

    if metrics.pace_fade_pct:
        if metrics.pace_fade_pct < 3:
            insights["pacing"]["evaluation"] = "Pacing parfait"
            insights["performance"]["forces"].append("Régularité")
        elif metrics.pace_fade_pct < 8:
            insights["pacing"]["evaluation"] = "Bon pacing avec légère fatigue finale"
        else:
            insights["pacing"]["evaluation"] = (
                f"Pacing à revoir ({metrics.pace_fade_pct:.0f}% de perte)"
            )
            insights["pacing"]["suggestion"] = "Partez 5-10s/km plus lent"

    if metrics.cadence_cv and metrics.cadence_cv > 0.1:
        insights["technique"]["conseils"].append("Travaillez la régularité de cadence")

    if metrics.vertical_oscillation_avg:
        if metrics.vertical_oscillation_avg > 100:
            insights["technique"]["conseils"].append("Réduisez l'oscillation verticale")
            insights["technique"]["analyse"] = "Foulée avec rebond excessif"
        elif metrics.vertical_oscillation_avg < 60:
            insights["performance"]["forces"].append("Excellente économie de course")

    # Set priority recommendation
    if metrics.anomalies:
        insights["recommendation_prioritaire"] = metrics.anomalies[0]
    elif insights["pacing"]["suggestion"]:
        insights["recommendation_prioritaire"] = insights["pacing"]["suggestion"]
    else:
        insights["recommendation_prioritaire"] = "Maintenez cette qualité de travail"

    return ActivityAnalysis(
        actual_session_id=actual.id or 0,
        analysis_type="detailed",
        insights=insights,
        recommendations=insights["recommendation_prioritaire"],
        generated_by="rules",
    )


def _generate_fallback_interval_analysis(
    actual: ActualSession,
    metrics: DerivedMetrics,
    workout: WorkoutStructure,
) -> ActivityAnalysis:
    """Generate rule-based interval workout analysis."""
    insights = {
        "execution": {"note": "B", "respect_structure": "oui", "regularite": "bonne"},
        "intervalles": {
            "analyse": "",
            "progression": "stable",
            "meilleur_intervalle": 1,
            "pire_intervalle": 1,
        },
        "recuperations": {"analyse": "", "adequates": "oui"},
        "physiologie": {"hr_evolution": "", "recup_cardiaque": "moyenne"},
        "recommendation_prioritaire": "",
        "_metrics": json.loads(metrics.to_compact_json()),
        "_anomalies": metrics.anomalies,
        "_workout_structure": json.loads(workout.to_compact_json()),
        "_is_interval_workout": True,
    }

    # Analyze interval consistency
    if workout.work_pace_consistency_cv is not None:
        cv = workout.work_pace_consistency_cv
        if cv < 2:
            insights["execution"]["regularite"] = "excellente"
            insights["execution"]["note"] = "A"
            insights["intervalles"]["analyse"] = (
                "Allures très régulières entre les intervalles"
            )
        elif cv < 5:
            insights["execution"]["regularite"] = "bonne"
            insights["intervalles"]["analyse"] = (
                "Bonne régularité avec variations mineures"
            )
        else:
            insights["execution"]["regularite"] = "variable"
            insights["execution"]["note"] = "C"
            insights["intervalles"]["analyse"] = (
                f"Variations d'allure importantes (CV={cv:.1f}%)"
            )

    # Analyze HR progression across work intervals
    if workout.work_hr_progression is not None:
        drift = workout.work_hr_progression
        if drift < 3:
            insights["intervalles"]["progression"] = "stable"
            insights["physiologie"]["hr_evolution"] = "FC stable sur les intervalles"
        elif drift < 8:
            insights["intervalles"]["progression"] = "fatigue"
            insights["physiologie"]["hr_evolution"] = (
                f"Légère dérive cardiaque ({drift:.0f}%)"
            )
        else:
            insights["intervalles"]["progression"] = "fatigue"
            insights["physiologie"]["hr_evolution"] = (
                f"Fatigue marquée ({drift:.0f}% de dérive)"
            )
            insights["execution"]["note"] = "C"

    # Find best/worst intervals based on pace
    if workout.work_intervals:
        paces = [
            (i + 1, lap.pace_sec_km)
            for i, lap in enumerate(workout.work_intervals)
            if lap.pace_sec_km
        ]
        if paces:
            best = min(paces, key=lambda x: x[1])
            worst = max(paces, key=lambda x: x[1])
            insights["intervalles"]["meilleur_intervalle"] = best[0]
            insights["intervalles"]["pire_intervalle"] = worst[0]

    # Analyze recoveries
    if workout.rest_intervals:
        avg_rest = workout.avg_rest_duration_sec
        insights["recuperations"]["analyse"] = (
            f"Récupérations moyennes de {avg_rest / 60:.1f}min"
        )

        # Check if rest is too short or too long
        work_duration = workout.avg_work_duration_sec
        if work_duration > 0:
            ratio = avg_rest / work_duration
            if ratio < 0.25:
                insights["recuperations"]["adequates"] = "non"
                insights["recuperations"]["analyse"] += " (trop courtes)"
            elif ratio > 1.0:
                insights["recuperations"]["analyse"] += " (généreuses)"

    # Generate recommendation
    if insights["execution"]["regularite"] == "variable":
        insights["recommendation_prioritaire"] = (
            "Travaillez la régularité d'allure sur les intervalles"
        )
    elif insights["intervalles"]["progression"] == "fatigue":
        insights["recommendation_prioritaire"] = (
            "Partez moins vite sur les premiers intervalles"
        )
    elif insights["recuperations"]["adequates"] == "non":
        insights["recommendation_prioritaire"] = (
            "Allongez les récupérations pour maintenir la qualité"
        )
    else:
        insights["recommendation_prioritaire"] = (
            f"Excellent travail! {workout.num_work_intervals} intervalles bien exécutés"
        )

    return ActivityAnalysis(
        actual_session_id=actual.id or 0,
        analysis_type="interval",
        insights=insights,
        recommendations=insights["recommendation_prioritaire"],
        generated_by="rules",
    )
