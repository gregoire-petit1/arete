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
    @pytest.fixture
    def anyio_backend(self):
        return "asyncio"

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
            patch.object(scheduler, "write_daily_briefing", return_value="rules"),
            patch("asyncio.sleep", side_effect=fake_sleep),
            patch.object(scheduler, "is_due", side_effect=[True, False]),
            pytest.raises(StopAsyncIteration),
        ):
            await scheduler.run_forever(9, tick_seconds=1)

        assert len(calls) == 1
        assert scheduler.last_run_date() == date.today()

    @pytest.mark.anyio
    async def test_the_briefing_is_written_after_the_sync_not_before(self):
        # It reads the data the sync just landed, so the order matters.
        order: list[str] = []

        async def fake_sleep(_seconds):
            if order:
                raise StopAsyncIteration

        with (
            patch.object(
                scheduler, "daily_sync", side_effect=lambda: order.append("sync")
            ),
            patch.object(
                scheduler,
                "write_daily_briefing",
                side_effect=lambda: order.append("briefing") or "agent",
            ),
            patch("asyncio.sleep", side_effect=fake_sleep),
            patch.object(scheduler, "is_due", side_effect=[True, False]),
            pytest.raises(StopAsyncIteration),
        ):
            await scheduler.run_forever(9, tick_seconds=1)

        assert order == ["sync", "briefing"]

    @pytest.mark.anyio
    async def test_a_failing_briefing_does_not_stop_the_loop(self):
        ticks = []

        async def fake_sleep(_seconds):
            ticks.append(1)
            raise StopAsyncIteration

        with (
            patch.object(scheduler, "daily_sync", return_value={}),
            patch(
                "arete.coaching.generate_briefing",
                side_effect=RuntimeError("model is away"),
            ),
            patch("arete.services.briefing.briefing_enabled", return_value=True),
            patch("asyncio.sleep", side_effect=fake_sleep),
            patch.object(scheduler, "is_due", side_effect=[True, False]),
            pytest.raises(StopAsyncIteration),
        ):
            await scheduler.run_forever(9, tick_seconds=1)

        # The loop reached its sleep, i.e. the failure was swallowed.
        assert ticks == [1]


class TestWriteDailyBriefing:
    def test_disabled_is_reported_not_run(self):
        with patch("arete.services.briefing.briefing_enabled", return_value=False):
            assert scheduler.write_daily_briefing() == "disabled"

    def test_failure_is_reported_not_raised(self):
        with (
            patch("arete.services.briefing.briefing_enabled", return_value=True),
            patch(
                "arete.services.coaching_repository.BriefingRepository.get_for_day",
                return_value=None,
            ),
            patch(
                "arete.coaching.generate_briefing",
                side_effect=RuntimeError("boom"),
            ),
        ):
            assert scheduler.write_daily_briefing().startswith("failed:")

    def _existing(self, trigger):
        from arete.services.coaching_repository import Briefing

        return Briefing(
            id=1,
            date=date.today(),
            text="Déjà écrit.",
            priority="info",
            source="agent",
            status="ok",
            error=None,
            trigger=trigger,
            created_at=None,
        )

    def test_a_second_scheduler_run_keeps_its_briefing(self):
        with (
            patch("arete.services.briefing.briefing_enabled", return_value=True),
            patch(
                "arete.services.coaching_repository.BriefingRepository.get_for_day",
                return_value=self._existing("scheduler"),
            ),
            patch("arete.coaching.generate_briefing") as generate,
        ):
            assert scheduler.write_daily_briefing() == "agent"
        generate.assert_not_called()

    def test_a_briefing_written_before_the_sync_is_rewritten(self):
        fresh = self._existing("scheduler")
        with (
            patch("arete.services.briefing.briefing_enabled", return_value=True),
            patch(
                "arete.services.coaching_repository.BriefingRepository.get_for_day",
                return_value=self._existing("api"),
            ),
            patch("arete.coaching.generate_briefing", return_value=fresh) as generate,
        ):
            scheduler.write_daily_briefing()
        generate.assert_called_once_with(trigger="scheduler")


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

    def test_status_is_kept_not_discarded(self, tmp_path, monkeypatch):
        # run_forever ignores the return value; the coach needs to know what
        # the last sync actually did before briefing on the day's data.
        monkeypatch.setenv("ARETE_GARMIN_TOKENS_DIR", str(tmp_path / "none"))
        with patch("arete.api.strava._get_strava_tokens", return_value=None):
            status = scheduler.daily_sync()
        assert scheduler.last_status() == status

    def test_last_status_is_a_copy(self):
        # Callers must not be able to edit the scheduler's record.
        snapshot = scheduler.last_status()
        snapshot["garmin"] = "tampered"
        assert scheduler.last_status().get("garmin") != "tampered"


class TestSyncStatusEndpoint:
    def test_reports_schedule_and_last_run(self, client, monkeypatch):
        monkeypatch.setenv("ARETE_AUTO_SYNC_HOUR", "9")
        with patch.object(scheduler, "last_run_date", return_value=date(2026, 9, 20)):
            body = client.get("/sync/status").json()
        assert body["scheduled_hour"] == 9
        assert body["last_run"] == "2026-09-20"
        assert isinstance(body["sources"], dict)

    def test_never_run_reports_null(self, client, monkeypatch):
        monkeypatch.delenv("ARETE_AUTO_SYNC_HOUR", raising=False)
        with patch.object(scheduler, "last_run_date", return_value=None):
            body = client.get("/sync/status").json()
        assert body["scheduled_hour"] is None
        assert body["last_run"] is None
