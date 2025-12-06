"""Tests for Garmin sync module."""

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from arete.garmin.sync import (
    GarminActivity,
    GarminSyncClient,
    SyncResult,
)


class TestGarminActivity:
    """Tests for GarminActivity dataclass."""

    def test_from_api_response(self):
        """Test parsing from Garmin API response."""
        api_data = {
            "activityId": 12345678,
            "activityName": "Morning Run",
            "activityType": {"typeKey": "running"},
            "startTimeLocal": "2025-12-01T07:30:00",
            "duration": 3600.0,
            "distance": 10000.0,
            "averageHR": 145,
            "maxHR": 165,
            "calories": 650,
            "averageSpeed": 2.78,
            "maxSpeed": 3.5,
            "elevationGain": 120.0,
            "elevationLoss": 115.0,
            "averageRunningCadenceInStepsPerMinute": 175,
            "maxRunningCadenceInStepsPerMinute": 185,
        }

        activity = GarminActivity.from_api_response(api_data)

        assert activity.activity_id == 12345678
        assert activity.activity_name == "Morning Run"
        assert activity.activity_type == "running"
        assert activity.duration_sec == 3600
        assert activity.distance_m == 10000.0
        assert activity.avg_hr == 145
        assert activity.max_hr == 165
        assert activity.calories == 650
        assert activity.avg_cadence == 175

    def test_from_api_response_minimal(self):
        """Test parsing with minimal data."""
        api_data = {
            "activityId": 99999,
            "duration": 1800,
        }

        activity = GarminActivity.from_api_response(api_data)

        assert activity.activity_id == 99999
        assert activity.activity_name == ""
        assert activity.activity_type == "unknown"
        assert activity.duration_sec == 1800
        assert activity.distance_m is None
        assert activity.avg_hr is None

    def test_to_actual_session(self):
        """Test conversion to ActualSession."""
        activity = GarminActivity(
            activity_id=12345,
            activity_name="Test Run",
            activity_type="running",
            start_time=datetime(2025, 12, 1, 7, 30),
            duration_sec=3600,
            distance_m=10000.0,
            avg_hr=145,
            max_hr=165,
            calories=650,
            avg_speed_mps=2.78,
            max_speed_mps=3.5,
            ascent_m=120.0,
            descent_m=115.0,
            avg_cadence=175,
            max_cadence=185,
        )

        session = activity.to_actual_session()

        assert session.date == date(2025, 12, 1)
        assert session.sport == "running"
        assert session.duration_sec == 3600
        assert session.distance_m == 10000.0
        assert session.avg_hr == 145
        assert session.garmin_activity_id == "12345"

    def test_map_activity_type(self):
        """Test activity type mapping."""
        test_cases = [
            ("running", "running"),
            ("trail_running", "running"),
            ("cycling", "cycling"),
            ("indoor_cycling", "cycling"),
            ("swimming", "swimming"),
            ("lap_swimming", "swimming"),
            ("strength_training", "strength"),
            ("hiking", "hiking"),
            ("unknown_type", "other"),
        ]

        for garmin_type, expected_sport in test_cases:
            activity = GarminActivity(
                activity_id=1,
                activity_name="Test",
                activity_type=garmin_type,
                start_time=datetime.now(),
                duration_sec=1000,
                distance_m=None,
                avg_hr=None,
                max_hr=None,
                calories=None,
                avg_speed_mps=None,
                max_speed_mps=None,
                ascent_m=None,
                descent_m=None,
                avg_cadence=None,
                max_cadence=None,
            )
            assert activity._map_activity_type() == expected_sport


