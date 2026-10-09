"""Arete steps as Garmin's workout payload, and the calendar round trip."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock

import pytest

from arete.features.hr_zones import ZoneModel
from arete.garmin.models import PlannedSession, SessionType
from arete.garmin.workout_structure import derive
from arete.garmin.workouts import build_payload, remove, upload_and_schedule

ZONES = ZoneModel.from_reference(lthr=176)


def _payload():
    blocks = derive(
        PlannedSession(session_type=SessionType.INTERVALS, target_duration_min=45),
        ZONES,
    )
    return build_payload(blocks, name="Arete — VMA", description="x", sport="running")


def test_the_payload_has_garmins_shape():
    payload = _payload()
    assert payload["sportType"]["sportTypeKey"] == "running"
    assert payload["estimatedDurationInSecs"] == 45 * 60
    (segment,) = payload["workoutSegments"]
    warmup, repeat, cooldown = segment["workoutSteps"]
    assert warmup["type"] == "ExecutableStepDTO"
    assert warmup["stepType"]["stepTypeKey"] == "warmup"
    assert warmup["endCondition"]["conditionTypeKey"] == "time"
    assert warmup["endConditionValue"] == 600.0
    assert warmup["targetType"]["workoutTargetTypeKey"] == "heart.rate.zone"
    assert (warmup["targetValueOne"], warmup["targetValueTwo"]) == (150, 157)
    assert repeat["type"] == "RepeatGroupDTO" and repeat["numberOfIterations"] == 5
    assert [s["stepType"]["stepTypeKey"] for s in repeat["workoutSteps"]] == [
        "interval",
        "recovery",
    ]
    # Garmin numbers steps depth-first: the group, then its children.
    orders = [warmup["stepOrder"], repeat["stepOrder"]]
    orders += [s["stepOrder"] for s in repeat["workoutSteps"]] + [cooldown["stepOrder"]]
    assert orders == [1, 2, 3, 4, 5]


def test_a_race_pace_target_is_a_speed_range():
    blocks = derive(
        PlannedSession(session_type=SessionType.RACE, target_distance_km=10.0),
        ZONES,
        threshold_pace_sec_km=250,
    )
    (step,) = build_payload(blocks, name="10K", description="", sport="running")[
        "workoutSegments"
    ][0]["workoutSteps"]
    assert step["endCondition"]["conditionTypeKey"] == "distance"
    assert step["targetType"]["workoutTargetTypeKey"] == "pace.zone"
    assert step["targetValueOne"] < step["targetValueTwo"]  # slow, then fast, in m/s


def test_upload_then_schedule():
    client = MagicMock()
    client.upload_workout.return_value = {"workoutId": 987}
    client.schedule_workout.return_value = {"workoutScheduleId": 55}
    ids = upload_and_schedule(client, _payload(), date(2026, 10, 9))
    assert ids == ("987", "55")
    client.schedule_workout.assert_called_once_with("987", date(2026, 10, 9))


def test_remove_tolerates_a_copy_already_gone():
    client = MagicMock()
    client.unschedule_workout.side_effect = RuntimeError("404 Not Found")
    remove(client, "987", "55")
    client.delete_workout.assert_called_once_with("987")
    client.delete_workout.side_effect = RuntimeError("500 boom")
    with pytest.raises(RuntimeError):
        remove(client, "987", None)
