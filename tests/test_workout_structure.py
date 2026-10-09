"""Planned sessions as watch steps, in the athlete's zones."""

from __future__ import annotations

import pytest

from arete.features.hr_zones import ZoneModel
from arete.garmin.models import PlannedSession, SessionType
from arete.garmin.workout_structure import (
    NotPushable,
    Repeat,
    Step,
    derive,
    describe_fr,
    estimated_seconds,
    from_json,
    to_json,
)

ZONES = ZoneModel.from_reference(lthr=176)  # boundaries 150, 158, 167, 176


def _session(kind: SessionType, minutes: int | None = 50, **kw) -> PlannedSession:
    return PlannedSession(session_type=kind, target_duration_min=minutes, **kw)


def test_zone_ranges_are_closed_and_in_the_athletes_bpm():
    assert ZONES.target_range(2) == (150, 157)
    assert ZONES.target_range(4) == (167, 175)
    assert ZONES.target_range(1) == (142, 149)  # Z1 given Z2's width
    assert ZONES.target_range(5) == (176, 185)  # Z5 given Z4's width


def test_easy_sessions_are_one_block():
    (step,) = derive(_session(SessionType.ENDURANCE, 60), ZONES)
    assert isinstance(step, Step)
    assert (step.duration_sec, step.zone, step.hr_low, step.hr_high) == (
        3600,
        2,
        150,
        157,
    )
    (recovery,) = derive(_session(SessionType.RECOVERY, 30), ZONES)
    assert isinstance(recovery, Step) and recovery.zone == 1


def test_tempo_has_a_warm_up_a_block_and_a_cool_down():
    blocks = derive(_session(SessionType.TEMPO, 50, target_hr_zone="Z4"), ZONES)
    assert describe_fr(blocks) == "10' Z2 · 30' Z4 · 10' Z1"
    assert estimated_seconds(blocks) == 50 * 60


def test_intervals_fill_the_main_block_with_3_2_repeats():
    blocks = derive(_session(SessionType.INTERVALS, 45), ZONES)
    assert describe_fr(blocks) == "10' Z2 · 5×(3' Z5 / 2' Z1) · 10' Z1"
    repeat = blocks[1]
    assert isinstance(repeat, Repeat) and repeat.iterations == 5
    assert estimated_seconds(blocks) == 45 * 60


def test_a_short_session_gets_shorter_edges():
    blocks = derive(_session(SessionType.TEMPO, 30), ZONES)
    assert describe_fr(blocks) == "5' Z2 · 20' Z4 · 5' Z1"


def test_race_runs_at_threshold_pace_when_known():
    race = _session(SessionType.RACE, None, target_distance_km=10.0)
    (step,) = derive(race, ZONES, threshold_pace_sec_km=250)
    assert isinstance(step, Step)
    assert (step.distance_m, step.pace_fast_sec_km, step.pace_slow_sec_km) == (
        10000,
        240,
        260,
    )
    (open_step,) = derive(race, ZONES)
    assert isinstance(open_step, Step) and open_step.pace_fast_sec_km is None


@pytest.mark.parametrize(
    "session",
    [
        PlannedSession(
            session_type=SessionType.STRENGTH, sport="strength", target_duration_min=60
        ),
        PlannedSession(
            session_type=SessionType.ENDURANCE, sport="swimming", target_duration_min=40
        ),
        PlannedSession(session_type=SessionType.ENDURANCE, target_duration_min=None),
        PlannedSession(session_type=SessionType.TEMPO, target_duration_min=8),
    ],
)
def test_sessions_without_a_watch_structure_say_why(session):
    with pytest.raises(NotPushable) as error:
        derive(session, ZONES)
    assert str(error.value)  # a French reason for the UI


def test_an_explicit_structure_wins_and_round_trips():
    blocks = derive(_session(SessionType.INTERVALS, 45), ZONES)
    explicit = _session(SessionType.ENDURANCE, 60, structure_json=to_json(blocks))
    assert derive(explicit, ZONES) == blocks
    assert from_json(to_json(blocks)) == blocks
    with pytest.raises(NotPushable):
        from_json("not json")
