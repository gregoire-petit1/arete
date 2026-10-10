"""Kept FIT streams, the dormant analytics they feed, and the session page's read."""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta

import pytest

from arete.garmin.models import ActivitySource, ActualSession
from arete.garmin.repository import GarminRepository
from arete.garmin.streams import (
    MAX_SAMPLES,
    ActivityStreams,
    downsample,
    from_time_series,
    route,
)
from arete.garmin.time_series import (
    ActivityMetricsCalculator,
    LapIntensity,
    TimeSeriesData,
    TimeSeriesPoint,
)

START = datetime(2026, 10, 1, 8, 0)


def _series(
    n: int, *, hr=lambda i: 140, speed=lambda i: 3.0, **extra
) -> TimeSeriesData:
    return TimeSeriesData(
        points=[
            TimeSeriesPoint(
                timestamp=START + timedelta(seconds=i),
                elapsed_sec=i,
                heart_rate=hr(i),
                speed_mps=speed(i),
                **{key: fn(i) for key, fn in extra.items()},
            )
            for i in range(n)
        ]
    )


# ---------------------------------------------------------------------------
# The dormant analytics, fixed where they were wrong
# ---------------------------------------------------------------------------


class TestAnalytics:
    def test_decoupling_is_positive_when_the_heart_drifts_at_the_same_pace(self):
        ts = _series(3600, hr=lambda i: 140 if i < 1800 else 150)
        assert ActivityMetricsCalculator().calculate(ts).hr_decoupling_pct == (
            pytest.approx((1 - 140 / 150) * 100, abs=0.01)
        )

    def test_decoupling_is_positive_when_the_pace_drops_at_the_same_heart(self):
        # The old ratio (HR / pace) called this an improvement.
        ts = _series(3600, speed=lambda i: 3.0 if i < 1800 else 2.7)
        assert ActivityMetricsCalculator().calculate(ts).hr_decoupling_pct > 9

    def test_decoupling_pairs_the_samples_carrying_both(self):
        ts = _series(3600, hr=lambda i: None if i % 10 == 0 else 140)
        assert ActivityMetricsCalculator().calculate(ts).hr_decoupling_pct == (
            pytest.approx(0, abs=0.01)
        )

    def test_normalized_power_of_a_steady_effort_is_its_average(self):
        ts = _series(1200, power=lambda i: 250)
        metrics = ActivityMetricsCalculator().calculate(ts)
        assert metrics.power_normalized == 250
        assert metrics.power_variability_index == 1.0

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("active", LapIntensity.ACTIVE),
            (5, LapIntensity.ACTIVE),  # interval, unnamed by fitparse
            (4, LapIntensity.REST),  # recovery
            ("rest", LapIntensity.REST),
            ("warmup", LapIntensity.WARMUP),
            (None, LapIntensity.OTHER),
        ],
    )
    def test_lap_intensity(self, raw, expected):
        assert LapIntensity.from_fit_value(raw) is expected


# ---------------------------------------------------------------------------
# Streams: conversion, thinning, chart and route
# ---------------------------------------------------------------------------


