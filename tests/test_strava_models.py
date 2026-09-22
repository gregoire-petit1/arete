"""Tests for Strava -> ActualSession mapping."""

from datetime import date, datetime

from arete.garmin.models import ActivitySource
from arete.strava.models import strava_activity_to_actual_session

SAMPLE_ACTIVITY = {
    "id": 123456789,
    "name": "Morning Run",
    "type": "Run",
    "sport_type": "Run",
    "start_date": "2026-05-10T08:00:00Z",
    "start_date_local": "2026-05-10T10:00:00Z",
    "elapsed_time": 3600,
    "moving_time": 3500,
    "distance": 10000.0,
    "total_elevation_gain": 120.5,
    "average_speed": 2.78,
    "max_speed": 4.5,
    "average_heartrate": 145.0,
    "max_heartrate": 172.0,
    "average_cadence": 82.0,
    "calories": 650,
    "start_latlng": [48.8566, 2.3522],
}


class TestStravaToActualSession:
    def test_basic_fields(self):
        session = strava_activity_to_actual_session(SAMPLE_ACTIVITY)
        assert session.source == ActivitySource.STRAVA
        assert session.garmin_activity_id == "123456789"
        assert session.sport == "run"
        assert session.duration_sec == 3600
        assert session.distance_m == 10000.0

    def test_heart_rate(self):
        session = strava_activity_to_actual_session(SAMPLE_ACTIVITY)
        assert session.avg_hr == 145
        assert session.max_hr == 172

    def test_speed(self):
        session = strava_activity_to_actual_session(SAMPLE_ACTIVITY)
        assert session.avg_speed_mps == 2.78
        assert session.max_speed_mps == 4.5

    def test_pace_computed(self):
        session = strava_activity_to_actual_session(SAMPLE_ACTIVITY)
        assert session.avg_pace_sec_km == 360

    def test_elevation(self):
        session = strava_activity_to_actual_session(SAMPLE_ACTIVITY)
        assert session.ascent_m == 120.5

    def test_gps(self):
        session = strava_activity_to_actual_session(SAMPLE_ACTIVITY)
        assert session.start_lat == 48.8566
        assert session.start_lon == 2.3522

    def test_running_cadence_doubled(self):
        session = strava_activity_to_actual_session(SAMPLE_ACTIVITY)
        assert session.avg_cadence == 164

    def test_cycling_cadence_not_doubled(self):
        activity = {**SAMPLE_ACTIVITY, "type": "Ride", "average_cadence": 90}
        session = strava_activity_to_actual_session(activity)
        assert session.avg_cadence == 90

    def test_missing_optional_fields(self):
        minimal = {
            "id": 1,
            "type": "Run",
            "start_date": "2026-05-10T08:00:00Z",
            "start_date_local": "2026-05-10T10:00:00Z",
            "elapsed_time": 1800,
            "distance": 5000,
        }
        session = strava_activity_to_actual_session(minimal)
        assert session.avg_hr is None
        assert session.start_lat is None
        assert session.calories is None

    def test_sport_type_mapping(self):
        for strava_type, expected in [
            ("Run", "run"),
            ("TrailRun", "trail_run"),
            ("Ride", "ride"),
            ("Swim", "swim"),
            ("Hike", "hike"),
            ("Walk", "walk"),
            ("WeightTraining", "weight_training"),
        ]:
            activity = {**SAMPLE_ACTIVITY, "type": strava_type}
            session = strava_activity_to_actual_session(activity)
            assert session.sport == expected, f"{strava_type} -> {session.sport}"


def test_maps_detail_fields():
    activity = {
        "id": 1,
        "type": "Run",
        "start_date_local": "2026-05-10T07:30:00",
        "elapsed_time": 3600,
        "distance": 10000,
        "name": "Morning Run",
        "description": "Easy jog in the park",
        "moving_time": 3400,
        "suffer_score": 78,
        "workout_type": 3,
        "calories": 450,
        "device_name": "Garmin FR 265",
        "average_watts": None,
        "weighted_average_watts": None,
        "laps": [{"elapsed_time": 300}],
        "splits_metric": [{"distance": 1000, "average_speed": 2.78}],
        "best_efforts": [{"name": "1k", "elapsed_time": 240}],
    }
    session = strava_activity_to_actual_session(activity)
    assert session.name == "Morning Run"
    assert session.notes == "Easy jog in the park"
    assert session.moving_time_sec == 3400
    assert session.suffer_score == 78
    assert session.device_name == "Garmin FR 265"
    assert session.laps_json is not None
    assert "elapsed_time" in session.laps_json
    assert session.splits_json is not None
    assert session.best_efforts_json is not None


