"""Tests for daily readiness score computation."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from arete.api.garmin_health import router
from arete.garmin.readiness import compute_readiness


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


def _seed_metrics(rows: list[tuple]) -> None:
    """Insert test rows into app.daily_metrics. Each row: (date, hrv, sleep, bb, stress, rhr)."""
    with patch("arete.garmin.readiness.connect") as mock_connect:
        mock_conn = mock_connect.return_value
        mock_conn.execute.return_value.fetchone.return_value = None
        # Just let the test skip baseline calculation by inserting no history
        compute_readiness(date(2026, 6, 1))


class TestReadinessFormula:
    def test_no_data_returns_none(self):
        with patch("arete.garmin.readiness.connect") as mock_connect:
            mock_conn = mock_connect.return_value
            mock_conn.execute.return_value.fetchone.return_value = None
            assert compute_readiness(date(2026, 6, 1)) is None

    def test_strong_recovery_high_score(self):
        """HRV above baseline, full sleep, BB 100 = high score."""
        with patch("arete.garmin.readiness.connect") as mock_connect:
            mock_conn = mock_connect.return_value
            # First call: fetch_day_metrics returns (hrv, sleep, bb, stress, rhr)
            # Second call: fetch_baseline returns rows for stats
            mock_conn.execute.return_value.fetchone.return_value = (
                80,
                8 * 3600,
                100,
                25,
                50,
            )
            mock_conn.execute.return_value.fetchall.return_value = [
                (60, 7 * 3600, 80, 30, 52) for _ in range(14)
            ]
            score = compute_readiness(date(2026, 6, 1))
            assert score is not None
            assert score >= 80  # strong recovery

    def test_poor_recovery_low_score(self):
        """HRV below baseline, short sleep, low BB = low score."""
        with patch("arete.garmin.readiness.connect") as mock_connect:
            mock_conn = mock_connect.return_value
            mock_conn.execute.return_value.fetchone.return_value = (
                30,
                4 * 3600,
                30,
                60,
                60,
            )
            mock_conn.execute.return_value.fetchall.return_value = [
                (60, 7 * 3600, 80, 30, 52) for _ in range(14)
            ]
            score = compute_readiness(date(2026, 6, 1))
            assert score is not None
            assert score < 40  # poor recovery

    def test_cold_start_with_data(self):
        """Less than 5 days of baseline history = fallback to 1.0 ratios."""
        with patch("arete.garmin.readiness.connect") as mock_connect:
            mock_conn = mock_connect.return_value
            mock_conn.execute.return_value.fetchone.return_value = (
                60,
                8 * 3600,
                80,
                30,
                50,
            )
            mock_conn.execute.return_value.fetchall.return_value = []  # no history
            score = compute_readiness(date(2026, 6, 1))
            # Fallback: hrv_ratio=1.0 (ratio 0.5 from 0.5 offset = 0.5 → 0.5 mapped)
            # sleep_ratio=1.0 (8h = target, 0.5/0.7 = 0.71)
            # bb=80 (0.8)
            # score = 0.4*0.5 + 0.3*0.71 + 0.3*0.8 = 0.2 + 0.21 + 0.24 = 0.65 → 65
            assert 50 <= score <= 80

    def test_penalty_for_high_stress(self):
        """Stress significantly above baseline = score penalty."""
        with patch("arete.garmin.readiness.connect") as mock_connect:
            mock_conn = mock_connect.return_value
            # Target: stress 70 (vs baseline mean 30, std 5 = +8 std) → -40 penalty
            mock_conn.execute.return_value.fetchone.return_value = (
                80,
                8 * 3600,
                100,
                70,
                50,
            )
            # Varied baseline: stress ~30 ± 5, so std > 0
            mock_conn.execute.return_value.fetchall.return_value = [
                (60, 7 * 3600, 80, 25 + (i % 5), 52) for i in range(14)
            ]
            score = compute_readiness(date(2026, 6, 1))
            # Base ~85, but penalty should bring it well under
            assert score < 50

    def test_score_clamped_0_100(self):
        """Score is always 0-100."""
        with patch("arete.garmin.readiness.connect") as mock_connect:
            mock_conn = mock_connect.return_value
            # Worst case: very low HRV, no sleep, BB 0
            mock_conn.execute.return_value.fetchone.return_value = (1, 0, 0, 100, 100)
            mock_conn.execute.return_value.fetchall.return_value = [
                (60, 7 * 3600, 80, 30, 52) for _ in range(14)
            ]
            score = compute_readiness(date(2026, 6, 1))
            assert 0 <= score <= 100

    def test_extreme_stress_penalty_clamped(self):
        """Even huge stress penalty shouldn't push below 0."""
        with patch("arete.garmin.readiness.connect") as mock_connect:
            mock_conn = mock_connect.return_value
            mock_conn.execute.return_value.fetchone.return_value = (
                60,
                8 * 3600,
                80,
                200,
                50,
            )
            mock_conn.execute.return_value.fetchall.return_value = [
                (60, 7 * 3600, 80, 30, 5)
                for _ in range(14)  # std = 0
            ]
            score = compute_readiness(date(2026, 6, 1))
            assert score >= 0


class TestGarminHealthApi:
    @patch("arete.api.garmin_health.connect")
    def test_status_endpoint(self, mock_connect, client):
        mock_conn = mock_connect.return_value
        mock_conn.execute.return_value.fetchone.return_value = (
            5,
            "2026-05-28",
            "2026-06-01",
            None,
        )
        with (
            patch("pathlib.Path.exists") as mock_exists,
            patch("pathlib.Path.iterdir") as mock_iter,
        ):
            mock_exists.return_value = True
            mock_iter.return_value = ["token1"]
            resp = client.get("/garmin/health/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["days_stored"] == 5
            assert data["tokens_present"] is True

    @patch("arete.api.garmin_health.connect")
    def test_daily_endpoint_404_when_no_data(self, mock_connect, client):
        mock_conn = mock_connect.return_value
        mock_conn.execute.return_value.fetchone.return_value = None
        resp = client.get("/garmin/health/daily?date=2026-06-01")
        assert resp.status_code == 404

    @patch("arete.api.garmin_health.connect")
    def test_daily_endpoint_returns_metrics(self, mock_connect, client):
        mock_conn = mock_connect.return_value
        mock_conn.execute.return_value.fetchone.return_value = (
            "2026-06-01",
            60,
            70,
            "BALANCED",
            28800,
            85,
            7200,
            14400,
            5400,
            1800,
            80,
            30,
            95,
            40,
            48,
            25,
            60,
            8500,
            45,
            82,
            "garmin",
            "2026-06-01 10:00:00",
        )
        resp = client.get("/garmin/health/daily?date=2026-06-01")
        assert resp.status_code == 200
        data = resp.json()
        assert data["hrv_last_night"] == 70
        assert data["sleep_duration_sec"] == 28800
        assert data["body_battery_high"] == 95
        assert data["readiness_score"] == 82

    @patch("arete.api.garmin_health.connect")
    def test_range_endpoint(self, mock_connect, client):
        mock_conn = mock_connect.return_value
        mock_conn.execute.return_value.fetchall.return_value = [
            ("2026-05-30", 60, 65, 80, 28800, 90, 40, 25, 50, 78, 8000),
            ("2026-05-31", 65, 67, 85, 30000, 95, 45, 22, 48, 85, 9500),
        ]
        resp = client.get("/garmin/health/range?start=2026-05-30&end=2026-05-31")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["days"]) == 2
        assert data["days"][0]["readiness_score"] == 78
