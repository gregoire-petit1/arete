"""Tests for LLM token manager."""

import pytest

from arete.llm.token_manager import GroqLimits, TokenManager


class TestGroqLimits:
    """Test Groq rate limits configuration."""

    def test_known_model_limits(self):
        limits = GroqLimits.for_model("llama-3.3-70b-versatile")
        assert limits.tokens_per_day == 100000
        assert limits.tokens_per_minute == 12000
        assert limits.requests_per_day == 1000

    def test_fallback_limits_for_unknown_model(self):
        limits = GroqLimits.for_model("unknown-model")
        assert limits.tokens_per_day == 100000  # Conservative default
        assert limits.requests_per_day == 1000


class TestTokenManager:
    """Test TokenManager for rate limiting."""

    @pytest.fixture
    def temp_data_dir(self, tmp_path):
        """Create a temporary data directory."""
        return tmp_path / "data"

    @pytest.fixture
    def token_manager(self, temp_data_dir):
        """Create a TokenManager with temp directory."""
        return TokenManager(data_dir=temp_data_dir)

    def test_initialization(self, token_manager):
        """Test TokenManager initializes correctly."""
        stats = token_manager.get_usage_stats()
        assert stats["tokens"]["today"] == 0
        assert stats["requests"]["today"] == 0

    def test_record_usage(self, token_manager):
        """Test recording token usage."""
        token_manager.record_usage(
            model="llama-3.3-70b-versatile",
            prompt_tokens=100,
            completion_tokens=50,
        )
        stats = token_manager.get_usage_stats()
        assert stats["tokens"]["today"] == 150
        assert stats["requests"]["today"] == 1

    def test_can_make_request_under_limit(self, token_manager):
        """Test can_make_request returns True when under limits."""
        can, reason = token_manager.can_make_request(
            "llama-3.3-70b-versatile",
            estimated_tokens=1000,
        )
        assert can is True
        assert reason == "OK"

    def test_can_make_request_near_limit(self, token_manager):
        """Test can_make_request returns False when near limits."""
        # Simulate usage near daily limit
        for _ in range(60):
            token_manager.record_usage(
                model="llama-3.3-70b-versatile",
                prompt_tokens=1500,
                completion_tokens=500,
            )
        # 60 * 2000 = 120,000 tokens > 100,000 limit
        can, reason = token_manager.can_make_request(
            "llama-3.3-70b-versatile",
            estimated_tokens=2000,
        )
        assert can is False
        assert "limit" in reason.lower()

    def test_get_best_model(self, token_manager):
        """Test model selection when primary quota exhausted."""
        # Fresh manager should prefer best model
        best = token_manager.get_best_model(estimated_tokens=2000)
        assert best == "llama-3.3-70b-versatile"

    def test_usage_stats_structure(self, token_manager):
        """Test usage stats have correct structure."""
        stats = token_manager.get_usage_stats()

        assert "model" in stats
        assert "tokens" in stats
        assert "requests" in stats
        assert "remaining" in stats

        assert "today" in stats["tokens"]
        assert "limit_day" in stats["tokens"]
        assert "percent_day" in stats["tokens"]
