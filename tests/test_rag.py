"""Tests for RAG (Retrieval-Augmented Generation) module."""

import tempfile
from pathlib import Path

import pytest

from arete.rag.knowledge_base import Document, KnowledgeBase, RetrievedDocument
from arete.rag.retriever import (
    CardioBenchmark,
    Retriever,
    StrengthBenchmark,
    UserContext,
)
from arete.rag.seed_knowledge import seed_knowledge_base


@pytest.fixture
def temp_kb_dir():
    """Create a temporary directory for test knowledge base."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def kb(temp_kb_dir):
    """Create a test knowledge base."""
    return KnowledgeBase(persist_directory=temp_kb_dir)


@pytest.fixture
def seeded_kb(kb):
    """Create and seed a test knowledge base."""
    seed_knowledge_base(kb)
    return kb


class TestKnowledgeBase:
    """Tests for KnowledgeBase class."""

    def test_initialization(self, temp_kb_dir):
        """Test knowledge base initialization."""
        kb = KnowledgeBase(persist_directory=temp_kb_dir)
        assert kb is not None
        assert len(kb.COLLECTIONS) == 3
        assert "scientific" in kb.COLLECTIONS
        assert "protocols" in kb.COLLECTIONS
        assert "exercises" in kb.COLLECTIONS

    def test_add_document(self, kb):
        """Test adding a single document."""
        doc = Document(
            id="test_doc_1",
            content="This is a test document about ACWR.",
            metadata={"type": "test", "topic": "acwr"},
        )
        count = kb.add_documents("scientific", [doc])
        assert count == 1

    def test_add_multiple_documents(self, kb):
        """Test adding multiple documents."""
        docs = [
            Document(
                id=f"test_doc_{i}",
                content=f"Test document {i} about training.",
                metadata={"index": i},
            )
            for i in range(5)
        ]
        count = kb.add_documents("protocols", docs)
        assert count == 5

    def test_metadata_list_sanitization(self, kb):
        """Test that list metadata is properly sanitized."""
        doc = Document(
            id="test_list_meta",
            content="Document with list metadata",
            metadata={
                "authors": ["Author 1", "Author 2"],
                "tags": ["tag1", "tag2", "tag3"],
                "year": 2024,
            },
        )
        # Should not raise ValueError
        count = kb.add_documents("scientific", [doc])
        assert count == 1

    def test_query_empty_collection(self, kb):
        """Test querying an empty collection returns empty list."""
        results = kb.query("exercises", "running workout", n_results=5)
        assert results == []

    def test_invalid_collection(self, kb):
        """Test that invalid collection raises error."""
        doc = Document(id="test", content="Test", metadata={})
        with pytest.raises(ValueError, match="Unknown collection"):
            kb.add_documents("invalid_collection", [doc])


class TestSeedKnowledge:
    """Tests for knowledge base seeding."""

    @pytest.mark.slow
    def test_seed_knowledge_base(self, kb):
        """Test seeding the knowledge base."""
        stats = seed_knowledge_base(kb)
        assert "scientific" in stats
        assert "protocols" in stats
        assert "exercises" in stats
        assert stats["scientific"] >= 5
        assert stats["protocols"] >= 3
        assert stats["exercises"] >= 3

    @pytest.mark.slow
    def test_seed_is_idempotent(self, kb):
        """Test that seeding twice doesn't duplicate documents."""
        stats1 = seed_knowledge_base(kb)
        stats2 = seed_knowledge_base(kb)
        # Counts should be the same (upsert behavior)
        assert stats1 == stats2


class TestRetriever:
    """Tests for Retriever class."""

    def test_initialization(self, kb):
        """Test retriever initialization."""
        retriever = Retriever(kb)
        assert retriever is not None


class TestUserContext:
    """Tests for UserContext dataclass."""

    def test_default_context(self):
        """Test default user context."""
        context = UserContext()
        assert context.experience == "intermediate"
        assert context.primary_sport == "running"
        assert context.fatigue == 5

    def test_context_with_metrics(self):
        """Test context with training metrics."""
        context = UserContext(
            acwr=1.2,
            tsb=-10,
            ctl=80,
            monotony=1.5,
            strain=3000,
        )
        assert context.acwr == 1.2
        assert context.tsb == -10
        assert context.ctl == 80

    def test_risk_level_high(self):
        """Test high risk level detection."""
        context = UserContext(acwr=1.6, fatigue=9)
        assert context.get_risk_level() > 0.5

    def test_risk_level_low(self):
        """Test low risk level."""
        context = UserContext(acwr=1.0, tsb=10, fatigue=3)
        assert context.get_risk_level() <= 0.5


class TestDocument:
    """Tests for Document dataclass."""

    def test_document_creation(self):
        """Test document creation."""
        doc = Document(
            id="test_id",
            content="Test content",
            metadata={"key": "value"},
        )
        assert doc.id == "test_id"
        assert doc.content == "Test content"
        assert doc.metadata == {"key": "value"}

    def test_document_default_metadata(self):
        """Test document with default empty metadata."""
        doc = Document(id="test", content="content")
        assert doc.metadata == {}