class TestStreams:
    def test_running_cadence_is_stored_in_steps_per_minute(self):
        streams = from_time_series(_series(10, cadence=lambda i: 85), "running")
        assert streams is not None and streams.cadence == [170] * 10
        bike = from_time_series(_series(10, cadence=lambda i: 85), "cycling")
        assert bike is not None and bike.cadence == [85] * 10

    def test_a_channel_never_recorded_is_absent_not_a_list_of_nulls(self):
        streams = from_time_series(_series(10), "running")
        assert streams is not None
        assert streams.power_w is None and streams.lat is None
        assert not streams.has_route
        assert set(streams.channels()) == {"heart_rate", "speed_mps"}

    def test_t_counts_from_the_first_record_and_keeps_pauses(self):
        ts = _series(4)
        ts.points[3].timestamp += timedelta(seconds=60)  # a stop at the lights
        streams = from_time_series(ts, "running")
        assert streams is not None and streams.t == [0, 1, 2, 63]

    def test_no_points_no_streams(self):
        assert from_time_series(None, "running") is None
        assert from_time_series(TimeSeriesData(), "running") is None

    def test_a_long_recording_is_thinned_evenly(self):
        ts = _series(MAX_SAMPLES * 2 + 1)
        streams = from_time_series(ts, "running")
        assert streams is not None and len(streams) <= MAX_SAMPLES
        assert streams.t[-1] > MAX_SAMPLES * 2 - 10  # still reaches the end

    def test_downsample_averages_each_bucket(self):
        streams = ActivityStreams(t=list(range(10)), heart_rate=[100, 200] * 5)
        out = downsample(streams, 5)
        assert out == {"t": [0, 2, 4, 6, 8], "heart_rate": [150] * 5}

    def test_route_keeps_the_finish(self):
        n = 1001
        streams = ActivityStreams(
            t=list(range(n)),
            lat=[45.9 + i * 1e-5 for i in range(n)],
            lon=[6.87] * n,
        )
        trace = route(streams, 100)
        assert trace is not None and len(trace) <= 102
        assert trace[0] == [45.9, 6.87] and trace[-1] == [streams.lat[-1], 6.87]

    def test_round_trips_through_the_analytics(self):
        streams = ActivityStreams(t=[0, 1, 2], heart_rate=[140, None, 150])
        ts = streams.to_time_series(START)
        assert [p.heart_rate for p in ts.points] == [140, None, 150]
        assert ts.points[2].timestamp == START + timedelta(seconds=2)


# ---------------------------------------------------------------------------
# Repository and the session page's read
# ---------------------------------------------------------------------------


def _laps(intensities: list[str | None]) -> str:
    return json.dumps(
        [
            {
                "lap_index": i,
                "distance": 1000.0 if kind == "active" else 400.0,
                "elapsed_time": 240 if kind == "active" else 120,
                "moving_time": 240 if kind == "active" else 120,
                "average_speed": 4.17 if kind == "active" else 3.3,
                "average_heartrate": 170 if kind == "active" else 140,
                "max_heartrate": 178,
                "average_cadence": 180,
                "intensity": kind,
            }
            for i, kind in enumerate(intensities, start=1)
        ]
    )


@pytest.fixture
def make_session():
    repo = GarminRepository()
    created: list[int] = []

    def make(**fields) -> int:
        values = {
            "date": date(2031, 3, 4),
            "sport": "running",
            "duration_sec": 3600,
            "distance_m": 10000,
            "avg_hr": 150,
            "source": ActivitySource.GARMIN_CONNECT,
            "start_time": datetime(2031, 3, 4, 7, 30),
            **fields,
        }
        session_id = repo.create_actual_session(ActualSession(**values))
        created.append(session_id)
        return session_id

    yield make
    for session_id in created:
        repo.delete_actual_session(session_id)


def _steady_streams(n: int = 3600) -> ActivityStreams:
    ts = _series(
        n,
        hr=lambda i: 140 if i < n // 2 else 147,
        altitude=lambda i: 1000.0 + i / 100,
        distance_m=lambda i: i * 3.0,
        lat=lambda i: 45.9 + i * 1e-5,
        lon=lambda i: 6.87,
    )
    streams = from_time_series(ts, "running")
    assert streams is not None
    return streams


class TestRepository:
    def test_streams_round_trip_and_replace(self, make_session):
        repo = GarminRepository()
        session_id = make_session()
        repo.save_activity_streams(session_id, _steady_streams(100))
        repo.save_activity_streams(session_id, _steady_streams(50))
        stored = repo.get_activity_streams(session_id)
        assert stored is not None and len(stored) == 50
        assert stored.heart_rate == [140] * 25 + [147] * 25
        assert stored.lat is not None and stored.lat[0] == pytest.approx(45.9, abs=1e-5)
        assert stored.power_w is None

    def test_deleting_the_session_deletes_its_streams(self, make_session):
        repo = GarminRepository()
        session_id = make_session()
        repo.save_activity_streams(session_id, _steady_streams(10))
        repo.delete_actual_session(session_id)
        assert repo.get_activity_streams(session_id) is None


