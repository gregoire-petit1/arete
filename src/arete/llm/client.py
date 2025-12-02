"""Groq LLM client for training plan generation.

Uses OpenAI-compatible API with Groq backend.
Models: llama-3.3-70b-versatile (default), llama-4-scout-17b-16e-instruct
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

logger = logging.getLogger(__name__)

# Groq configuration
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "llama-3.3-70b-versatile"  # Best quality/speed for French text generation


@dataclass
class TrainingContext:
    """Context for training plan generation."""

    date: str
    objectif: str
    dispo_min: int
    fatigue: int  # 1-10 scale
    rpe_moy7j: float | None = None

    # From metrics (optional)
    acwr: float | None = None
    acwr_zone: str | None = None
    tsb: float | None = None
    form_zone: str | None = None
    ctl: float | None = None
    monotony: float | None = None
    strain: float | None = None
    recommendations: list[str] | None = None


def get_client() -> OpenAI | None:
    """Get Groq client via OpenAI SDK.

    Returns None if GROQ_API_KEY not set.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.warning("GROQ_API_KEY not set, LLM features disabled")
        return None

    return OpenAI(
        api_key=api_key,
        base_url=GROQ_BASE_URL,
    )


def _build_system_prompt() -> str:
    """Build system prompt for training coach."""
    return """Tu es un coach d'entraînement expert en course à pied et préparation physique.
Tu génères des plans d'entraînement personnalisés basés sur les données physiologiques de l'athlète.

Règles :
- Réponds UNIQUEMENT en JSON valide, sans texte avant/après
- Adapte l'intensité selon le TSB (forme) et l'ACWR (charge)
- Si fatigue élevée (>7) ou TSB < -10, privilégie récupération active
- Si ACWR > 1.3, réduis la charge pour éviter blessure
- Inclus toujours échauffement et retour au calme
- Utilise les zones FC françaises : Z1 (récup), Z2 (endurance), Z3 (tempo), Z4 (seuil), Z5 (VO2max)

Format JSON requis :
{
  "seance": "Description courte de la séance",
  "details": {
    "echauffement": "Description échauffement",
    "corps": "Description du corps de séance",
    "retour_calme": "Description retour au calme"
  },
  "cible": {
    "fc": "Zone FC cible",
    "allure": "Zone d'allure",
    "duree_totale": "Durée en minutes"
  },
  "justification": "Explication courte basée sur les métriques",
  "charge_prevue": "légère | modérée | intense"
}"""


def _build_user_prompt(ctx: TrainingContext) -> str:
    """Build user prompt with training context."""
    lines = [
        f"Date : {ctx.date}",
        f"Objectif : {ctx.objectif}",
        f"Disponibilité : {ctx.dispo_min} minutes",
        f"Fatigue ressentie : {ctx.fatigue}/10",
    ]

    if ctx.rpe_moy7j is not None:
        lines.append(f"RPE moyen 7 jours : {ctx.rpe_moy7j:.1f}")

    # Add metrics if available
    if ctx.acwr is not None:
        lines.append(f"ACWR : {ctx.acwr:.2f} ({ctx.acwr_zone or 'unknown'})")

    if ctx.tsb is not None:
        lines.append(f"TSB (forme) : {ctx.tsb:.1f} ({ctx.form_zone or 'unknown'})")

    if ctx.ctl is not None:
        lines.append(f"CTL (fitness) : {ctx.ctl:.1f}")

    if ctx.monotony is not None:
        lines.append(f"Monotony : {ctx.monotony:.2f}")

    if ctx.strain is not None:
        lines.append(f"Strain : {ctx.strain:.0f}")

    if ctx.recommendations:
        lines.append(f"Recommandations système : {', '.join(ctx.recommendations[:3])}")

    lines.append("\nGénère un plan d'entraînement adapté pour aujourd'hui.")

    return "\n".join(lines)


def generate_plan(
    ctx: TrainingContext,
    model: str = DEFAULT_MODEL,
) -> dict[str, Any]:
    """Generate training plan using Groq LLM.

    Args:
        ctx: Training context with user data and metrics
        model: Groq model to use

    Returns:
        Parsed JSON plan or fallback if LLM unavailable
    """
    import json

    client = get_client()

    if client is None:
        # Fallback when no API key
        return _generate_fallback_plan(ctx)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _build_system_prompt()},
                {"role": "user", "content": _build_user_prompt(ctx)},
            ],
            temperature=0.7,
            max_tokens=1024,
            response_format={"type": "json_object"},
        )

        content = response.choices[0].message.content
        if content:
            result: dict[str, Any] = json.loads(content)
            return result
        return _generate_fallback_plan(ctx)

    except Exception as e:
        logger.error(f"LLM generation failed: {e}")
        return _generate_fallback_plan(ctx)


def _generate_fallback_plan(ctx: TrainingContext) -> dict[str, Any]:
    """Generate rule-based fallback plan when LLM unavailable."""
    # Determine intensity based on fatigue and metrics
    if ctx.fatigue >= 8:
        return {
            "seance": "Récupération active",
            "details": {
                "echauffement": "5' marche",
                "corps": "20-30' footing très léger ou marche",
                "retour_calme": "5' étirements doux",
            },
            "cible": {
                "fc": "Z1 (< 65% FCM)",
                "allure": "Libre, au ressenti",
                "duree_totale": str(min(ctx.dispo_min, 40)),
            },
            "justification": f"Fatigue élevée ({ctx.fatigue}/10), priorité récupération",
            "charge_prevue": "légère",
        }

    if ctx.tsb is not None and ctx.tsb < -15:
        return {
            "seance": "Footing régénération",
            "details": {
                "echauffement": "5' marche progressive",
                "corps": "25-35' footing Z1-Z2",
                "retour_calme": "5' marche + étirements",
            },
            "cible": {
                "fc": "Z1-Z2 (60-70% FCM)",
                "allure": "Aisance respiratoire",
                "duree_totale": str(min(ctx.dispo_min, 45)),
            },
            "justification": f"TSB bas ({ctx.tsb:.0f}), forme dégradée, récupération nécessaire",
            "charge_prevue": "légère",
        }

    if ctx.acwr is not None and ctx.acwr > 1.3:
        return {
            "seance": "Endurance fondamentale légère",
            "details": {
                "echauffement": "10' footing progressif",
                "corps": "30-40' footing Z2 stable",
                "retour_calme": "5' footing lent + étirements",
            },
            "cible": {
                "fc": "Z2 (65-75% FCM)",
                "allure": "Conversation possible",
                "duree_totale": str(min(ctx.dispo_min, 55)),
            },
            "justification": f"ACWR élevé ({ctx.acwr:.2f}), charge à modérer",
            "charge_prevue": "modérée",
        }

    # Default: moderate session
    return {
        "seance": "Endurance fondamentale",
        "details": {
            "echauffement": "10' footing progressif",
            "corps": f"{ctx.dispo_min - 20}' footing Z2 avec quelques accélérations",
            "retour_calme": "10' retour au calme + étirements",
        },
        "cible": {
            "fc": "Z2 (70-75% FCM)",
            "allure": "Allure marathon +30s/km",
            "duree_totale": str(ctx.dispo_min),
        },
        "justification": "Métriques dans la norme, séance standard",
        "charge_prevue": "modérée",
    }
