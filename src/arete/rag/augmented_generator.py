"""RAG-augmented generator integrating knowledge with LLM.

Combines retrieved knowledge with user context for enriched recommendations.
Token-optimized for Groq free tier limits.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from arete.llm.token_manager import get_token_manager
from arete.rag.knowledge_base import KnowledgeBase, RetrievedDocument
from arete.rag.retriever import Retriever, UserContext

logger = logging.getLogger(__name__)

# Token budget optimization
MAX_DOCS_FOR_CONTEXT = 3  # Reduced from 5
MAX_CONTENT_CHARS = 200  # Reduced from 500
MAX_COMPLETION_TOKENS = 800  # Reduced from 1500


class AugmentedGenerator:
    """RAG-augmented response generator.

    Integrates:
    - Knowledge base retrieval
    - User context analysis
    - LLM generation with Groq
    """

    def __init__(
        self,
        knowledge_base: KnowledgeBase | None = None,
        retriever: Retriever | None = None,
    ):
        """Initialize generator.

        Args:
            knowledge_base: Optional pre-initialized knowledge base
            retriever: Optional pre-initialized retriever
        """
        self.kb = knowledge_base or KnowledgeBase()
        self.retriever = retriever or Retriever(self.kb)

    def generate_augmented_plan(
        self,
        query: str,
        context: UserContext,
        model: str | None = None,
    ) -> dict[str, Any]:
        """Generate training plan augmented with RAG knowledge.

        Args:
            query: User query or training objective
            context: User context with metrics and profile
            model: Groq model to use (auto-selected if None)

        Returns:
            Structured plan with citations
        """
        # Token management
        token_manager = get_token_manager()

        # Auto-select best available model
        if model is None:
            model = token_manager.get_best_model(estimated_tokens=2000)

        # Check if we can make request
        can_proceed, reason = token_manager.can_make_request(
            model, estimated_tokens=2000
        )
        if not can_proceed:
            logger.warning(f"Rate limit: {reason}, using fallback")
            return self._fallback_response()

        # Retrieve relevant knowledge (reduced count for token efficiency)
        retrieved_docs = self.retriever.retrieve(query, context, k=MAX_DOCS_FOR_CONTEXT)

        # Build augmented prompt
        prompt = self._build_augmented_prompt(query, context, retrieved_docs)

        # Generate with LLM
        response = self._call_llm(prompt, model)

        # Structure response with metadata
        result = self._structure_response(response, retrieved_docs, context)

        return result

    def _build_augmented_prompt(
        self,
        query: str,
        context: UserContext,
        docs: list[RetrievedDocument],
    ) -> tuple[str, str]:
        """Build compact system and user prompts with RAG augmentation.

        Token-optimized: ~600 tokens total vs ~2000 before.

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        # Compact system prompt (~250 tokens)
        system_prompt = """Expert science du sport. Plans basés sur preuves.

RÈGLES:
- JSON valide uniquement
- Cite sources avec [Source: ID]
- Si ACWR>1.3 ou TSB<-15: SÉCURITÉ prioritaire
- Quantifie (%, durées, zones)
- Utilise les benchmarks de force si disponibles

FORMAT JSON:
{"seance":"...", "details":{"echauffement":"...", "corps":"...", "retour_calme":"..."}, "cible":{"fc":"Zone", "allure":"...", "duree_totale":"min"}, "justification":"...", "charge_prevue":"légère|modérée|intense", "sources_utilisees":["ID"], "avertissements":[]}"""

        # Compact user prompt
        user_parts = []

        # Essential context only
        user_parts.append(
            f"Sport:{context.primary_sport} Niveau:{context.experience} Fatigue:{context.fatigue}/10"
        )

        # Key metrics on one line
        metrics = []
        if context.acwr is not None:
            metrics.append(f"ACWR:{context.acwr:.2f}")
        if context.tsb is not None:
            metrics.append(f"TSB:{context.tsb:.0f}")
        if context.ctl is not None:
            metrics.append(f"CTL:{context.ctl:.0f}")
        if metrics:
            user_parts.append(" ".join(metrics))

        # Risk/intent summary
        user_parts.append(
            f"Risque:{context.get_risk_level():.0%} Intent:{context.infer_intent()}"
        )

        # Strength benchmarks (compact)
        strength_summary = context.get_strength_summary()
        if strength_summary:
            user_parts.append(f"Force: {strength_summary}")

        # Cardio benchmarks (compact)
        cardio_summary = context.get_cardio_summary()
        if cardio_summary:
            user_parts.append(f"Cardio: {cardio_summary}")

        # Compact knowledge (limited chars per doc)
        if docs:
            user_parts.append("\nSources:")
            for doc in docs[:MAX_DOCS_FOR_CONTEXT]:
                title = doc.metadata.get("title", doc.id)[:50]
                content = doc.content[:MAX_CONTENT_CHARS].replace("\n", " ")
                user_parts.append(f"[{doc.id}] {title}: {content}...")

        # Query
        user_parts.append(f"\nDemande: {query[:200]}")

        user_prompt = "\n".join(user_parts)

        return system_prompt, user_prompt

    def _call_llm(
        self,
        prompt: tuple[str, str],
        model: str,
    ) -> dict[str, Any]:
        """Call Groq LLM for generation with token tracking."""
        import os

        from openai import OpenAI

        from arete.llm.token_manager import get_token_manager

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            logger.warning("GROQ_API_KEY not set, using fallback")
            return self._fallback_response()

        client = OpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
        )

        system_prompt, user_prompt = prompt
        token_manager = get_token_manager()

        # Wait if per-minute limit reached
        token_manager.wait_if_needed(model, estimated_tokens=2000)

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
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
                return json.loads(content)
            return self._fallback_response()

        except Exception as e:
            logger.error(f"LLM call failed: {e}")
            return self._fallback_response()

    def _fallback_response(self) -> dict[str, Any]:
        """Fallback when LLM unavailable."""
        return {
            "seance": "Endurance fondamentale",
            "details": {
                "echauffement": "10' footing progressif",
                "corps": "30-40' footing Z2",
                "retour_calme": "10' retour au calme + étirements",
            },
            "cible": {
                "fc": "Z2 (65-75% FCM)",
                "allure": "Conversation possible",
                "duree_totale": "50-60",
            },
            "justification": "Plan générique (LLM non disponible)",
            "charge_prevue": "modérée",
            "sources_utilisees": [],
            "avertissements": ["Recommandation générique sans personnalisation"],
        }

    def _structure_response(
        self,
        response: dict[str, Any],
        docs: list[RetrievedDocument],
        context: UserContext,
    ) -> dict[str, Any]:
        """Add metadata and structure to response."""
        # Add retrieval metadata
        response["_metadata"] = {
            "sources_retrieved": [
                {
                    "id": doc.id,
                    "collection": doc.collection,
                    "relevance": round(doc.relevance_score, 3),
                }
                for doc in docs
            ],
            "context_summary": self.retriever.get_context_summary(context),
            "rag_enabled": True,
        }

        # Add strength context if available
        if context.strength_benchmarks:
            response["_metadata"]["strength_benchmarks_count"] = len(
                context.strength_benchmarks
            )

        return response


