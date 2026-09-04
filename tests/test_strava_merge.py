"""Garmin/Strava merge rules and the overlap lookup on a real temp DB."""

from __future__ import annotations

from datetime import datetime

from arete.garmin.models import ActivitySource, ActualSession
from arete.garmin.repository import GarminRepository
from arete.strava.merge import garmin_takeover, strava_extras


def _session(source: ActivitySource, start: datetime, **kw) -> ActualSession:
    return ActualSession(
        date=start.date(),
        sport="running",
        duration_sec=3600,
        start_time=start,
        source=source,
        **kw,
    )


class TestMergeRules:
    def test_strava_extras_fill_gaps_and_best_efforts(self):
        garmin = _session(
            ActivitySource.GARMIN_CONNECT,
            datetime(2026, 6, 1, 8),
            name="Course",
            hr_zones_json="{}",
        )
        strava = _session(
            ActivitySource.STRAVA,
            datetime(2026, 6, 1, 8, 1),
            garmin_activity_id="s1",
            name="Morning Run",
            suffer_score=80,
            best_efforts_json="[...]",
            hr_zones_json='{"z1": 1}',
        )
        fields = strava_extras(garmin, strava)
        assert fields["strava_activity_id"] == "s1"
        assert fields["suffer_score"] == 80
        assert fields["best_efforts_json"] == "[...]"
        assert "name" not in fields  # Garmin name wins
        assert "hr_zones_json" not in fields  # Garmin zones win

    def test_garmin_takeover_changes_provenance(self):
        garmin = _session(
            ActivitySource.GARMIN_CONNECT,
            datetime(2026, 6, 1, 8),
            garmin_activity_id="g1",
            session_type="running",
            hr_zones_json="{}",
        )
        fields = garmin_takeover(garmin)
        assert fields["source"] == "garmin_connect"
        assert fields["garmin_activity_id"] == "g1"
        assert fields["session_type"] == "running"


class TestOverlapLookup:
    def test_finds_twin_within_two_minutes(self):
        repo = GarminRepository()
        start = datetime(2031, 3, 3, 7, 0)
        sid = repo.create_actual_session(
            _session(ActivitySource.GARMIN_CONNECT, start, garmin_activity_id="twin")
        )
        try:
            hit = repo.find_overlapping_session(datetime(2031, 3, 3, 7, 1, 30), 3600)
            assert hit is not None and hit.id == sid
            assert (
                repo.find_overlapping_session(datetime(2031, 3, 3, 7, 10), 3600) is None
            )
            assert repo.find_overlapping_session(None, 3600) is None
        finally:
            repo.delete_actual_session(sid)

    def test_known_strava_ids_include_merged(self):
        repo = GarminRepository()
        start = datetime(2031, 4, 4, 7, 0)
        sid = repo.create_actual_session(
            _session(ActivitySource.GARMIN_CONNECT, start, garmin_activity_id="g9")
        )
        sid2 = repo.create_actual_session(
            _session(
                ActivitySource.STRAVA, datetime(2031, 4, 5, 7), garmin_activity_id="s5"
            )
        )
        try:
            repo.update_actual_session_fields(sid, strava_activity_id="s9")
            ids = repo.known_strava_ids()
            assert {"s9", "s5"} <= ids and "g9" not in ids
        finally:
            repo.delete_actual_session(sid)
            repo.delete_actual_session(sid2)