class TestGarminSyncClient:
    """Tests for GarminSyncClient."""

    def test_init_default_token_dir(self):
        """Test default token directory."""
        client = GarminSyncClient()
        assert client.token_dir == Path.home() / ".garth"

    def test_init_custom_token_dir(self, tmp_path):
        """Test custom token directory."""
        client = GarminSyncClient(token_dir=tmp_path / "tokens")
        assert client.token_dir == tmp_path / "tokens"
        assert client.token_dir.exists()

    @patch("arete.garmin.sync.garth")
    def test_is_authenticated_success(self, mock_garth, tmp_path):
        """Test successful authentication check."""
        client = GarminSyncClient(token_dir=tmp_path)
        mock_garth.resume.return_value = None

        assert client.is_authenticated() is True
        mock_garth.resume.assert_called_once()

    @patch("arete.garmin.sync.garth")
    def test_is_authenticated_failure(self, mock_garth, tmp_path):
        """Test failed authentication check."""
        client = GarminSyncClient(token_dir=tmp_path)
        mock_garth.resume.side_effect = Exception("No tokens")

        assert client.is_authenticated() is False

    @patch("arete.garmin.sync.garth")
    def test_login_success(self, mock_garth, tmp_path):
        """Test successful login."""
        client = GarminSyncClient(token_dir=tmp_path)

        result = client.login(email="test@example.com", password="password123")

        assert result is True
        mock_garth.login.assert_called_once_with("test@example.com", "password123")
        mock_garth.save.assert_called_once()

    def test_login_no_credentials(self, tmp_path, monkeypatch):
        """Test login without credentials."""
        monkeypatch.delenv("GARMIN_EMAIL", raising=False)
        monkeypatch.delenv("GARMIN_PASSWORD", raising=False)

        client = GarminSyncClient(token_dir=tmp_path)

        with pytest.raises(ValueError, match="Garmin credentials required"):
            client.login()

    @patch("arete.garmin.sync.garth")
    def test_login_from_env(self, mock_garth, tmp_path, monkeypatch):
        """Test login using environment variables."""
        monkeypatch.setenv("GARMIN_EMAIL", "env@example.com")
        monkeypatch.setenv("GARMIN_PASSWORD", "envpass")

        client = GarminSyncClient(token_dir=tmp_path)
        client.login()

        mock_garth.login.assert_called_once_with("env@example.com", "envpass")

    def test_logout(self, tmp_path):
        """Test logout clears tokens."""
        client = GarminSyncClient(token_dir=tmp_path)

        # Create fake token files
        (tmp_path / "oauth1_token.json").write_text("{}")
        (tmp_path / "oauth2_token.json").write_text("{}")

        client.logout()

        assert not (tmp_path / "oauth1_token.json").exists()
        assert not (tmp_path / "oauth2_token.json").exists()

    @patch("arete.garmin.sync.garth")
    def test_get_activities(self, mock_garth, tmp_path):
        """Test fetching activities."""
        client = GarminSyncClient(token_dir=tmp_path)
        client._authenticated = True

        mock_garth.connectapi.return_value = [
            {
                "activityId": 1,
                "activityName": "Run 1",
                "activityType": {"typeKey": "running"},
                "startTimeLocal": "2025-12-01T08:00:00",
                "duration": 3600,
            },
            {
                "activityId": 2,
                "activityName": "Run 2",
                "activityType": {"typeKey": "running"},
                "startTimeLocal": "2025-12-02T08:00:00",
                "duration": 2700,
            },
        ]

        activities = client.get_activities(limit=10)

        assert len(activities) == 2
        assert activities[0].activity_id == 1
        assert activities[1].activity_id == 2

    @patch("arete.garmin.sync.garth")
    def test_get_activities_with_date_filter(self, mock_garth, tmp_path):
        """Test filtering activities by date."""
        client = GarminSyncClient(token_dir=tmp_path)
        client._authenticated = True

        mock_garth.connectapi.return_value = [
            {
                "activityId": 1,
                "startTimeLocal": "2025-11-15T08:00:00",
                "duration": 3600,
            },
            {
                "activityId": 2,
                "startTimeLocal": "2025-12-01T08:00:00",
                "duration": 2700,
            },
            {
                "activityId": 3,
                "startTimeLocal": "2025-12-10T08:00:00",
                "duration": 1800,
            },
        ]

        activities = client.get_activities(start_date=date(2025, 12, 1), end_date=date(2025, 12, 5))

        # Only activity 2 should match
        assert len(activities) == 1
        assert activities[0].activity_id == 2


class TestSyncResult:
    """Tests for SyncResult dataclass."""

    def test_default_values(self):
        """Test default SyncResult values."""
        result = SyncResult(success=True)

        assert result.success is True
        assert result.activities_synced == 0
        assert result.activities_skipped == 0
        assert result.errors == []
        assert result.last_activity_date is None

    def test_with_values(self):
        """Test SyncResult with values."""
        result = SyncResult(
            success=True,
            activities_synced=5,
            activities_skipped=2,
            errors=["Error 1"],
            last_activity_date=date(2025, 12, 1),
        )

        assert result.activities_synced == 5
        assert result.activities_skipped == 2
        assert len(result.errors) == 1
        assert result.last_activity_date == date(2025, 12, 1)
