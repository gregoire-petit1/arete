"""Tests for the daily sync scheduler helpers."""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from arete import scheduler


class TestSecondsUntil:
    def test_later_today(self):
        now = datetime(2026, 9, 4, 20, 0, 0)
        assert scheduler.seconds_until(23, now) == 3 * 3600

    def test_wraps_to_tomorrow(self):
        now = datetime(2026, 9, 4, 3, 30, 0)
        assert scheduler.seconds_until(3, now) == 23.5 * 3600


class TestStart:
    def test_disabled_without_env(self, monkeypatch):
        monkeypatch.delenv("ARETE_AUTO_SYNC_HOUR", raising=False)
        assert scheduler.start() is None


class TestNightlySync:
    def test_reports_missing_connectors(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ARETE_GARMIN_TOKENS_DIR", str(tmp_path / "none"))
        with patch("arete.api.strava._get_strava_tokens", return_value=None):
            status = scheduler.daily_sync()
        assert status == {"garmin": "no tokens", "strava": "not connected"}
