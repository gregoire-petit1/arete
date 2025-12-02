"""RAG-augmented generator integrating knowledge with LLM.

Combines retrieved knowledge with user context for enriched recommendations.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from arete.rag.knowledge_base import KnowledgeBase, RetrievedDocument
from arete.rag.retriever import Retriever, UserContext

logger = logging.getLogger(__name__)


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
        model: str = "llama-3.3-70b-versatile",
    ) -> dict[str, Any]:
        """Generate training plan augmented with RAG knowledge.

        Args:
            query: User query or training objective
            context: User context with metrics and profile
            model: Groq model to use

        Returns:
            Structured plan with citations
        """
        # Retrieve relevant knowledge
        retrieved_docs = self.retriever.retrieve(query, context, k=5)

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
        """Build system and user prompts with RAG augmentation.

        Returns:
            Tuple of (system_prompt, user_prompt)
        """
        # System prompt with role and constraints
        system_prompt = """Tu es un expert en science du sport et coaching personnalisé.
Tu génères des plans d'entraînement basés sur des preuves scientifiques.

## RÈGLES ABSOLUES
1. Réponds UNIQUEMENT en JSON valide
2. Cite les sources avec [Source: ID] quand tu utilises une connaissance
3. Adapte l'intensité selon les métriques (ACWR, TSB)
4. Si risque élevé (ACWR > 1.3 ou TSB < -15), PRIORISE la sécurité
5. Quantifie tes recommandations (%, durées, zones)
6. NE JAMAIS inventer de données ou sources

## FORMAT JSON REQUIS
{
  "seance": "Description courte",
  "details": {
    "echauffement": "...",
    "corps": "...",
    "retour_calme": "..."
  },
  "cible": {
    "fc": "Zone FC",
    "allure": "Zone allure",
    "duree_totale": "minutes"
  },
  "justification": "Explication basée sur métriques et science",
  "charge_prevue": "légère | modérée | intense",
  "sources_utilisees": ["ID1", "ID2"],
  "avertissements": ["si applicable"]
}"""

        # Build user prompt with context and knowledge
        user_parts = []

        # User context
        user_parts.append("## CONTEXTE UTILISATEUR")
        user_parts.append(f"- Sport : {context.primary_sport}")
        user_parts.append(f"- Niveau : {context.experience}")
        user_parts.append(f"- Fatigue ressentie : {context.fatigue}/10")

        # Current metrics
        user_parts.append("\n## MÉTRIQUES ACTUELLES")
        if context.acwr is not None:
            zone = context.acwr_zone or "unknown"
            user_parts.append(f"- ACWR : {context.acwr:.2f} ({zone})")
        if context.tsb is not None:
            zone = context.form_zone or "unknown"
            user_parts.append(f"- TSB (forme) : {context.tsb:.1f} ({zone})")
        if context.ctl is not None:
            user_parts.append(f"- CTL (fitness) : {context.ctl:.1f}")
        if context.monotony is not None:
            user_parts.append(f"- Monotonie : {context.monotony:.2f}")
        if context.strain is not None:
            user_parts.append(f"- Strain : {context.strain:.0f}")

        # Risk assessment
        risk = context.get_risk_level()
        intent = context.infer_intent()
        user_parts.append("\n## ÉVALUATION")
        user_parts.append(f"- Niveau de risque : {risk:.0%}")
        user_parts.append(f"- Intention détectée : {intent}")

        # Retrieved knowledge
        if docs:
            user_parts.append("\n## CONNAISSANCES SCIENTIFIQUES PERTINENTES")
            for doc in docs:
                user_parts.append(f"\n### [Source: {doc.id}]")
                user_parts.append(f"Collection: {doc.collection}")
                if doc.metadata.get("title"):
                    user_parts.append(f"Titre: {doc.metadata['title']}")
                user_parts.append(f"Contenu: {doc.content[:500]}...")
                if doc.metadata.get("key_findings"):
                    findings = doc.metadata["key_findings"]
                    if isinstance(findings, list):
                        user_parts.append("Conclusions clés:")
                        for f in findings[:3]:
                            user_parts.append(f"  - {f}")

        # Query
        user_parts.append(f"\n## DEMANDE\n{query}")
        user_parts.append("\nGénère un plan d'entraînement adapté en JSON.")

        user_prompt = "\n".join(user_parts)

        return system_prompt, user_prompt

    def _call_llm(
        self,
        prompt: tuple[str, str],
        model: str,
    ) -> dict[str, Any]:
        """Call Groq LLM for generation."""
        import os

        from openai import OpenAI

        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            logger.warning("GROQ_API_KEY not set, using fallback")
            return self._fallback_response()

        client = OpenAI(
            api_key=api_key,
            base_url="https://api.groq.com/openai/v1",
        )

        system_prompt, user_prompt = prompt

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=1500,
                response_format={"type": "json_object"},
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

        return response


def create_augmented_generator() -> AugmentedGenerator:
    """Factory function to create configured generator."""
    kb = KnowledgeBase()
    retriever = Retriever(kb)
    return AugmentedGenerator(knowledge_base=kb, retriever=retriever)
