"""Tests for the analytics API endpoints."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from arete.api.analytics import _format_pace, _parse_period, router


@pytest.fixture
def client(router_client):
    return router_client(router)


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
    @patch("arete.api.analytics.tss_history")
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


class TestCardiacEfficiency:
    @patch("arete.api.analytics.connect")
    def test_returns_weekly_efficiency(self, mock_connect, client):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [
            (date(2026, 5, 5), 165, 330, 3600),  # week, hr, pace, duration
            (date(2026, 5, 5), 170, 340, 2400),  # same week, second run
        ]

        resp = client.get("/analytics/cardiac-efficiency?period=30d")
        assert resp.status_code == 200
        data = resp.json()
        assert "data" in data
        assert len(data["data"]) == 1
        entry = data["data"][0]
        assert "efficiency" in entry
        assert "avg_hr" in entry
        assert "n_runs" in entry
        assert entry["n_runs"] == 2
        # Efficiency should be a reasonable number (hr / speed_kmh)
        assert 10 < entry["efficiency"] < 30

    @patch("arete.api.analytics.connect")
    def test_empty_when_no_runs(self, mock_connect, client):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = []

        resp = client.get("/analytics/cardiac-efficiency?period=30d")
        assert resp.status_code == 200
        assert resp.json() == {"data": []}


class TestHrPaceScatter:
    @patch("arete.api.analytics.connect")
    def test_returns_sessions(self, mock_connect, client):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [
            (date(2026, 5, 1), "run", "Morning Run", 165, 185, 330, 120, 10.5, 3600),
            (date(2026, 5, 3), "walk", "Walk", 110, 130, None, 50, 5.0, 2400),
        ]

        resp = client.get("/analytics/hr-pace-scatter?period=90d")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["sessions"]) == 2
        run = data["sessions"][0]
        assert run["avg_hr"] == 165
        assert run["pace_sec_km"] == 330
        assert run["elevation_gain"] == 120
        assert run["distance_km"] == 10.5
        assert run["pace_display"] == "5:30"
        # Walk has no pace
        walk = data["sessions"][1]
        assert walk["pace_sec_km"] is None
        assert walk["pace_display"] is None

    @patch("arete.api.analytics.connect")
    def test_empty_when_no_data(self, mock_connect, client):
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = []

        resp = client.get("/analytics/hr-pace-scatter")
        assert resp.status_code == 200
        assert resp.json() == {"sessions": []}


# ---------- HR drift tests ----------


def _make_laps(n: int, hr_first: float, hr_last: float, elev: float = 0) -> str:
    """Build a JSON laps list: n 1-km laps, HR rising from hr_first to hr_last."""
    import json as _json

    laps = []
    for i in range(n):
        hr = hr_first + (hr_last - hr_first) * i / max(n - 1, 1)
        laps.append(
            {
                "distance": 1000,
                "average_heartrate": hr,
                "average_speed": 1000 / 360,  # 6:00/km pace
                "total_elevation_gain": elev,
            }
        )
    return _json.dumps(laps)


class TestHrDrift:
    @patch("arete.api.analytics.connect")
    def test_negative_hr_drift_is_excellent(self, mock_connect, client):
        """Run with HR dropping from 160 to 150 over 10 km = negative split."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        # 10 km, 60 min, pace 360 sec/km, HR drops 160→150
        mock_conn.execute.return_value.fetchall.return_value = [
            (
                1,
                date(2026, 5, 23),
                "Long Run",
                10000,
                100,
                3600,
                155,
                360,
                _make_laps(10, 160, 150),
            ),
        ]

        resp = client.get("/analytics/hr-drift?period=1y")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        run = data["runs"][0]
        assert run["hr_drift_pct"] < 0
        assert run["drift_score"] == "excellent"
        assert "negative_hr_drift" in run["tags"]
        assert len(run["splits"]) == 10

    @patch("arete.api.analytics.connect")
    def test_high_hr_drift_base_run_is_concerning(self, mock_connect, client):
        """Base run with HR rising 15% = concerning aerobic deficit."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        # 10 km flat (D+=10), 360 sec/km, HR 140→180 (+28% range, ~15% half-drift)
        mock_conn.execute.return_value.fetchall.return_value = [
            (
                1,
                date(2026, 5, 1),
                "Base Run",
                10000,
                10,
                3600,
                160,
                360,
                _make_laps(10, 140, 180),
            ),
        ]

        resp = client.get("/analytics/hr-drift?period=1y")
        data = resp.json()
        assert data["count"] == 1
        run = data["runs"][0]
        # Half-drift should be around 14-15%
        assert run["hr_drift_pct"] > 13
        assert run["drift_score"] == "concerning"

    @patch("arete.api.analytics.connect")
    def test_workout_gets_lenient_threshold(self, mock_connect, client):
        """Hard interval workout: pace 5:00/km, HR rises 15% — should NOT be concerning
        because run_type=intensity has higher threshold."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        # 8 km, 40 min, pace 300 sec/km (5:00/km = intensity), HR 165→190 (+15%)
        mock_conn.execute.return_value.fetchall.return_value = [
            (
                1,
                date(2026, 5, 5),
                "Thresholds",
                8000,
                10,
                2400,
                178,
                300,
                _make_laps(8, 165, 190),
            ),
        ]

        resp = client.get("/analytics/hr-drift?period=1y")
        run = resp.json()["runs"][0]
        assert run["run_type"] == "intensity"
        # 15% HR drift is at the threshold of "moderate" for intensity (12-18%)
        assert run["drift_score"] in ("good", "moderate")

    @patch("arete.api.analytics.connect")
    def test_short_run_filtered_out(self, mock_connect, client):
        """Run with < 4 full 1-km laps should be excluded (insufficient data)."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        # 3 km, 18 min — only 3 full 1-km laps (need >= 4)
        mock_conn.execute.return_value.fetchall.return_value = [
            (
                1,
                date(2026, 5, 1),
                "Short",
                3000,
                10,
                1080,
                160,
                300,
                _make_laps(3, 150, 170),
            ),
        ]

        resp = client.get("/analytics/hr-drift?period=1y")
        assert resp.json()["count"] == 0

    @patch("arete.api.analytics.connect")
    def test_runs_without_laps_excluded(self, mock_connect, client):
        """Runs with NULL laps_json should be skipped."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [
            (1, date(2026, 5, 1), "No Laps", 10000, 100, 3600, 155, 360, None),
        ]

        resp = client.get("/analytics/hr-drift?period=1y")
        assert resp.json()["count"] == 0

    @patch("arete.api.analytics.connect")
    def test_min_lap_count_required(self, mock_connect, client):
        """Need at least 4 full 1-km laps to compute drift."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        # Only 3 laps (3 km) — should be excluded
        mock_conn.execute.return_value.fetchall.return_value = [
            (
                1,
                date(2026, 5, 1),
                "Short",
                3000,
                10,
                1800,
                160,
                360,
                _make_laps(3, 150, 170),
            ),
        ]

        resp = client.get("/analytics/hr-drift?period=1y")
        assert resp.json()["count"] == 0

    @patch("arete.api.analytics.connect")
    def test_baseline_regression_fitted(self, mock_connect, client):
        """With enough runs, baseline regression should be computed."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        # 12 runs, varied distance/elev/pace
        runs = []
        for i in range(12):
            runs.append(
                (
                    i + 1,
                    date(2026, 5, i + 1),
                    f"Run {i}",
                    8000 + i * 500,
                    50 + i * 20,
                    3000 + i * 200,
                    155,
                    320 + i * 10,
                    _make_laps(10, 150 + i, 165 + i),
                )
            )
        mock_conn.execute.return_value.fetchall.return_value = runs

        resp = client.get("/analytics/hr-drift?period=1y")
        data = resp.json()
        assert data["baseline"] is not None
        assert "coefficients" in data["baseline"]
        assert "r_squared" in data["baseline"]
        assert data["baseline"]["n_samples"] == 12
        # All runs should have residual computed
        assert all(r.get("drift_residual_pct") is not None for r in data["runs"])

    @patch("arete.api.analytics.connect")
    def test_effort_buckets_computed(self, mock_connect, client):
        """Effort buckets should classify runs by distance + elevation."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        runs = [
            # 8 km, 50m = short
            (
                1,
                date(2026, 5, 1),
                "Short",
                8000,
                50,
                2700,
                155,
                340,
                _make_laps(8, 150, 160),
            ),
            # 15 km, 500m = 33 m/km → moderate_hilly (> 30 m/km)
            (
                2,
                date(2026, 5, 2),
                "ModHilly",
                15000,
                500,
                5400,
                158,
                360,
                _make_laps(15, 150, 160),
            ),
            # 22 km, 1500m = 68 m/km → long_hilly (40-80 m/km range)
            (
                3,
                date(2026, 5, 3),
                "LongHilly",
                22000,
                1500,
                9000,
                160,
                410,
                _make_laps(22, 150, 160),
            ),
        ]
        mock_conn.execute.return_value.fetchall.return_value = runs

        resp = client.get("/analytics/hr-drift?period=1y")
        buckets = resp.json()["effort_buckets"]
        assert "short" in buckets
        assert "moderate_hilly" in buckets
        assert "long_hilly" in buckets

    @patch("arete.api.analytics.connect")
    def test_too_few_runs_for_baseline(self, mock_connect, client):
        """With <10 runs, baseline regression should be None (fallback to raw thresholds)."""
        mock_conn = MagicMock()
        mock_connect.return_value = mock_conn
        runs = [
            (
                i,
                date(2026, 5, i + 1),
                f"Run {i}",
                10000,
                100,
                3600,
                155,
                360,
                _make_laps(10, 150, 160),
            )
            for i in range(5)
        ]
        mock_conn.execute.return_value.fetchall.return_value = runs

        resp = client.get("/analytics/hr-drift?period=1y")
        data = resp.json()
        assert data["baseline"] is None
        assert all(r.get("drift_residual_pct") is None for r in data["runs"])
