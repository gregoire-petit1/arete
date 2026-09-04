"""Tests for Garmin sync module."""

from __future__ import annotations

from datetime import date, datetime
from unittest.mock import MagicMock, patch

import pytest

from arete.garmin.client import GarminAuthError
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
    """Tests for GarminSyncClient (Garmin access mocked through GarminClient)."""

    def _client(self, **attrs) -> GarminSyncClient:
        garmin = MagicMock()
        for k, v in attrs.items():
            setattr(garmin, k, v)
        return GarminSyncClient(client=garmin)

    def test_is_authenticated_delegates(self):
        client = self._client()
        client.client.is_authenticated.return_value = True
        assert client.is_authenticated() is True
        client.client.is_authenticated.return_value = False
        assert client.is_authenticated() is False

    def test_login_success(self):
        client = self._client()
        client.client.login.return_value = "ok"
        assert client.login(email="test@example.com", password="password123") == "ok"
        client.client.login.assert_called_once_with("test@example.com", "password123")

    def test_login_needs_mfa(self):
        client = self._client()
        client.client.login.return_value = "needs_mfa"
        assert client.login(email="a@b.c", password="x") == "needs_mfa"

    def test_login_no_credentials(self, monkeypatch):
        monkeypatch.delenv("GARMIN_EMAIL", raising=False)
        monkeypatch.delenv("GARMIN_PASSWORD", raising=False)
        with pytest.raises(ValueError, match="Garmin credentials required"):
            self._client().login()

    def test_login_from_env(self, monkeypatch):
        monkeypatch.setenv("GARMIN_EMAIL", "env@example.com")
        monkeypatch.setenv("GARMIN_PASSWORD", "envpass")
        client = self._client()
        client.client.login.return_value = "ok"
        client.login()
        client.client.login.assert_called_once_with("env@example.com", "envpass")

    def test_logout_delegates(self):
        client = self._client()
        client.logout()
        client.client.logout.assert_called_once()

    def test_get_activities(self):
        client = self._client()
        client._last_request_time = 0.0
        client.client.activities.return_value = [
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
        with patch("arete.garmin.sync.time.sleep"):
            activities = client.get_activities(
                start_date=date(2025, 12, 1), end_date=date(2025, 12, 5), limit=10
            )
        assert [a.activity_id for a in activities] == [1, 2]
        client.client.activities.assert_called_once_with(
            date(2025, 12, 1), date(2025, 12, 5)
        )

    def test_get_activities_respects_limit_and_skips_garbage(self):
        client = self._client()
        client.client.activities.return_value = [
            "not-a-dict",
            {"activityId": 1, "startTimeLocal": "2025-12-01T08:00:00", "duration": 1},
            {"activityId": 2, "startTimeLocal": "2025-12-02T08:00:00", "duration": 1},
        ]
        with patch("arete.garmin.sync.time.sleep"):
            activities = client.get_activities(limit=2)
        assert [a.activity_id for a in activities] == [1]

    def test_download_fit_file_writes_and_caches(self, tmp_path):
        client = self._client()
        client.client.download_fit.return_value = b"FITDATA"
        with patch("arete.garmin.sync.time.sleep"):
            path = client.download_fit_file(42, output_dir=tmp_path)
            assert path == tmp_path / "42.fit"
            assert path.read_bytes() == b"FITDATA"
            # second call: served from disk, no API call
            client.download_fit_file(42, output_dir=tmp_path)
        client.client.download_fit.assert_called_once()

    def test_sync_activities_reports_auth_error(self):
        client = self._client()
        client.client.activities.side_effect = GarminAuthError("no tokens")
        client._repository = MagicMock()
        client._repository.list_actual_sessions.return_value = []
        with patch("arete.garmin.sync.time.sleep"):
            result = client.sync_activities(start_date=date(2025, 12, 1))
        assert result.success is False
        assert "no tokens" in result.errors[0]


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