def create_augmented_generator() -> AugmentedGenerator:
    """Factory function to create configured generator."""
    kb = KnowledgeBase()
    retriever = Retriever(kb)
    return AugmentedGenerator(knowledge_base=kb, retriever=retriever)


def enrich_context_with_strength(
    context: UserContext,
    db_path: str = "data/arete.duckdb",
) -> UserContext:
    """Enrich UserContext with strength training benchmarks.

    Fetches personal records and recent volume from strength module.

    Args:
        context: Existing user context
        db_path: Path to DuckDB database

    Returns:
        Enriched UserContext with strength data
    """
    from arete.rag.retriever import StrengthBenchmark
    from arete.strength.repository import StrengthRepository

    try:
        repo = StrengthRepository(db_path)

        # Get all PRs
        prs = repo.get_all_prs_summary()
        context.strength_benchmarks = [
            StrengthBenchmark(
                exercise=pr["exercise"],
                category=pr["category"],
                muscle=pr["muscle"],
                estimated_1rm=pr["estimated_1rm"],
                weight_kg=pr["weight_kg"],
                reps=pr["reps"],
            )
            for pr in prs
        ]

        # Get 30-day trends
        trends = repo.get_strength_trends(days=30)
        context.strength_session_count_30d = trends["session_count"]
        context.strength_total_volume_30d = trends["total_volume_kg"]
        context.strength_volume_by_muscle = trends["volume_by_muscle"]

    except Exception as e:
        logger.warning(f"Failed to load strength benchmarks: {e}")

    return context


def enrich_context_with_cardio(
    context: UserContext,
    db_path: str = "data/arete.duckdb",  # Kept for API consistency; GarminRepository uses ARETE_DB env
) -> UserContext:
    """Enrich UserContext with cardio/running benchmarks.

    Fetches cadence, vertical oscillation, pace benchmarks from Garmin data.

    Note:
        GarminRepository uses the ARETE_DB environment variable for the database path.
        The db_path parameter is maintained for API consistency with enrich_context_with_strength.

    Args:
        context: Existing user context
        db_path: Path to DuckDB database (unused; for API consistency)

    Returns:
        Enriched UserContext with cardio data
    """
    from arete.garmin.repository import GarminRepository
    from arete.rag.retriever import CardioBenchmark

    try:
        repo = GarminRepository()

        # Get cardio benchmarks (90-day averages)
        benchmarks = repo.get_cardio_benchmarks(days=90)
        context.cardio_benchmark = CardioBenchmark(
            avg_cadence_spm=benchmarks.get("avg_cadence_spm"),
            avg_vertical_oscillation_mm=benchmarks.get("avg_vertical_oscillation_mm"),
            avg_ground_contact_time_ms=benchmarks.get("avg_ground_contact_time_ms"),
            avg_stride_length_m=benchmarks.get("avg_stride_length_m"),
            avg_easy_hr=benchmarks.get("avg_easy_hr"),
            avg_easy_pace=benchmarks.get("avg_easy_pace"),
            best_pace=benchmarks.get("best_pace"),
            total_distance_km_90d=benchmarks.get("total_distance_km", 0),
            session_count_90d=benchmarks.get("session_count", 0),
        )

        # Get HR drift flags for fatigue detection
        drift_data = repo.get_hr_drift_analysis(days=14)
        context.hr_drift_flags = [
            f"{d['date']}: {d['flag']}"
            for d in drift_data
            if d.get("flag") == "potential_fatigue"
        ]

    except Exception as e:
        logger.warning(f"Failed to load cardio benchmarks: {e}")

    return context


def enrich_context_full(
    context: UserContext,
    db_path: str = "data/arete.duckdb",
) -> UserContext:
    """Enrich UserContext with all available benchmarks.

    Combines strength and cardio data for comprehensive RAG context.

    Args:
        context: Existing user context
        db_path: Path to DuckDB database

    Returns:
        Fully enriched UserContext
    """
    context = enrich_context_with_strength(context, db_path)
    context = enrich_context_with_cardio(context, db_path)
    return context
