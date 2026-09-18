"""The threshold Garmin measured, adopted only when it is newer."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

from arete.garmin.threshold import (
    ThresholdReading,
    parse_threshold,
    refresh_threshold,
)

GARMIN_PAYLOAD = {
    "userProfilePK": 1,
    "calendarDate": "2026-09-15T08:36:06.872",
    "speed": 0.3888878,  # tenths of a metre per second
    "heartRate": 176,
    "heartRateCycling": None,
}


class TestParse:
    def test_reads_heart_rate_speed_and_date(self):
        reading = parse_threshold(GARMIN_PAYLOAD)
        assert reading == ThresholdReading(176, 257, date(2026, 9, 15))

    def test_speed_becomes_seconds_per_kilometre(self):
        # 0.3888878 * 10 = 3.889 m/s = 4:17 per km
        assert parse_threshold(GARMIN_PAYLOAD).pace_sec_km == 4 * 60 + 17

    def test_absurd_speed_is_dropped_but_heart_rate_kept(self):
        reading = parse_threshold({**GARMIN_PAYLOAD, "speed": 0.0001})
        assert reading.heart_rate == 176
        assert reading.pace_sec_km is None

    def test_nothing_measured(self):
        assert parse_threshold(None) is None
        assert parse_threshold({}) is None
        assert parse_threshold({"heartRate": 0, "speed": None}) is None

    def test_date_may_be_missing(self):
        reading = parse_threshold({"heartRate": 176, "speed": 0.38, "calendarDate": ""})
        assert reading.measured_on is None


def client_returning(payload):
    client = MagicMock()
    client.lactate_threshold.return_value = payload
    return client


class TestRefresh:
    def settings(self, **overrides):
        base = {
            "user_id": 1,
            "display_name": "Athlète",
            "email": None,
            "timezone": "Europe/Paris",
            "weekly_training_goal": 6,
            "rest_day_preference": ["monday"],
            "fatigue_threshold": 85,
            "fitness_goal": "build",
            "notifications_enabled": True,
            "theme": "dark",
            "exercise_abbreviations": {},
            "weekly_volume_target_kg": 20000,
            "lthr": None,
            "max_hr": None,
            "threshold_pace_sec_km": None,
            "lthr_measured_on": None,
        }
        base.update(overrides)
        return base

    def test_first_measurement_is_stored(self):
        with (
            patch(
                "arete.garmin.threshold.get_user_settings", return_value=self.settings()
            ),
            patch("arete.garmin.threshold.upsert_user_settings") as upsert,
        ):
            out = refresh_threshold(client_returning(GARMIN_PAYLOAD))
        assert out["updated"] is True
        assert out["lthr"] == 176
        saved = upsert.call_args.kwargs
        assert saved["lthr"] == 176
        assert saved["threshold_pace_sec_km"] == 257
        assert saved["lthr_measured_on"] == date(2026, 9, 15)

    def test_same_values_change_nothing(self):
        stored = self.settings(
            lthr=176, threshold_pace_sec_km=257, lthr_measured_on=date(2026, 9, 15)
        )
        with (
            patch("arete.garmin.threshold.get_user_settings", return_value=stored),
            patch("arete.garmin.threshold.upsert_user_settings") as upsert,
        ):
            out = refresh_threshold(client_returning(GARMIN_PAYLOAD))
        assert out == {
            "updated": False,
            "reason": "unchanged",
            "lthr": 176,
            "measured_on": "2026-09-15",
        }
        upsert.assert_not_called()

    def test_same_values_still_record_the_test_date(self):
        stored = self.settings(lthr=176, threshold_pace_sec_km=257)
        with (
            patch("arete.garmin.threshold.get_user_settings", return_value=stored),
            patch("arete.garmin.threshold.upsert_user_settings") as upsert,
        ):
            out = refresh_threshold(client_returning(GARMIN_PAYLOAD))
        assert out["reason"] == "dated"
        assert out["updated"] is False
        assert upsert.call_args.kwargs["lthr_measured_on"] == date(2026, 9, 15)

    def test_an_older_test_never_overwrites(self):
        stored = self.settings(lthr=180, lthr_measured_on=date(2026, 10, 1))
        with (
            patch("arete.garmin.threshold.get_user_settings", return_value=stored),
            patch("arete.garmin.threshold.upsert_user_settings") as upsert,
        ):
            out = refresh_threshold(client_returning(GARMIN_PAYLOAD))
        assert out["reason"] == "older"
        upsert.assert_not_called()

    def test_a_newer_test_replaces_the_manual_value(self):
        stored = self.settings(lthr=170, lthr_measured_on=date(2026, 6, 1))
        with (
            patch("arete.garmin.threshold.get_user_settings", return_value=stored),
            patch("arete.garmin.threshold.upsert_user_settings") as upsert,
        ):
            out = refresh_threshold(client_returning(GARMIN_PAYLOAD))
        assert out["updated"] is True
        assert out["previous_lthr"] == 170
        assert upsert.call_args.kwargs["lthr"] == 176

    def test_garmin_failure_does_not_raise(self):
        client = MagicMock()
        client.lactate_threshold.side_effect = RuntimeError("503")
        with (
            patch(
                "arete.garmin.threshold.get_user_settings", return_value=self.settings()
            ),
            patch("arete.garmin.threshold.upsert_user_settings") as upsert,
        ):
            out = refresh_threshold(client)
        assert out == {"updated": False, "reason": "unavailable"}
        upsert.assert_not_called()

    def test_no_threshold_measured_yet(self):
        with (
            patch(
                "arete.garmin.threshold.get_user_settings", return_value=self.settings()
            ),
            patch("arete.garmin.threshold.upsert_user_settings") as upsert,
        ):
            out = refresh_threshold(client_returning({}))
        assert out["reason"] == "not_measured"
        upsert.assert_not_called()
