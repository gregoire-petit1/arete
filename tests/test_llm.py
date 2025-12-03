"""Tests for LLM client module."""

from unittest.mock import MagicMock, patch

import pytest

from arete.llm.client import (
    TrainingContext,
    _build_user_prompt,
    _generate_fallback_plan,
    generate_plan,
    get_client,
)
from arete.llm.token_manager import GroqLimits, TokenManager


class TestTrainingContext:
    """Test TrainingContext dataclass."""

    def test_basic_context(self):
        ctx = TrainingContext(
            date="2025-12-02",
            objectif="marathon",
            dispo_min=60,
            fatigue=5,
        )
        assert ctx.date == "2025-12-02"
        assert ctx.objectif == "marathon"
        assert ctx.dispo_min == 60
        assert ctx.fatigue == 5
        assert ctx.acwr is None
        assert ctx.tsb is None

    def test_full_context(self):
        ctx = TrainingContext(
            date="2025-12-02",
            objectif="10k",
            dispo_min=45,
            fatigue=7,
            rpe_moy7j=6.5,
            acwr=1.1,
            acwr_zone="optimal",
            tsb=5.0,
            form_zone="fresh",
            ctl=45.0,
            monotony=1.5,
            strain=200.0,
            recommendations=["Maintenir la charge", "Séance qualité possible"],
        )
        assert ctx.rpe_moy7j == 6.5
        assert ctx.acwr == 1.1
        assert ctx.tsb == 5.0


class TestBuildUserPrompt:
    """Test prompt building."""

    def test_minimal_prompt(self):
        ctx = TrainingContext(
            date="2025-12-02",
            objectif="forme",
            dispo_min=30,
            fatigue=3,
        )
        prompt = _build_user_prompt(ctx)
        assert "2025-12-02" in prompt
        assert "forme" in prompt
        assert "30 minutes" in prompt
        assert "3/10" in prompt

    def test_prompt_with_metrics(self):
        ctx = TrainingContext(
            date="2025-12-02",
            objectif="marathon",
            dispo_min=60,
            fatigue=5,
            acwr=1.2,
            acwr_zone="optimal",
            tsb=-5.0,
            form_zone="neutral",
        )
        prompt = _build_user_prompt(ctx)
        assert "ACWR : 1.20" in prompt
        assert "TSB (forme) : -5.0" in prompt


class TestFallbackPlan:
    """Test fallback plan generation."""

    def test_high_fatigue_recovery(self):
        ctx = TrainingContext(
            date="2025-12-02",
            objectif="marathon",
            dispo_min=60,
            fatigue=9,
        )
        plan = _generate_fallback_plan(ctx)
        assert "récupération" in plan["seance"].lower()
        assert plan["charge_prevue"] == "légère"

    def test_low_tsb_regeneration(self):
        ctx = TrainingContext(
            date="2025-12-02",
            objectif="marathon",
            dispo_min=60,
            fatigue=5,
            tsb=-20.0,
        )
        plan = _generate_fallback_plan(ctx)
        assert "régénération" in plan["seance"].lower()
        assert "TSB" in plan["justification"]

    def test_high_acwr_moderate(self):
        ctx = TrainingContext(
            date="2025-12-02",
            objectif="marathon",
            dispo_min=60,
            fatigue=5,
            acwr=1.5,
        )
        plan = _generate_fallback_plan(ctx)
        assert "ACWR" in plan["justification"]
        assert plan["charge_prevue"] in ["légère", "modérée"]

    def test_normal_metrics_standard_session(self):
        ctx = TrainingContext(
            date="2025-12-02",
            objectif="marathon",
            dispo_min=60,
            fatigue=4,
            acwr=1.0,
            tsb=5.0,
        )
        plan = _generate_fallback_plan(ctx)
        assert "endurance" in plan["seance"].lower()
        assert plan["charge_prevue"] == "modérée"

    def test_plan_structure(self):
        ctx = TrainingContext(
            date="2025-12-02",
            objectif="10k",
            dispo_min=45,
            fatigue=5,
        )
        plan = _generate_fallback_plan(ctx)

        # Check required fields
        assert "seance" in plan
        assert "details" in plan
        assert "cible" in plan
        assert "justification" in plan
        assert "charge_prevue" in plan

        # Check details structure
        assert "echauffement" in plan["details"]
        assert "corps" in plan["details"]
        assert "retour_calme" in plan["details"]

        # Check cible structure
        assert "fc" in plan["cible"]
        assert "allure" in plan["cible"]
        assert "duree_totale" in plan["cible"]