def test_maps_cycling_watts():
    activity = {
        "id": 2,
        "type": "Ride",
        "start_date_local": "2026-05-10T07:30:00",
        "elapsed_time": 3600,
        "distance": 30000,
        "average_watts": 200,
        "weighted_average_watts": 210,
    }
    session = strava_activity_to_actual_session(activity)
    assert session.avg_watts == 200
    assert session.weighted_avg_watts == 210


def test_maps_hr_zones():
    activity = {
        "id": 3,
        "type": "Run",
        "start_date_local": "2026-05-10T07:30:00",
        "elapsed_time": 3600,
        "distance": 10000,
    }
    hr_zones = {"z1": 120, "z2": 600, "z3": 1200, "z4": 300, "z5": 60}
    session = strava_activity_to_actual_session(activity, hr_zones=hr_zones)
    assert session.hr_zones_json is not None
    import json

    parsed = json.loads(session.hr_zones_json)
    assert parsed == hr_zones


def test_hr_zones_none_when_not_provided():
    activity = {
        "id": 4,
        "type": "Run",
        "start_date_local": "2026-05-10T07:30:00",
        "elapsed_time": 3600,
        "distance": 10000,
    }
    session = strava_activity_to_actual_session(activity)
    assert session.hr_zones_json is None


class TestLocalStartTime:
    """Start times must be naive local, or the Garmin/Strava merge misses.

    `find_overlapping_session` matches within 120 seconds. Strava returns
    `start_date_local` in the athlete's timezone but with a trailing "Z";
    parsing that as UTC produced an aware datetime, DuckDB shifted it into
    local time on insert, and a 07:17 run was stored as 09:17 — two hours
    away, so the same workout was saved twice and its load counted twice.
    """

    def test_the_bogus_trailing_z_is_not_a_timezone(self):
        from arete.strava.models import local_start_time

        started = local_start_time(
            {
                "start_date_local": "2026-09-21T07:17:22Z",
                "start_date": "2026-09-21T05:17:22Z",
            }
        )
        assert started == datetime(2026, 9, 21, 7, 17, 22)
        # Naive: an aware value is what DuckDB shifts.
        assert started.tzinfo is None

    def test_a_local_time_without_a_z_is_unchanged(self):
        from arete.strava.models import local_start_time

        assert local_start_time(
            {"start_date_local": "2026-09-21T07:17:22"}
        ) == datetime(2026, 9, 21, 7, 17, 22)

    def test_utc_is_shifted_by_the_offset_strava_ships(self):
        from arete.strava.models import local_start_time

        assert local_start_time(
            {"start_date": "2026-09-21T05:17:22Z", "utc_offset": 7200.0}
        ) == datetime(2026, 9, 21, 7, 17, 22)

    def test_utc_without_an_offset_stays_utc_rather_than_guessing(self):
        from arete.strava.models import local_start_time

        assert local_start_time({"start_date": "2026-09-21T05:17:22Z"}) == datetime(
            2026, 9, 21, 5, 17, 22
        )

    def test_the_mapped_session_carries_the_local_start(self):
        from arete.strava.models import strava_activity_to_actual_session

        session = strava_activity_to_actual_session(
            {
                "id": 20263557277,
                "type": "Run",
                "name": "Morning Run",
                "elapsed_time": 4332,
                "distance": 13237.4,
                "start_date_local": "2026-09-21T07:17:22Z",
                "start_date": "2026-09-21T05:17:22Z",
            }
        )
        assert session.start_time == datetime(2026, 9, 21, 7, 17, 22)
        assert session.date == date(2026, 9, 21)
