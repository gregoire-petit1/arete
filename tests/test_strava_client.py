"""Tests for Strava OAuth client."""

from __future__ import annotations
import time
from unittest.mock import patch, MagicMock
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
