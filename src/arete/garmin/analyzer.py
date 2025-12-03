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


def _build_analysis_system_prompt() -> str:
    """Compact system prompt for activity analysis (~200 tokens)."""
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
