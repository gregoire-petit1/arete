"""Contextual retriever with multi-stage ranking.

Implements intelligent retrieval based on user context and metrics.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from arete.rag.knowledge_base import KnowledgeBase, RetrievedDocument

logger = logging.getLogger(__name__)


@dataclass
class StrengthBenchmark:
    """Strength training benchmark for a single exercise."""

    exercise: str
    category: str
    muscle: str
    estimated_1rm: float
    weight_kg: float
    reps: int


@dataclass
class CardioBenchmark:
    """Cardio/running benchmarks for endurance sessions."""

    avg_cadence_spm: int | None = None
    avg_vertical_oscillation_mm: float | None = None
    avg_ground_contact_time_ms: int | None = None
    avg_stride_length_m: float | None = None
    avg_easy_hr: int | None = None
    avg_easy_pace: str | None = None  # "5:30" format
    best_pace: str | None = None
    total_distance_km_90d: float = 0.0
    session_count_90d: int = 0


@dataclass
class UserContext:
    """User context for retrieval personalization."""

    # Current metrics
    acwr: float | None = None
    acwr_zone: str | None = None
    monotony: float | None = None
    strain: float | None = None
    tsb: float | None = None
    form_zone: str | None = None
    ctl: float | None = None

    # User profile
    experience: str = "intermediate"  # beginner, intermediate, advanced
    primary_sport: str = "running"
    fatigue: int = 5  # 1-10

    # Inferred intent
    intent: str | None = None

    # Strength benchmarks
    strength_benchmarks: list[StrengthBenchmark] = field(default_factory=list)
    strength_session_count_30d: int = 0
    strength_total_volume_30d: float = 0.0
    strength_volume_by_muscle: dict[str, float] = field(default_factory=dict)

    # Cardio benchmarks
    cardio_benchmark: CardioBenchmark | None = None
    hr_drift_flags: list[str] = field(default_factory=list)  # Recent fatigue warnings

    def infer_intent(self) -> str:
        """Infer user intent from metrics."""
        if self.acwr is not None and self.acwr > 1.5:
            return "risk_mitigation"
        if self.monotony is not None and self.monotony > 2.0:
            return "variety_seeking"
        if self.tsb is not None and self.tsb < -20:
            return "recovery_needed"
        if self.tsb is not None and self.tsb > 15:
            return "ready_for_intensity"
        return "general_guidance"

    def get_risk_level(self) -> float:
        """Calculate overall risk level (0-1)."""
        risk = 0.0

        if self.acwr is not None:
            if self.acwr > 1.5:
                risk = max(risk, 0.9)
            elif self.acwr > 1.3:
                risk = max(risk, 0.6)

        if self.monotony is not None and self.monotony > 2.0:
            risk = max(risk, 0.5)

        if self.tsb is not None and self.tsb < -20:
            risk = max(risk, 0.7)

        if self.fatigue >= 8:
            risk = max(risk, 0.6)

        return risk

    def get_strength_summary(self) -> str:
        """Get compact strength summary for prompts."""
        if not self.strength_benchmarks:
            return ""

        parts = []

        # Top lifts by category (max 4 for token efficiency)
        seen_cats: set[str] = set()
        for bench in self.strength_benchmarks:
            if bench.category not in seen_cats and len(seen_cats) < 4:
                parts.append(f"{bench.exercise}:{bench.estimated_1rm:.0f}kg")
                seen_cats.add(bench.category)

        # Volume trend
        if self.strength_session_count_30d > 0:
            parts.append(
                f"Vol30d:{self.strength_total_volume_30d:.0f}kg({self.strength_session_count_30d}sess)"
            )

        return " ".join(parts)

    def get_cardio_summary(self) -> str:
        """Get compact cardio summary for prompts."""
        if not self.cardio_benchmark:
            return ""

        cb = self.cardio_benchmark
        parts = []

        # Key running dynamics
        if cb.avg_cadence_spm:
            parts.append(f"Cadence:{cb.avg_cadence_spm}spm")
        if cb.avg_vertical_oscillation_mm:
            parts.append(f"VO:{cb.avg_vertical_oscillation_mm}mm")
        if cb.avg_easy_pace:
            parts.append(f"EasyPace:{cb.avg_easy_pace}")
        if cb.avg_easy_hr:
            parts.append(f"EasyHR:{cb.avg_easy_hr}bpm")

        # Volume
        if cb.total_distance_km_90d > 0:
            parts.append(f"Km90d:{cb.total_distance_km_90d:.0f}")

        # Fatigue flags
        if self.hr_drift_flags:
            parts.append(f"⚠️Drift:{len(self.hr_drift_flags)}")

        return " ".join(parts)


class Retriever:
    """Contextual retriever with smart ranking.

    Retrieves documents from knowledge base and re-ranks based on:
    - User context (metrics, profile)
    - Risk level
    - Intent
    """

    def __init__(self, knowledge_base: KnowledgeBase):
        """Initialize retriever with knowledge base."""
        self.kb = knowledge_base

    def retrieve(
        self,
        query: str,
        context: UserContext | None = None,
        k: int = 5,
    ) -> list[RetrievedDocument]:
        """Retrieve and rank documents based on query and context.

        Args:
            query: User query or situation description
            context: User context for personalization
            k: Number of documents to return

        Returns:
            Ranked list of relevant documents
        """
        # Enrich query with context
        enriched_query = self._enrich_query(query, context)

        # Get more candidates for re-ranking
        candidates = self.kb.query_all(
            query_text=enriched_query,
            n_results_per_collection=k * 2,
        )

        if not candidates:
            return []

        # Re-rank with context
        if context:
            candidates = self._contextual_rerank(candidates, context)

        # Diversify results
        diverse_results = self._diversify(candidates, k)

        return diverse_results

    def _enrich_query(self, query: str, context: UserContext | None) -> str:
        """Enrich query with contextual information."""
        if not context:
            return query

        parts = [query]

        # Add metrics context
        if context.acwr is not None:
            zone = context.acwr_zone or "unknown"
            parts.append(f"ACWR: {context.acwr:.2f} ({zone})")

        if context.tsb is not None:
            zone = context.form_zone or "unknown"
            parts.append(f"TSB: {context.tsb:.1f} ({zone})")

        if context.monotony is not None:
            parts.append(f"Monotonie: {context.monotony:.2f}")

        # Add intent
        intent = context.intent or context.infer_intent()
        if intent == "risk_mitigation":
            parts.append("Risque blessure élevé, besoin prévention")
        elif intent == "recovery_needed":
            parts.append("Fatigue accumulée, récupération nécessaire")
        elif intent == "variety_seeking":
            parts.append("Monotonie élevée, besoin variation")

        # Add sport context
        parts.append(f"Sport: {context.primary_sport}")

        return " | ".join(parts)

    def _contextual_rerank(
        self,
        documents: list[RetrievedDocument],
        context: UserContext,
    ) -> list[RetrievedDocument]:
        """Re-rank documents based on context relevance."""
        risk_level = context.get_risk_level()
        intent = context.intent or context.infer_intent()

        for doc in documents:
            base_score = doc.relevance_score
            boost = 0.0

            # Boost scientific docs if high risk
            if doc.collection == "scientific" and risk_level > 0.6:
                boost += 0.2

            # Boost protocols if seeking progression
            if doc.collection == "protocols" and intent == "ready_for_intensity":
                boost += 0.15

            # Boost exercises if seeking variety
            if doc.collection == "exercises" and intent == "variety_seeking":
                boost += 0.15

            # Boost based on evidence level in metadata
            evidence = doc.metadata.get("evidence_level", "medium")
            if evidence == "high":
                boost += 0.1
            elif evidence == "low":
                boost -= 0.1

            # Boost based on sport match
            doc_sports = doc.metadata.get("sports", [])
            if context.primary_sport in doc_sports or "all" in doc_sports:
                boost += 0.1

            # Boost based on experience match
            doc_levels = doc.metadata.get("levels", [])
            if context.experience in doc_levels or "all" in doc_levels:
                boost += 0.05

            # Apply boost (capped at 1.0)
            doc.relevance_score = min(1.0, base_score + boost)

        # Re-sort
        documents.sort(key=lambda x: x.relevance_score, reverse=True)

        return documents

    def _diversify(
        self,
        documents: list[RetrievedDocument],
        k: int,
    ) -> list[RetrievedDocument]:
        """Ensure diversity in results (different collections, topics)."""
        diverse: list[RetrievedDocument] = []
        collection_counts: dict[str, int] = {}
        max_per_collection = max(2, k // 2)

        for doc in documents:
            # Limit per collection
            count = collection_counts.get(doc.collection, 0)
            if count >= max_per_collection:
                continue

            # Check similarity with already selected
            if not self._is_too_similar(doc, diverse):
                diverse.append(doc)
                collection_counts[doc.collection] = count + 1

            if len(diverse) >= k:
                break

        return diverse

    def _is_too_similar(
        self,
        doc: RetrievedDocument,
        selected: list[RetrievedDocument],
        threshold: float = 0.9,
    ) -> bool:
        """Check if document is too similar to already selected ones."""
        if not selected:
            return False

        # Simple check based on content overlap
        doc_words = set(doc.content.lower().split())
        for other in selected:
            other_words = set(other.content.lower().split())
            if not doc_words or not other_words:
                continue
            overlap = len(doc_words & other_words) / min(
                len(doc_words), len(other_words)
            )
            if overlap > threshold:
                return True

        return False

    def get_context_summary(self, context: UserContext) -> dict[str, Any]:
        """Generate a summary of the user context for prompts."""
        return {
            "intent": context.intent or context.infer_intent(),
            "risk_level": context.get_risk_level(),
            "metrics": {
                "acwr": context.acwr,
                "acwr_zone": context.acwr_zone,
                "tsb": context.tsb,
                "form_zone": context.form_zone,
                "monotony": context.monotony,
                "strain": context.strain,
                "ctl": context.ctl,
            },
            "profile": {
                "experience": context.experience,
                "sport": context.primary_sport,
                "fatigue": context.fatigue,
            },
        }
