"""Analytics API: the overview bundle, personal records, session CRUD."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import pytest

from arete.api.analytics import router
from arete.features.fitness import DailyTSS

TODAY = date.today()

CARD_KEYS = {
    "volume",
    "pmc",
    "zones",
    "sports",
    "decoupling",
    "pace",
    "readiness",
    "hrv",
    "sleep",
    "resting_hr",
}


@pytest.fixture
def client(router_client):
    return router_client(router)


@pytest.fixture
def stub_queries():
    """Patch every SELECT the overview makes; each test sets what it needs."""
    targets = {
        "volume_rows": [],
        "zone_rows": [],
        "sport_totals": [],
        "pace_rows": [],
        "drift_rows": [],
        "efficiency_rows": [],
        "daily_metrics_range": [],
        "earliest_session_date": None,
        "training_loads": [],
    }
    patches = {
        name: patch(f"arete.api.analytics.{name}", return_value=value)
        for name, value in targets.items()
    }
    mocks = {name: p.start() for name, p in patches.items()}
    with (
        patch("arete.api.analytics.db_connection"),
        patch("arete.api.analytics.tss_history", return_value=[]) as tss,
    ):
        mocks["tss_history"] = tss
        yield mocks
    for p in patches.values():
        p.stop()


class TestOverview:
    def test_returns_every_card(self, client, stub_queries):
        resp = client.get("/analytics/overview?period=30d")
        assert resp.status_code == 200
        data = resp.json()
        assert data["period"] == "30d"
        assert data["bucket"] == "day"
        assert set(data["cards"]) == CARD_KEYS

    def test_unknown_period_falls_back_to_30d(self, client, stub_queries):
        data = client.get("/analytics/overview?period=xyz").json()
        assert data["period"] == "30d"

    def test_long_period_switches_bucket(self, client, stub_queries):
        assert client.get("/analytics/overview?period=90d").json()["bucket"] == "week"
        assert client.get("/analytics/overview?period=1y").json()["bucket"] == "month"

    def test_all_period_has_no_previous_window(self, client, stub_queries):
        stub_queries["earliest_session_date"].return_value = TODAY - timedelta(days=200)
        data = client.get("/analytics/overview?period=all").json()
        assert data["start"] == (TODAY - timedelta(days=200)).isoformat()
        assert data["prev_start"] is None

    def test_volume_card_uses_sessions(self, client, stub_queries):
        stub_queries["volume_rows"].return_value = [
            (TODAY - timedelta(days=1), "running", 3600, 12000.0),
            (TODAY - timedelta(days=40), "running", 3600, 8000.0),
        ]
        card = client.get("/analytics/overview?period=30d").json()["cards"]["volume"]
        assert card["headline"]["value"] == 12.0
        assert card["headline"]["previous"] == 8.0
        assert len(card["series"]) == 30

    def test_pmc_card_uses_tss_history_with_warmup(self, client, stub_queries):
        stub_queries["tss_history"].return_value = [
            DailyTSS(date=TODAY - timedelta(days=i), tss=60.0)
            for i in range(60, -1, -1)
        ]
        data = client.get("/analytics/overview?period=30d").json()
        stub_queries["tss_history"].assert_called_once_with(days=60 + 84)
        assert data["cards"]["pmc"]["headline"]["value"] > 0

    def test_sports_card_compares_windows(self, client, stub_queries):
        stub_queries["sport_totals"].side_effect = [
            [("running", 6.0, 4), ("strength", 2.0, 2)],
            [("running", 4.0, 3)],
        ]
        card = client.get("/analytics/overview?period=30d").json()["cards"]["sports"]
        assert card["headline"]["value"] == 8.0
        assert card["headline"]["previous"] == 4.0

    def test_no_data_still_renders_cards(self, client, stub_queries):
        cards = client.get("/analytics/overview?period=7d").json()["cards"]
        assert cards["volume"]["headline"]["value"] == 0.0
        assert cards["hrv"]["headline"]["value"] is None
        assert all(len(c["series"]) in (0, 7) for c in cards.values())


class TestRecords:
    @patch("arete.api.analytics.db_connection")
    @patch("arete.api.analytics.best_effort_rows")
    def test_keeps_the_fastest_per_distance(self, mock_rows, _con, client):
        mock_rows.return_value = [
            (
                '[{"name": "1k", "elapsed_time": 240}, '
                '{"name": "5k", "elapsed_time": 1250}]',
                date(2026, 5, 1),
                "Morning Run",
            ),
            ('[{"name": "1k", "elapsed_time": 234}]', date(2026, 4, 20), "Fast Run"),
        ]
        records = client.get("/analytics/records?sport=running").json()["records"]
        one_k = next(r for r in records if r["name"] == "1k")
        assert one_k["time_sec"] == 234
        assert one_k["activity_name"] == "Fast Run"
        assert one_k["time_display"] == "3:54"

    @patch("arete.api.analytics.db_connection")
    @patch("arete.api.analytics.best_effort_rows")
    def test_long_efforts_display_hours(self, mock_rows, _con, client):
        mock_rows.return_value = [
            (
                '[{"name": "Half-Marathon", "elapsed_time": 5535}]',
                date(2026, 5, 1),
                "Semi",
            )
        ]
        record = client.get("/analytics/records").json()["records"][0]
        assert record["time_display"] == "1:32:15"

    @patch("arete.api.analytics.db_connection")
    @patch("arete.api.analytics.best_effort_rows", return_value=[])
    def test_no_records(self, _rows, _con, client):
        assert client.get("/analytics/records").json() == {"records": []}


class TestSessionUpdate:
    @patch("arete.api.analytics.connect")
    def test_update_rpe_and_notes(self, mock_connect, client):
        mock_conn = mock_connect.return_value
        resp = client.patch(
            "/analytics/sessions/42", json={"rpe": 7, "notes": "Felt good"}
        )
        assert resp.status_code == 200
        assert resp.json()["success"] is True
        mock_conn.execute.assert_called_once()

    @patch("arete.api.analytics.connect")
    def test_update_empty_body(self, mock_connect, client):
        mock_conn = mock_connect.return_value
        resp = client.patch("/analytics/sessions/42", json={})
        assert resp.status_code == 200
        mock_conn.execute.assert_not_called()


class TestListSessions:
    @patch("arete.api.analytics.db_connection")
    def test_returns_sessions(self, mock_db, client):
        con = mock_db.return_value.__enter__.return_value
        con.execute.return_value.fetchall.return_value = [
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
        sessions = client.get("/analytics/sessions").json()["sessions"]
        assert sessions[0]["name"] == "Morning Run"
        assert sessions[0]["pace_display"] == "5:20 /km"


class TestRemovedEndpoints:
    @pytest.mark.parametrize(
        "path",
        [
            "/analytics/volume",
            "/analytics/training-load",
            "/analytics/pace",
            "/analytics/hr-zones",
            "/analytics/sport-distribution",
            "/analytics/best-efforts",
            "/analytics/cardiac-efficiency",
            "/analytics/hr-pace-scatter",
            "/analytics/hr-drift",
        ],
    )
    def test_per_card_endpoints_are_gone(self, client, path):
        assert client.get(path).status_code == 404
