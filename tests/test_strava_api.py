"""Tests for /strava API endpoints."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from arete.api.strava import router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestStravaAuthorize:
    @patch.dict(
        "os.environ",
        {
            "STRAVA_CLIENT_ID": "12345",
            "STRAVA_CLIENT_SECRET": "secret",
            "STRAVA_REDIRECT_URI": "http://localhost:8000/strava/callback",
        },
    )
    def test_returns_authorize_url(self, client):
        resp = client.get("/strava/authorize")
        assert resp.status_code == 200
        data = resp.json()
        assert "url" in data
        assert "strava.com/oauth/authorize" in data["url"]
        assert "client_id=12345" in data["url"]


class TestStravaStatus:
    @patch("arete.api.strava._get_strava_tokens")
    def test_disconnected(self, mock_tokens, client):
        mock_tokens.return_value = None
        resp = client.get("/strava/status")
        assert resp.status_code == 200
        assert resp.json()["connected"] is False

    @patch("arete.api.strava._get_strava_tokens")
    def test_connected(self, mock_tokens, client):
        mock_tokens.return_value = {
            "athlete_id": 42,
            "athlete_name": "Greg",
            "expires_at": 9999999999,
        }
        resp = client.get("/strava/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is True
        assert data["athlete_name"] == "Greg"


class TestStravaDisconnect:
    @patch("arete.api.strava._delete_strava_tokens")
    def test_disconnect(self, mock_delete, client):
        resp = client.delete("/strava/disconnect")
        assert resp.status_code == 200
        mock_delete.assert_called_once()
