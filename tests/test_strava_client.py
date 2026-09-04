"""Tests for Strava OAuth client."""

from __future__ import annotations

import time
from unittest.mock import MagicMock, patch

import pytest

from arete.strava.client import StravaClient


@pytest.fixture
def client():
    return StravaClient(
        client_id="test_id",
        client_secret="test_secret",
        redirect_uri="http://localhost:8000/strava/callback",
    )


class TestAuthorizeUrl:
    def test_contains_client_id(self, client):
        url = client.get_authorize_url()
        assert "client_id=test_id" in url

    def test_contains_redirect_uri(self, client):
        url = client.get_authorize_url()
        assert "redirect_uri=" in url

    def test_contains_scope(self, client):
        url = client.get_authorize_url()
        assert "activity%3Aread_all" in url

    def test_contains_state(self, client):
        url = client.get_authorize_url(state="abc123")
        assert "state=abc123" in url


class TestTokenExchange:
    @patch("arete.strava.client.httpx.post")
    def test_exchange_code_returns_tokens(self, mock_post, client):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "access_token": "at_123",
                "refresh_token": "rt_456",
                "expires_at": 9999999999,
                "athlete": {"id": 42, "firstname": "Greg", "lastname": "P"},
            },
        )
        tokens = client.exchange_code("auth_code_xyz")
        assert tokens["access_token"] == "at_123"
        assert tokens["refresh_token"] == "rt_456"
        assert tokens["athlete"]["id"] == 42

    @patch("arete.strava.client.httpx.post")
    def test_exchange_code_raises_on_error(self, mock_post, client):
        mock_post.return_value = MagicMock(
            status_code=400,
            text="Bad Request",
            json=lambda: {"message": "Bad Request"},
        )
        with pytest.raises(ValueError):
            client.exchange_code("bad_code")


class TestTokenRefresh:
    @patch("arete.strava.client.httpx.post")
    def test_refresh_returns_new_tokens(self, mock_post, client):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "access_token": "new_at",
                "refresh_token": "new_rt",
                "expires_at": 9999999999,
            },
        )
        tokens = client.refresh_token("old_rt")
        assert tokens["access_token"] == "new_at"
        assert tokens["refresh_token"] == "new_rt"


class TestFetchActivities:
    @patch("arete.strava.client.httpx.get")
    def test_fetch_single_page(self, mock_get, client):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [
                {
                    "id": 1,
                    "name": "Morning Run",
                    "type": "Run",
                    "start_date": "2026-05-10T08:00:00Z",
                    "distance": 10000,
                    "moving_time": 3600,
                    "total_elevation_gain": 50,
                },
            ],
        )
        activities = client.fetch_activities("at_123", after=0)
        assert len(activities) == 1
        assert activities[0]["id"] == 1

    @patch("arete.strava.client.httpx.get")
    def test_fetch_empty(self, mock_get, client):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [],
        )
        activities = client.fetch_activities("at_123", after=0)
        assert activities == []


class TestNeedsRefresh:
    def test_expired_token(self, client):
        assert client.needs_refresh(int(time.time()) - 100) is True

    def test_valid_token(self, client):
        assert client.needs_refresh(int(time.time()) + 600) is False

    def test_within_margin(self, client):
        assert client.needs_refresh(int(time.time()) + 240) is True


class TestFetchActivityDetail:
    @patch("arete.strava.client.httpx.get")
    def test_fetches_detail_with_all_fields(self, mock_get, client):
        detail = {
            "id": 123,
            "name": "Morning Run",
            "description": "Easy recovery",
            "calories": 450,
            "device_name": "Garmin FR 265",
            "laps": [{"elapsed_time": 300, "distance": 1000}],
            "splits_metric": [{"average_speed": 3.5, "distance": 1000}],
            "best_efforts": [{"name": "1k", "elapsed_time": 240}],
            "suffer_score": 78,
            "workout_type": 1,
            "average_watts": None,
            "weighted_average_watts": None,
        }
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: detail,
        )
        result = client.fetch_activity_detail("token123", 123)
        assert result["name"] == "Morning Run"
        assert result["description"] == "Easy recovery"
        assert result["laps"] == detail["laps"]
        mock_get.assert_called_once()

    @patch("arete.strava.client.httpx.get")
    def test_detail_returns_none_on_404(self, mock_get, client):
        mock_get.return_value = MagicMock(status_code=404)
        result = client.fetch_activity_detail("token123", 999)
        assert result is None


class TestFetchActivityZones:
    @patch("arete.strava.client.httpx.get")
    def test_fetches_hr_zones(self, mock_get, client):
        zones_response = [
            {
                "type": "heartrate",
                "distribution_buckets": [
                    {"min": 0, "max": 115, "time": 120},
                    {"min": 115, "max": 152, "time": 600},
                    {"min": 152, "max": 171, "time": 1200},
                    {"min": 171, "max": 190, "time": 300},
                    {"min": 190, "max": -1, "time": 60},
                ],
            }
        ]
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: zones_response,
        )
        result = client.fetch_activity_zones("token123", 123)
        assert result == {"z1": 120, "z2": 600, "z3": 1200, "z4": 300, "z5": 60}
        mock_get.assert_called_once()
        assert "/zones" in mock_get.call_args[0][0]

    @patch("arete.strava.client.httpx.get")
    def test_zones_returns_none_on_404(self, mock_get, client):
        mock_get.return_value = MagicMock(status_code=404)
        result = client.fetch_activity_zones("token123", 999)
        assert result is None

    @patch("arete.strava.client.httpx.get")
    def test_zones_returns_none_no_hr_type(self, mock_get, client):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [{"type": "power", "distribution_buckets": []}],
        )
        result = client.fetch_activity_zones("token123", 123)
        assert result is None

    @patch("arete.strava.client.httpx.get")
    def test_zones_returns_none_on_server_error(self, mock_get, client):
        mock_get.return_value = MagicMock(status_code=500)
        result = client.fetch_activity_zones("token123", 123)
        assert result is None
