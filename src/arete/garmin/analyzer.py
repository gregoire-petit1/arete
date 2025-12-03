"""Activity analysis using LLM.

Compares planned vs actual sessions and provides insights.
Token-optimized for Groq free tier.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime

from arete.garmin.models import ActualSession, PlannedSession
from arete.llm.client import get_client
from arete.llm.token_manager import get_token_manager

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


def _build_analysis_system_prompt(detailed: bool = False) -> str:
    """Compact system prompt for activity analysis (~200 tokens)."""
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
                {"role": "user", "content": _build_analysis_user_prompt(planned, actual)},
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
        "adherence": {"score": 0, "durée": "n/a", "distance": "n/a", "intensité": "n/a"},
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
        insights["recommendation"] = "Continuez à planifier vos séances pour un meilleur suivi"
        
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
                insights["points_amelioration"].append("Intensité plus élevée que prévu")
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
    and provides expert-level analysis.

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

    except Exception as e:
        logger.error(f"Failed to parse FIT file for detailed analysis: {e}")
        return analyze_activity(actual, planned, model)

    # Call LLM with detailed prompt
    client = get_client()
    if client is None:
        return _generate_fallback_detailed_analysis(actual, metrics)

    token_manager = get_token_manager()
    if model is None:
        model = token_manager.get_best_model(estimated_tokens=1200)

    can_proceed, reason = token_manager.can_make_request(model, estimated_tokens=1200)
    if not can_proceed:
        logger.warning(f"Rate limit: {reason}, using fallback")
        return _generate_fallback_detailed_analysis(actual, metrics)

    token_manager.wait_if_needed(model, estimated_tokens=1200)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _build_analysis_system_prompt(detailed=True)},
                {"role": "user", "content": _build_detailed_user_prompt(actual, planned, metrics_json)},
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

            return ActivityAnalysis(
                actual_session_id=actual.id or 0,
                analysis_type="detailed",
                insights=insights,
                recommendations=insights.get("recommendation_prioritaire", ""),
                generated_by="llm",
            )

    except Exception as e:
        logger.error(f"Detailed LLM analysis failed: {e}")

    return _generate_fallback_detailed_analysis(actual, metrics)


def _generate_fallback_detailed_analysis(
    actual: ActualSession,
    metrics: "DerivedMetrics",
) -> ActivityAnalysis:
    """Generate rule-based detailed analysis when LLM unavailable."""
    from arete.garmin.time_series import DerivedMetrics

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
            insights["physiologie"]["hr_analysis"] = f"Dérive cardiaque importante ({metrics.hr_drift_pct:.0f}%)"
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
            insights["pacing"]["evaluation"] = f"Pacing à revoir ({metrics.pace_fade_pct:.0f}% de perte)"
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