class TestDetail:
    def test_a_steady_run_gets_its_analysis_chart_and_route(self, make_session):
        from arete.services.activity_detail import CHART_POINTS, get_activity_detail

        session_id = make_session(laps_json=_laps(["active"] * 10))
        GarminRepository().save_activity_streams(session_id, _steady_streams())
        detail = get_activity_detail(session_id)
        assert detail is not None
        assert detail["session"]["id"] == session_id
        assert len(detail["laps"]) == 10 and detail["intervals"] is None
        metrics = detail["metrics"]
        assert metrics["decoupling_pct"] == pytest.approx(
            (1 - 140 / 147) * 100, abs=0.1
        )
        assert metrics["pace_first_half_sec_km"] == 333
        assert len(detail["streams"]["t"]) <= CHART_POINTS
        assert {"heart_rate", "speed_mps", "altitude_m"} <= set(detail["streams"])
        assert detail["route"] is not None and len(detail["route"]) > 2

    def test_structured_intervals_are_detected_from_the_laps(self, make_session):
        from arete.services.activity_detail import get_activity_detail

        laps = ["warmup"] + ["active", 4] * 5 + ["cooldown"]
        session_id = make_session(laps_json=_laps(laps))
        GarminRepository().save_activity_streams(session_id, _steady_streams())
        detail = get_activity_detail(session_id)
        assert detail is not None
        intervals = detail["intervals"]
        assert intervals["count"] == 5 and intervals["work_avg_sec"] == 240
        assert intervals["work"][0]["pace_sec_km"] == 240
        # Halves of an interval session say nothing about aerobic drift.
        assert "decoupling_pct" not in detail["metrics"]

    def test_laps_without_intensity_are_never_guessed_into_intervals(
        self, make_session
    ):
        from arete.services.activity_detail import get_activity_detail

        session_id = make_session(laps_json=_laps([None] * 6))
        detail = get_activity_detail(session_id)
        assert detail is not None
        assert detail["intervals"] is None
        assert detail["streams"] is None and detail["metrics"] is None

    def test_an_unknown_session_is_none(self):
        from arete.services.activity_detail import get_activity_detail

        assert get_activity_detail(987654321) is None

    def test_the_endpoint(self, make_session, client):
        session_id = make_session()
        response = client.get(f"/analytics/sessions/{session_id}/detail")
        assert response.status_code == 200
        assert response.json()["session"]["name"] is None
        assert client.get("/analytics/sessions/987654321/detail").status_code == 404


class TestCoachTool:
    def test_the_digest_is_compact_and_has_no_stream(self, make_session):
        from arete.agent.tools.analytics import get_activity_detail

        session_id = make_session(laps_json=_laps(["active"] * 40))
        GarminRepository().save_activity_streams(session_id, _steady_streams())
        out = json.loads(get_activity_detail.invoke({"session_id": session_id}))
        assert out["streams_kept"] is True
        assert "streams" not in out and "route" not in out
        assert len(out["laps"]) == 15 and out["laps_omitted"] == 25
        assert "decoupling_pct" in out["analysis"]
        assert len(json.dumps(out)) < 4000

    def test_strava_rows_never_reach_the_model(self, make_session):
        from arete.agent.tools.analytics import get_activity_detail

        session_id = make_session(source=ActivitySource.STRAVA)
        out = json.loads(get_activity_detail.invoke({"session_id": session_id}))
        assert "Strava" in out["error"]

    def test_an_unknown_session_is_a_tool_error(self):
        from arete.agent.tools.analytics import get_activity_detail

        out = json.loads(get_activity_detail.invoke({"session_id": 987654321}))
        assert "introuvable" in out["error"]

    def test_the_feedback_facts_carry_the_analysis(self, make_session):
        from arete.services.coaching_rules import _generate_cardio_feedback

        laps = ["warmup"] + ["active", 4] * 5 + ["cooldown"]
        session_id = make_session(laps_json=_laps(laps))
        result, _ = _generate_cardio_feedback(session_id)
        assert any("Fractionné détecté : 5 répétitions" in h for h in result.highlights)
