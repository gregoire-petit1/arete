"""RAG module for knowledge-augmented training recommendations."""

from arete.rag.augmented_generator import (
    AugmentedGenerator,
    enrich_context_with_strength,
)
from arete.rag.knowledge_base import KnowledgeBase
from arete.rag.retriever import Retriever, StrengthBenchmark, UserContext

__all__ = [
    "KnowledgeBase",
    "Retriever",
    "AugmentedGenerator",
    "UserContext",
    "StrengthBenchmark",
    "enrich_context_with_strength",
]