class TestGetClient:
    """Test client initialization."""

    def test_no_api_key(self):
        with patch.dict("os.environ", {}, clear=True):
            # Remove GROQ_API_KEY if present
            import os

            env_backup = os.environ.get("GROQ_API_KEY")
            if "GROQ_API_KEY" in os.environ:
                del os.environ["GROQ_API_KEY"]
            try:
                client = get_client()
                assert client is None
            finally:
                if env_backup:
                    os.environ["GROQ_API_KEY"] = env_backup

    def test_with_api_key(self):
        with patch.dict("os.environ", {"GROQ_API_KEY": "test_key"}):
            client = get_client()
            assert client is not None
            assert client.base_url.host == "api.groq.com"


class TestGeneratePlan:
    """Test plan generation."""

    def test_fallback_when_no_client(self):
        with patch("arete.llm.client.get_client", return_value=None):
            ctx = TrainingContext(
                date="2025-12-02",
                objectif="marathon",
                dispo_min=60,
                fatigue=5,
            )
            plan = generate_plan(ctx)
            assert "seance" in plan
            assert "details" in plan

    def test_llm_success(self):
        mock_response = MagicMock()
        mock_response.choices = [
            MagicMock(
                message=MagicMock(
                    content='{"seance": "Test séance", "details": {}, "cible": {}, "justification": "test", "charge_prevue": "modérée"}'
                )
            )
        ]
        mock_response.usage = MagicMock(
            prompt_tokens=100,
            completion_tokens=50,
        )

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        mock_token_manager = MagicMock()
        mock_token_manager.get_best_model.return_value = "llama-3.3-70b-versatile"
        mock_token_manager.can_make_request.return_value = (True, "OK")
        mock_token_manager.wait_if_needed.return_value = 0.0

        with (
            patch("arete.llm.client.get_client", return_value=mock_client),
            patch(
                "arete.llm.client.get_token_manager", return_value=mock_token_manager
            ),
        ):
            ctx = TrainingContext(
                date="2025-12-02",
                objectif="marathon",
                dispo_min=60,
                fatigue=5,
            )
            plan = generate_plan(ctx)
            assert plan["seance"] == "Test séance"

    def test_llm_error_fallback(self):
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = Exception("API Error")

        mock_token_manager = MagicMock()
        mock_token_manager.get_best_model.return_value = "llama-3.3-70b-versatile"
        mock_token_manager.can_make_request.return_value = (True, "OK")
        mock_token_manager.wait_if_needed.return_value = 0.0

        with (
            patch("arete.llm.client.get_client", return_value=mock_client),
            patch(
                "arete.llm.client.get_token_manager", return_value=mock_token_manager
            ),
        ):
            ctx = TrainingContext(
                date="2025-12-02",
                objectif="marathon",
                dispo_min=60,
                fatigue=5,
            )
            plan = generate_plan(ctx)
            # Should fall back to rule-based
            assert "seance" in plan
            assert "details" in plan

    def test_rate_limit_fallback(self):
        """Test fallback when rate limit is reached."""
        mock_token_manager = MagicMock()
        mock_token_manager.get_best_model.return_value = "llama-3.3-70b-versatile"
        mock_token_manager.can_make_request.return_value = (
            False,
            "Daily limit reached",
        )

        with (
            patch("arete.llm.client.get_client", return_value=MagicMock()),
            patch(
                "arete.llm.client.get_token_manager", return_value=mock_token_manager
            ),
        ):
            ctx = TrainingContext(
                date="2025-12-02",
                objectif="marathon",
                dispo_min=60,
                fatigue=5,
            )
            plan = generate_plan(ctx)
            # Should use fallback plan
            assert "seance" in plan
            assert "details" in plan


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
