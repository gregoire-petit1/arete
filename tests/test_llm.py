"""Tests for LLM client module."""

import pytest
from unittest.mock import patch, MagicMock
from arete.llm.client import (
    TrainingContext,
    generate_plan,
    _generate_fallback_plan,
    _build_user_prompt,
    get_client,
)


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

        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response

        with patch("arete.llm.client.get_client", return_value=mock_client):
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

        with patch("arete.llm.client.get_client", return_value=mock_client):
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