class TestRetrievedDocument:
    """Tests for RetrievedDocument dataclass."""

    def test_retrieved_document(self):
        """Test retrieved document creation."""
        doc = RetrievedDocument(
            id="ret_id",
            content="Retrieved content",
            metadata={"source": "test"},
            relevance_score=0.85,
            collection="scientific",
        )
        assert doc.id == "ret_id"
        assert doc.relevance_score == 0.85
        assert doc.collection == "scientific"


class TestStrengthBenchmarkIntegration:
    """Tests for strength benchmark integration in UserContext."""

    def test_strength_benchmark_dataclass(self):
        """Test StrengthBenchmark creation."""
        bench = StrengthBenchmark(
            exercise="Back Squat",
            category="SQUAT",
            muscle="QUADS",
            estimated_1rm=120.0,
            weight_kg=100.0,
            reps=5,
        )
        assert bench.exercise == "Back Squat"
        assert bench.estimated_1rm == 120.0

    def test_context_with_strength_benchmarks(self):
        """Test context with strength benchmarks."""
        benchmarks = [
            StrengthBenchmark("Squat", "SQUAT", "QUADS", 120.0, 100.0, 5),
            StrengthBenchmark("Bench", "PUSH_HORIZONTAL", "CHEST", 80.0, 70.0, 4),
        ]
        context = UserContext(
            strength_benchmarks=benchmarks,
            strength_session_count_30d=8,
            strength_total_volume_30d=15000.0,
        )
        assert len(context.strength_benchmarks) == 2
        assert context.strength_session_count_30d == 8
        assert context.strength_total_volume_30d == 15000.0

    def test_strength_summary_generation(self):
        """Test compact strength summary for prompts."""
        benchmarks = [
            StrengthBenchmark("Back Squat", "SQUAT", "QUADS", 120.0, 100.0, 5),
            StrengthBenchmark("Bench Press", "PUSH_HORIZONTAL", "CHEST", 80.0, 70.0, 4),
            StrengthBenchmark("Deadlift", "HINGE", "GLUTES", 140.0, 120.0, 4),
        ]
        context = UserContext(
            strength_benchmarks=benchmarks,
            strength_session_count_30d=10,
            strength_total_volume_30d=20000.0,
        )
        summary = context.get_strength_summary()

        # Should include key lifts
        assert "Squat:120kg" in summary or "Back Squat:120kg" in summary
        assert "20000kg" in summary
        assert "10sess" in summary

    def test_empty_strength_summary(self):
        """Test that empty benchmarks returns empty string."""
        context = UserContext()
        assert context.get_strength_summary() == ""

    def test_strength_default_values(self):
        """Test default strength values in context."""
        context = UserContext()
        assert context.strength_benchmarks == []
        assert context.strength_session_count_30d == 0
        assert context.strength_total_volume_30d == 0.0
        assert context.strength_volume_by_muscle == {}


class TestCardioBenchmarkIntegration:
    """Tests for cardio benchmark integration in UserContext."""

    def test_cardio_benchmark_dataclass(self):
        """Test CardioBenchmark creation."""
        bench = CardioBenchmark(
            avg_cadence_spm=180,
            avg_vertical_oscillation_mm=8.5,
            avg_ground_contact_time_ms=240,
            avg_stride_length_m=1.15,
            avg_easy_hr=145,
            avg_easy_pace="5:30",
            best_pace="4:15",
            total_distance_km_90d=350.0,
            session_count_90d=40,
        )
        assert bench.avg_cadence_spm == 180
        assert bench.avg_easy_pace == "5:30"
        assert bench.total_distance_km_90d == 350.0

    def test_context_with_cardio_benchmarks(self):
        """Test context with cardio benchmarks."""
        cardio = CardioBenchmark(
            avg_cadence_spm=178,
            avg_easy_pace="5:45",
            total_distance_km_90d=200.0,
        )
        context = UserContext(
            cardio_benchmark=cardio,
            hr_drift_flags=["2024-12-01: potential_fatigue"],
        )
        assert context.cardio_benchmark is not None
        assert context.cardio_benchmark.avg_cadence_spm == 178
        assert len(context.hr_drift_flags) == 1

    def test_cardio_summary_generation(self):
        """Test compact cardio summary for prompts."""
        cardio = CardioBenchmark(
            avg_cadence_spm=180,
            avg_vertical_oscillation_mm=8.2,
            avg_easy_hr=142,
            avg_easy_pace="5:30",
            total_distance_km_90d=400.0,
        )
        context = UserContext(cardio_benchmark=cardio)
        summary = context.get_cardio_summary()

        assert "Cadence:180spm" in summary
        assert "VO:8.2mm" in summary
        assert "EasyPace:5:30" in summary
        assert "EasyHR:142bpm" in summary
        assert "Km90d:400" in summary

    def test_cardio_summary_with_drift_flags(self):
        """Test cardio summary includes drift warnings."""
        cardio = CardioBenchmark(avg_cadence_spm=175)
        context = UserContext(
            cardio_benchmark=cardio,
            hr_drift_flags=["flag1", "flag2"],
        )
        summary = context.get_cardio_summary()
        assert "⚠️Drift:2" in summary

    def test_empty_cardio_summary(self):
        """Test that no cardio benchmark returns empty string."""
        context = UserContext()
        assert context.get_cardio_summary() == ""

    def test_cardio_default_values(self):
        """Test default cardio values in context."""
        context = UserContext()
        assert context.cardio_benchmark is None
        assert context.hr_drift_flags == []
