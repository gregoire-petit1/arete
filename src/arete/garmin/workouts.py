"""Arete workout steps as a Garmin Connect workout, scheduled on its calendar.

The watch picks a scheduled workout up at its next sync with the phone:
Garmin's calendar is the delivery, there is no direct push in the API.

The numeric ids below are the ones public Garmin clients send. They were not
read from a workout on this account: before turning the push on, run
``scripts/garmin_probe.py --workout <id>`` on a workout built by hand and
compare its ``stepType`` / ``endCondition`` / ``targetType`` pairs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from arete.garmin.workout_structure import Block, Repeat, Step, estimated_seconds

if TYPE_CHECKING:
    from datetime import date

    from arete.garmin.client import GarminClient

SPORT_TYPES: dict[str, dict[str, Any]] = {
    "running": {"sportTypeId": 1, "sportTypeKey": "running", "displayOrder": 1},
    "cycling": {"sportTypeId": 2, "sportTypeKey": "cycling", "displayOrder": 2},
}
STEP_TYPES: dict[str, dict[str, Any]] = {
    "warmup": {"stepTypeId": 1, "stepTypeKey": "warmup", "displayOrder": 1},
    "cooldown": {"stepTypeId": 2, "stepTypeKey": "cooldown", "displayOrder": 2},
    "interval": {"stepTypeId": 3, "stepTypeKey": "interval", "displayOrder": 3},
    "recovery": {"stepTypeId": 4, "stepTypeKey": "recovery", "displayOrder": 4},
    "repeat": {"stepTypeId": 6, "stepTypeKey": "repeat", "displayOrder": 6},
}
END_CONDITIONS: dict[str, dict[str, Any]] = {
    "time": {"conditionTypeId": 2, "conditionTypeKey": "time", "displayOrder": 2},
    "distance": {
        "conditionTypeId": 3,
        "conditionTypeKey": "distance",
        "displayOrder": 3,
    },
    "iterations": {
        "conditionTypeId": 7,
        "conditionTypeKey": "iterations",
        "displayOrder": 7,
    },
}
TARGET_TYPES: dict[str, dict[str, Any]] = {
    "none": {
        "workoutTargetTypeId": 1,
        "workoutTargetTypeKey": "no.target",
        "displayOrder": 1,
    },
    "heart_rate": {
        "workoutTargetTypeId": 4,
        "workoutTargetTypeKey": "heart.rate.zone",
        "displayOrder": 4,
    },
    "pace": {
        "workoutTargetTypeId": 6,
        "workoutTargetTypeKey": "pace.zone",
        "displayOrder": 6,
    },
}


def _speed(sec_per_km: int) -> float:
    """Garmin's pace targets are speeds, in metres per second."""
    return round(1000 / sec_per_km, 3)


def _executable(step: Step, order: int) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "type": "ExecutableStepDTO",
        "stepOrder": order,
        "stepType": STEP_TYPES[step.kind],
    }
    if step.distance_m:
        payload["endCondition"] = END_CONDITIONS["distance"]
        payload["endConditionValue"] = float(step.distance_m)
    else:
        payload["endCondition"] = END_CONDITIONS["time"]
        payload["endConditionValue"] = float(step.duration_sec or 0)
    if step.hr_low is not None and step.hr_high is not None:
        payload["targetType"] = TARGET_TYPES["heart_rate"]
        payload["targetValueOne"] = step.hr_low
        payload["targetValueTwo"] = step.hr_high
    elif step.pace_fast_sec_km and step.pace_slow_sec_km:
        payload["targetType"] = TARGET_TYPES["pace"]
        payload["targetValueOne"] = _speed(step.pace_slow_sec_km)
        payload["targetValueTwo"] = _speed(step.pace_fast_sec_km)
    else:
        payload["targetType"] = TARGET_TYPES["none"]
    return payload


def _steps(
    blocks: tuple[Block, ...] | tuple[Step, ...], start: int
) -> tuple[list, int]:
    """Payload steps, numbered depth-first as Garmin numbers them."""
    out: list[dict[str, Any]] = []
    order = start
    for block in blocks:
        if isinstance(block, Repeat):
            group_order = order
            inner, order = _steps(block.steps, order + 1)
            out.append(
                {
                    "type": "RepeatGroupDTO",
                    "stepOrder": group_order,
                    "stepType": STEP_TYPES["repeat"],
                    "numberOfIterations": block.iterations,
                    "smartRepeat": False,
                    "endCondition": END_CONDITIONS["iterations"],
                    "endConditionValue": float(block.iterations),
                    "workoutSteps": inner,
                }
            )
        else:
            out.append(_executable(block, order))
            order += 1
    return out, order


def build_payload(
    blocks: tuple[Block, ...], *, name: str, description: str, sport: str
) -> dict[str, Any]:
    """The workout as Garmin's ``POST /workout-service/workout`` expects it."""
    sport_type = SPORT_TYPES[sport]
    steps, _ = _steps(blocks, 1)
    return {
        "workoutName": name[:80],
        "description": description[:500],
        "sportType": sport_type,
        "estimatedDurationInSecs": estimated_seconds(blocks),
        "workoutSegments": [
            {"segmentOrder": 1, "sportType": sport_type, "workoutSteps": steps}
        ],
    }


def upload_and_schedule(
    client: GarminClient, payload: dict[str, Any], day: date
) -> tuple[str, str | None]:
    """Create the workout and put it on ``day``: (workout id, schedule id)."""
    created = client.upload_workout(payload)
    workout_id = str(created["workoutId"])
    scheduled = client.schedule_workout(workout_id, day)
    schedule_id = (
        scheduled.get("workoutScheduleId") if isinstance(scheduled, dict) else None
    )
    return workout_id, str(schedule_id) if schedule_id is not None else None


def remove(
    client: GarminClient, workout_id: str | None, schedule_id: str | None
) -> None:
    """Take an earlier copy off the calendar and delete it; gone already is fine."""
    for action, value in (
        (client.unschedule_workout, schedule_id),
        (client.delete_workout, workout_id),
    ):
        if value is None:
            continue
        try:
            action(value)
        except Exception as e:  # noqa: BLE001 - a missing copy is not an error
            if "404" not in str(e):
                raise
