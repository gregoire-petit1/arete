"""The daily sync must fire once a day, even across a suspended machine."""

from __future__ import annotations

import json
from datetime import date, datetime
from unittest.mock import patch

import pytest

from arete import scheduler


class TestIsDue:
    def test_not_before_the_scheduled_hour(self):
        now = datetime(2026, 9, 20, 8, 59)
        assert scheduler.is_due(9, now, None) is False

    def test_due_at_the_hour_when_never_run(self):
        assert scheduler.is_due(9, datetime(2026, 9, 20, 9, 0), None) is True

    def test_done_today_is_not_due_again(self):
        now = datetime(2026, 9, 20, 18, 0)
        assert scheduler.is_due(9, now, date(2026, 9, 20)) is False

    def test_a_missed_day_runs_late_rather_than_never(self):
        # machine asleep at 9:00, back at 18:07 with yesterday as the last run
        now = datetime(2026, 9, 20, 18, 7)
        assert scheduler.is_due(9, now, date(2026, 9, 19)) is True

    def test_midnight_hour_is_supported(self):
        assert scheduler.is_due(0, datetime(2026, 9, 20, 0, 1), None) is True


class TestState:
    @pytest.fixture(autouse=True)
    def state_file(self, tmp_path, monkeypatch):
        path = tmp_path / "last_daily_sync.json"
        monkeypatch.setattr(scheduler, "state_path", lambda: path)
        return path

    def test_never_run_before(self, state_file):
        assert scheduler.last_run_date() is None

    def test_round_trip(self, state_file):
        scheduler.record_run(datetime(2026, 9, 20, 9, 0, 12))
        assert scheduler.last_run_date() == date(2026, 9, 20)
        assert json.loads(state_file.read_text())["ran_at"].startswith("2026-09-20")

    def test_corrupt_state_is_treated_as_never_run(self, state_file):
        state_file.write_text("{oops")
        assert scheduler.last_run_date() is None


class TestRunForever:
    @pytest.fixture(autouse=True)
    def state_file(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            scheduler, "state_path", lambda: tmp_path / "last_daily_sync.json"
        )

    @pytest.mark.anyio
    async def test_runs_once_then_waits(self):
        calls = []

        async def fake_sleep(_seconds):
            if len(calls) >= 1:  # one sync is enough for this test
                raise StopAsyncIteration

        with (
            patch.object(scheduler, "daily_sync", side_effect=lambda: calls.append(1)),
            patch("asyncio.sleep", side_effect=fake_sleep),
            patch.object(scheduler, "is_due", side_effect=[True, False]),
            pytest.raises(StopAsyncIteration),
        ):
            await scheduler.run_forever(9, tick_seconds=1)

        assert len(calls) == 1
        assert scheduler.last_run_date() == date.today()

    @pytest.fixture
    def anyio_backend(self):
        return "asyncio"


class TestStart:
    def test_disabled_without_env(self, monkeypatch):
        monkeypatch.delenv("ARETE_AUTO_SYNC_HOUR", raising=False)
        assert scheduler.start() is None


class TestDailySync:
    def test_reports_missing_connectors(self, tmp_path, monkeypatch):
        monkeypatch.setenv("ARETE_GARMIN_TOKENS_DIR", str(tmp_path / "none"))
        with patch("arete.api.strava._get_strava_tokens", return_value=None):
            status = scheduler.daily_sync()
        assert status == {"garmin": "no tokens", "strava": "not connected"}
