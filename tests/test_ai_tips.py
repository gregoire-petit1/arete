"""Tests for /tips/daily endpoint."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from arete.api.ai_tips import generate_daily_tip


# ---------- Unit tests for tip generation logic ----------
class TestGenerateDailyTip:
    """Test rule-based tip generation."""

    def test_acwr_danger_returns_alert(self):
        tip, priority = generate_daily_tip(acwr=1.6, tsb=0.0, readiness_score=50.0)
        assert priority == "alert"
        assert "1.60" in tip
        assert "dangereux" in tip.lower()

    def test_tsb_exhausted_returns_alert(self):
        tip, priority = generate_daily_tip(acwr=1.0, tsb=-30.0, readiness_score=40.0)
        assert priority == "alert"
        assert "épuisement" in tip.lower()

    def test_acwr_caution_returns_warning(self):
        tip, priority = generate_daily_tip(acwr=1.4, tsb=0.0, readiness_score=50.0)
        assert priority == "warning"
        assert "1.40" in tip

    def test_tsb_tired_returns_warning(self):
        tip, priority = generate_daily_tip(acwr=1.0, tsb=-15.0, readiness_score=50.0)
        assert priority == "warning"
        assert "fatigue" in tip.lower()

    def test_high_readiness_returns_info(self):
        tip, priority = generate_daily_tip(acwr=1.0, tsb=5.0, readiness_score=85.0)
        assert priority == "info"
        assert "excellente forme" in tip.lower()

    def test_optimal_acwr_returns_info(self):
        tip, priority = generate_daily_tip(acwr=1.1, tsb=0.0, readiness_score=60.0)
        assert priority == "info"
        assert "optimale" in tip.lower()

    def test_no_data_returns_fallback(self):
        tip, priority = generate_daily_tip(acwr=None, tsb=None, readiness_score=None)
        assert priority == "info"
        assert "enregistrez" in tip.lower()

    def test_alert_priority_over_warning(self):
        """ACWR danger takes precedence over TSB tired."""
        _, priority = generate_daily_tip(acwr=1.6, tsb=-15.0, readiness_score=50.0)
        assert priority == "alert"


# ---------- Integration test for endpoint ----------
class TestDailyTipEndpoint:
    """Test the /tips/daily endpoint with mocked DB."""

    @pytest.fixture()
    def client(self):
        from arete.api.main import app

        return TestClient(app)

    def test_endpoint_returns_valid_response(self, client: TestClient):
        """Endpoint returns 200 with correct schema even without DB."""
        with (
            patch(
                "arete.api.ai_tips._get_training_loads", side_effect=Exception("no db")
            ),
            patch("arete.api.ai_tips._get_tss_history", side_effect=Exception("no db")),
        ):
            resp = client.get("/tips/daily")
            assert resp.status_code == 200
            data = resp.json()
            assert "tip" in data
            assert data["priority"] in ("info", "warning", "alert")
            assert "generated_at" in data

    def test_endpoint_with_mocked_metrics(self, client: TestClient):
        """Endpoint uses metrics when available."""
        from datetime import date

        from arete.features.fitness import (
            DailyTSS,
            FormZone,
            PerformanceModel,
            ReadinessLevel,
        )
        from arete.features.workload import ACWRZone, DailyLoad, WorkloadMetrics

        fake_loads = [DailyLoad(date=date.today(), duration_min=60, rpe=7)]
        fake_workload = WorkloadMetrics(
            date=date.today(),
            acute_load=420,
            chronic_load=300,
            acwr=1.4,
            acwr_zone=ACWRZone.CAUTION,
            acwr_ewma=1.35,
            monotony=1.2,
            monotony_zone=None,
            strain=504.0,
            strain_zone=None,
        )
        fake_tss = [DailyTSS(date=date.today(), tss=80.0)]
        fake_model = PerformanceModel(
            date=date.today(),
            ctl=50.0,
            atl=60.0,
            tsb=-10.0,
            form_zone=FormZone.NEUTRAL,
            readiness_score=55.0,
            readiness_level=ReadinessLevel.MODERATE,
            predicted_performance=90.0,
            ramp_rate=3.0,
        )

        with (
            patch("arete.api.ai_tips._get_training_loads", return_value=fake_loads),
            patch(
                "arete.api.ai_tips.compute_workload_metrics", return_value=fake_workload
            ),
            patch("arete.api.ai_tips._get_tss_history", return_value=fake_tss),
            patch(
                "arete.api.ai_tips.compute_performance_model", return_value=fake_model
            ),
        ):
            resp = client.get("/tips/daily")
            assert resp.status_code == 200
            data = resp.json()
            # ACWR 1.4 → warning
            assert data["priority"] == "warning"
            assert "1.40" in data["tip"]
