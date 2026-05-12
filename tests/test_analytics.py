"""Tests for the analytics API endpoints."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from arete.api.analytics import _format_pace, _parse_period, router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# ---------- Helper tests ----------


class TestHelpers:
    def test_parse_period_known(self):
        assert _parse_period("7d") == 7
        assert _parse_period("30d") == 30
        assert _parse_period("90d") == 90
        assert _parse_period("6m") == 180
        assert _parse_period("1y") == 365
        assert _parse_period("all") == 3650

    def test_parse_period_unknown_defaults_30(self):
        assert _parse_period("xyz") == 30

    def test_format_pace(self):
        assert _format_pace(320) == "5:20"
        assert _format_pace(240) == "4:00"
        assert _format_pace(305) == "5:05"


# ---------- Endpoint tests ----------


class TestVolume:
    @patch("arete.api.analytics.connect")
    def test_returns_weekly_volume(self, mock_connect, client):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [
            (date(2026, 5, 5), "run", 3.5, 35.0),
            (date(2026, 5, 5), "ride", 2.0, 50.0),
        ]

        resp = client.get("/analytics/volume?period=30d")
        assert resp.status_code == 200
        data = resp.json()
        assert "weeks" in data
        assert len(data["weeks"]) == 1
        week = data["weeks"][0]
        assert "run" in week["sports"]
        assert week["total_hours"] == 5.5
        mock_conn.close.assert_called_once()

    @patch("arete.api.analytics.connect")
    def test_volume_with_sport_filter(self, mock_connect, client):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = []

        resp = client.get("/analytics/volume?sport=run")
        assert resp.status_code == 200
        assert resp.json() == {"weeks": []}
        # Verify sport param was passed (second param)
        call_args = mock_conn.execute.call_args
        assert "run" in call_args[0][1]


class TestTrainingLoad:
    @patch("arete.api.analytics._get_tss_history")
    def test_returns_daily_ctl_atl_tsb(self, mock_tss, client):
        from arete.features.fitness import DailyTSS

        mock_tss.return_value = [
            DailyTSS(date=date(2026, 5, 1), tss=50.0),
            DailyTSS(date=date(2026, 5, 2), tss=60.0),
        ]

        resp = client.get("/analytics/training-load?period=7d")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert len(data["data"]) == 2
        entry = data["data"][0]
        assert "ctl" in entry
        assert "atl" in entry
        assert "tsb" in entry
        assert "tss" in entry


class TestPace:
    @patch("arete.api.analytics.connect")
    def test_returns_pace_activities(self, mock_connect, client):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [
            (date(2026, 5, 1), 320, 10500, 3360, "Morning Run"),
        ]

        resp = client.get("/analytics/pace?period=90d&sport=running")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["activities"]) == 1
        act = data["activities"][0]
        assert act["pace_sec_km"] == 320
        assert act["pace_display"] == "5:20"
        assert act["distance_km"] == 10.5
        mock_conn.close.assert_called_once()


class TestHRZones:
    @patch("arete.api.analytics.connect")
    def test_returns_weekly_hr_zones(self, mock_connect, client):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [
            (date(2026, 5, 5), '{"zone1": 600, "zone2": 1200, "zone3": 300}'),
            (date(2026, 5, 5), '{"zone1": 400, "zone2": 800, "zone3": 200}'),
        ]

        resp = client.get("/analytics/hr-zones?period=30d")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["weeks"]) == 1
        zones = data["weeks"][0]["zones"]
        assert zones["zone1"] == 1000
        assert zones["zone2"] == 2000

    @patch("arete.api.analytics.connect")
    def test_returns_empty_when_no_data(self, mock_connect, client):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = []

        resp = client.get("/analytics/hr-zones")
        assert resp.status_code == 200
        assert resp.json() == {"weeks": []}


class TestSportDistribution:
    @patch("arete.api.analytics.connect")
    def test_returns_sport_distribution(self, mock_connect, client):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [
            ("run", 25.5, 20),
            ("ride", 10.2, 8),
        ]

        resp = client.get("/analytics/sport-distribution?period=90d")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["sports"]) == 2
        assert data["total_hours"] == 35.7
        assert data["sports"][0]["sport"] == "run"
        assert data["sports"][0]["percentage"] > 0


class TestBestEfforts:
    @patch("arete.api.analytics.connect")
    def test_returns_best_efforts(self, mock_connect, client):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [
            (
                '[{"name": "1k", "elapsed_time": 240, "distance": 1000}, '
                '{"name": "5k", "elapsed_time": 1250, "distance": 5000}]',
                date(2026, 5, 1),
                "Morning Run",
            ),
            (
                '[{"name": "1k", "elapsed_time": 234, "distance": 1000}]',
                date(2026, 4, 20),
                "Fast Run",
            ),
        ]

        resp = client.get("/analytics/best-efforts?sport=running")
        assert resp.status_code == 200
        data = resp.json()
        efforts = data["efforts"]
        # 1k should pick the best (234 from "Fast Run")
        one_k = next(e for e in efforts if e["name"] == "1k")
        assert one_k["best_time_sec"] == 234
        assert one_k["activity_name"] == "Fast Run"
        # 5k present
        five_k = next(e for e in efforts if e["name"] == "5k")
        assert five_k["best_time_sec"] == 1250


class TestSessionUpdate:
    @patch("arete.api.analytics.connect")
    def test_update_rpe_and_notes(self, mock_connect, client):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        resp = client.patch(
            "/analytics/sessions/42", json={"rpe": 7, "notes": "Felt good"}
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        mock_conn.execute.assert_called_once()

    @patch("arete.api.analytics.connect")
    def test_update_empty_body(self, mock_connect, client):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        resp = client.patch("/analytics/sessions/42", json={})
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        mock_conn.execute.assert_not_called()


class TestListSessions:
    @patch("arete.api.analytics.connect")
    def test_returns_sessions(self, mock_connect, client):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [
            (
                1,
                date(2026, 5, 10),
                "run",
                "Morning Run",
                3600,
                10000,
                145,
                320,
                7,
                "Great",
                "strava",
                450,
            ),
        ]
        resp = client.get("/analytics/sessions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["sessions"]) == 1
        assert data["sessions"][0]["name"] == "Morning Run"
        assert data["sessions"][0]["pace_display"] == "5:20"
