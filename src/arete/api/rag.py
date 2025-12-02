"""RAG API endpoints.

Provides knowledge-augmented training recommendations.
"""

from __future__ import annotations

import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from arete.rag.augmented_generator import AugmentedGenerator
from arete.rag.knowledge_base import KnowledgeBase
from arete.rag.retriever import Retriever, UserContext
from arete.rag.seed_knowledge import seed_knowledge_base

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rag", tags=["rag"])

# Lazy-loaded components
_kb: KnowledgeBase | None = None
_retriever: Retriever | None = None
_generator: AugmentedGenerator | None = None


def get_kb() -> KnowledgeBase:
    """Get or create knowledge base singleton."""
    global _kb
    if _kb is None:
        _kb = KnowledgeBase()
    return _kb


def get_retriever() -> Retriever:
    """Get or create retriever singleton."""
    global _retriever
    if _retriever is None:
        _retriever = Retriever(get_kb())
    return _retriever


def get_generator() -> AugmentedGenerator:
    """Get or create generator singleton."""
    global _generator
    if _generator is None:
        _generator = AugmentedGenerator(get_kb(), get_retriever())
    return _generator


# ---------- Schemas ----------


class RAGQueryRequest(BaseModel):
    """Request for RAG-augmented query."""

    query: str = Field(description="Question or training request")

    # User context (optional but recommended)
    acwr: float | None = Field(None, description="Current ACWR")
    acwr_zone: str | None = Field(None, description="ACWR zone")
    tsb: float | None = Field(None, description="Current TSB (form)")
    form_zone: str | None = Field(None, description="Form zone")
    ctl: float | None = Field(None, description="CTL (fitness)")
    monotony: float | None = Field(None, description="Training monotony")
    strain: float | None = Field(None, description="Training strain")

    # Profile
    experience: Literal["beginner", "intermediate", "advanced"] = Field(
        "intermediate", description="Experience level"
    )
    primary_sport: str = Field("running", description="Primary sport")
    fatigue: int = Field(5, ge=1, le=10, description="Perceived fatigue 1-10")


class SearchResult(BaseModel):
    """A single search result."""

    id: str
    content: str
    collection: str
    relevance_score: float
    metadata: dict


class SearchResponse(BaseModel):
    """Response for knowledge search."""

    results: list[SearchResult]
    query: str
    total_results: int


class KBStatsResponse(BaseModel):
    """Knowledge base statistics."""

    collections: dict[str, int]
    total_documents: int


# ---------- Endpoints ----------


@router.post("/query")
def rag_query(request: RAGQueryRequest):
    """Query with RAG-augmented response generation.

    Retrieves relevant knowledge and generates personalized recommendations
    using the LLM with full context.
    """
    # Build user context
    context = UserContext(
        acwr=request.acwr,
        acwr_zone=request.acwr_zone,
        tsb=request.tsb,
        form_zone=request.form_zone,
        ctl=request.ctl,
        monotony=request.monotony,
        strain=request.strain,
        experience=request.experience,
        primary_sport=request.primary_sport,
        fatigue=request.fatigue,
    )

    # Generate augmented response
    generator = get_generator()
    response = generator.generate_augmented_plan(
        query=request.query,
        context=context,
    )

    return response


@router.get("/search", response_model=SearchResponse)
def search_knowledge(
    q: str = Query(..., description="Search query"),
    collection: str | None = Query(None, description="Specific collection to search"),
    k: int = Query(5, ge=1, le=20, description="Number of results"),
):
    """Search the knowledge base for relevant documents.

    Useful for exploring available knowledge without LLM generation.
    """
    kb = get_kb()

    if collection and collection not in kb.COLLECTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown collection: {collection}. Valid: {kb.COLLECTIONS}",
        )

    if collection:
        results = kb.query(collection, q, n_results=k)
    else:
        results = kb.query_all(q, n_results_per_collection=k)

    return SearchResponse(
        results=[
            SearchResult(
                id=r.id,
                content=r.content[:500] + "..." if len(r.content) > 500 else r.content,
                collection=r.collection,
                relevance_score=round(r.relevance_score, 4),
                metadata=r.metadata,
            )
            for r in results
        ],
        query=q,
        total_results=len(results),
    )


@router.get("/stats", response_model=KBStatsResponse)
def get_stats():
    """Get knowledge base statistics."""
    kb = get_kb()
    stats = kb.get_collection_stats()
    return KBStatsResponse(
        collections=stats,
        total_documents=sum(stats.values()),
    )


@router.post("/seed")
def seed_database():
    """Seed the knowledge base with initial documents.

    This populates the KB with scientific literature, protocols, and exercises.
    Safe to call multiple times (uses upsert).
    """
    kb = get_kb()
    stats = seed_knowledge_base(kb)
    return {
        "status": "success",
        "documents_added": stats,
        "total": sum(stats.values()),
    }


@router.delete("/clear/{collection}")
def clear_collection(collection: str):
    """Clear all documents from a specific collection."""
    kb = get_kb()
    if collection not in kb.COLLECTIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown collection: {collection}. Valid: {kb.COLLECTIONS}",
        )
    kb.clear_collection(collection)
    return {"status": "success", "collection_cleared": collection}
