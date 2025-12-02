"""Groq LLM client for training plan generation.

Uses OpenAI-compatible API with Groq backend.
Models: llama-3.3-70b-versatile (default), llama-4-scout-17b-16e-instruct

Token usage is tracked and rate limits are enforced to stay within Groq free tier.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from arete.llm.token_manager import get_token_manager

logger = logging.getLogger(__name__)

# Groq configuration
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "llama-3.3-70b-versatile"  # Best quality/speed for French text generation

# Token budget per request (prompt + completion)
MAX_PROMPT_TOKENS = 800  # Reduced from ~1500
MAX_COMPLETION_TOKENS = 800  # Reduced from 1024


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
    """Build compact system prompt for training coach.

    Optimized for token efficiency (~300 tokens vs 500 before).
    """
    return """Coach expert course à pied. Génère plans personnalisés en JSON.

RÈGLES:
- JSON valide uniquement, sans texte
- Intensité selon TSB (forme) et ACWR (charge)
- Si fatigue>7 ou TSB<-10: récupération
- Si ACWR>1.3: réduire charge
- Zones FC: Z1 récup, Z2 endurance, Z3 tempo, Z4 seuil, Z5 VO2max

FORMAT JSON:
{"seance":"...", "details":{"echauffement":"...", "corps":"...", "retour_calme":"..."}, "cible":{"fc":"Zone", "allure":"...", "duree_totale":"min"}, "justification":"...", "charge_prevue":"légère|modérée|intense"}"""


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
        lines.append(f"Reco: {', '.join(ctx.recommendations[:2])}")

    lines.append("\nPlan pour aujourd'hui:")

    return "\n".join(lines)


def generate_plan(
    ctx: TrainingContext,
    model: str | None = None,
) -> dict[str, Any]:
    """Generate training plan using Groq LLM.

    Args:
        ctx: Training context with user data and metrics
        model: Groq model to use (auto-selected if None)

    Returns:
        Parsed JSON plan or fallback if LLM unavailable
    """
    import json

    client = get_client()

    if client is None:
        # Fallback when no API key
        return _generate_fallback_plan(ctx)

    # Token management
    token_manager = get_token_manager()

    # Auto-select best available model
    if model is None:
        model = token_manager.get_best_model(estimated_tokens=1500)

    # Check if we can make request
    can_proceed, reason = token_manager.can_make_request(model, estimated_tokens=1500)
    if not can_proceed:
        logger.warning(f"Rate limit: {reason}, using fallback")
        return _generate_fallback_plan(ctx)

    # Wait if needed (per-minute limit)
    token_manager.wait_if_needed(model, estimated_tokens=1500)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": _build_system_prompt()},
                {"role": "user", "content": _build_user_prompt(ctx)},
            ],
            temperature=0.7,
            max_tokens=MAX_COMPLETION_TOKENS,
            response_format={"type": "json_object"},
        )

        # Track token usage
        if response.usage:
            token_manager.record_usage(
                model=model,
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
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
