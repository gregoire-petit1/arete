"""Knowledge base with ChromaDB vector store.

Manages collections for scientific literature, training protocols, and exercises.
Uses ChromaDB's default embedding function for simplicity.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import chromadb
from chromadb.config import Settings

logger = logging.getLogger(__name__)

# Default path for ChromaDB persistence
DEFAULT_PERSIST_DIR = Path("data/chromadb")


@dataclass
class Document:
    """A document in the knowledge base."""

    id: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding: list[float] | None = None


@dataclass
class RetrievedDocument:
    """A retrieved document with relevance score."""

    id: str
    content: str
    metadata: dict[str, Any]
    relevance_score: float
    collection: str


class KnowledgeBase:
    """ChromaDB-based knowledge base for training knowledge.

    Collections:
    - scientific: Research papers, studies on ACWR, periodization, etc.
    - protocols: Training protocols, periodization schemes
    - exercises: Exercise database with variations and considerations
    """

    COLLECTIONS = ["scientific", "protocols", "exercises"]

    def __init__(
        self,
        persist_directory: str | Path | None = None,
    ):
        """Initialize knowledge base.

        Args:
            persist_directory: Path for ChromaDB persistence. Defaults to data/chromadb.
        """
        self.persist_dir = Path(persist_directory or DEFAULT_PERSIST_DIR)
        self.persist_dir.mkdir(parents=True, exist_ok=True)

        # Initialize ChromaDB with persistence
        self.client = chromadb.PersistentClient(
            path=str(self.persist_dir),
            settings=Settings(anonymized_telemetry=False),
        )

        # Initialize collections (ChromaDB handles embeddings automatically)
        self._collections: dict[str, chromadb.Collection] = {}
        for name in self.COLLECTIONS:
            self._collections[name] = self.client.get_or_create_collection(
                name=name,
                metadata={"description": f"Arete {name} knowledge base"},
            )

        logger.info(
            f"KnowledgeBase initialized at {self.persist_dir} "
            f"with {len(self.COLLECTIONS)} collections"
        )

    def _sanitize_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        """Sanitize metadata for ChromaDB (convert lists to JSON strings)."""
        sanitized = {}
        for key, value in metadata.items():
            if isinstance(value, list):
                sanitized[key] = json.dumps(value)
            elif value is None:
                sanitized[key] = ""
            else:
                sanitized[key] = value
        return sanitized

    def add_documents(
        self,
        collection: str,
        documents: list[Document],
    ) -> int:
        """Add documents to a collection.

        Args:
            collection: Collection name (scientific, protocols, exercises)
            documents: List of documents to add

        Returns:
            Number of documents added
        """
        if collection not in self.COLLECTIONS:
            raise ValueError(f"Unknown collection: {collection}")

        coll = self._collections[collection]

        # Prepare data
        ids = [doc.id for doc in documents]
        contents = [doc.content for doc in documents]
        metadatas = [self._sanitize_metadata(doc.metadata) for doc in documents]

        # Upsert to ChromaDB (ChromaDB generates embeddings automatically)
        # Cast metadatas to expected type for chromadb
        coll.upsert(
            ids=ids,
            documents=contents,
            metadatas=metadatas,  # type: ignore[arg-type]
        )

        logger.info(f"Added {len(documents)} documents to {collection}")
        return len(documents)

    def query(
        self,
        collection: str,
        query_text: str,
        n_results: int = 5,
        where: dict[str, Any] | None = None,
    ) -> list[RetrievedDocument]:
        """Query a collection for relevant documents.

        Args:
            collection: Collection to search
            query_text: Query text
            n_results: Number of results to return
            where: Optional metadata filter

        Returns:
            List of retrieved documents with scores
        """
        if collection not in self.COLLECTIONS:
            raise ValueError(f"Unknown collection: {collection}")

        coll = self._collections[collection]

        # Query ChromaDB (it handles embeddings automatically)
        results = coll.query(
            query_texts=[query_text],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )

        # Convert to RetrievedDocument objects
        retrieved = []
        if results["ids"] and results["ids"][0]:
            for i, doc_id in enumerate(results["ids"][0]):
                # ChromaDB returns L2 distance, convert to similarity
                distance = results["distances"][0][i] if results["distances"] else 0
                similarity = 1 / (1 + distance)  # Convert distance to similarity

                meta = results["metadatas"][0][i] if results["metadatas"] else {}
                retrieved.append(
                    RetrievedDocument(
                        id=doc_id,
                        content=results["documents"][0][i]
                        if results["documents"]
                        else "",
                        metadata=dict(meta),
                        relevance_score=similarity,
                        collection=collection,
                    )
                )

        return retrieved

    def query_all(
        self,
        query_text: str,
        n_results_per_collection: int = 3,
    ) -> list[RetrievedDocument]:
        """Query all collections and merge results.

        Args:
            query_text: Query text
            n_results_per_collection: Results per collection

        Returns:
            Merged and sorted list of documents
        """
        all_results = []

        for collection in self.COLLECTIONS:
            results = self.query(
                collection=collection,
                query_text=query_text,
                n_results=n_results_per_collection,
            )
            all_results.extend(results)

        # Sort by relevance score
        all_results.sort(key=lambda x: x.relevance_score, reverse=True)

        return all_results

    def get_collection_stats(self) -> dict[str, int]:
        """Get document counts per collection."""
        return {name: coll.count() for name, coll in self._collections.items()}

    def clear_collection(self, collection: str) -> None:
        """Clear all documents from a collection."""
        if collection not in self.COLLECTIONS:
            raise ValueError(f"Unknown collection: {collection}")

        # Delete and recreate
        self.client.delete_collection(collection)
        self._collections[collection] = self.client.get_or_create_collection(
            name=collection,
            metadata={"description": f"Arete {collection} knowledge base"},
        )
        logger.info(f"Cleared collection: {collection}")
