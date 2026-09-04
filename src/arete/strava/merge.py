"""Merging a Strava copy of a workout into the Garmin session (Garmin wins).

Garmin (FIT + Connect) is the primary source. Strava adds what Garmin does not
export: best efforts, metric splits, suffer score, workout type, description,
and a name when the Garmin one is missing.
"""

from __future__ import annotations

from typing import Any

from arete.garmin.models import ActualSession

# Strava fields copied only when the Garmin row has nothing there.
_FILL_IF_MISSING = (
    "name",
    "notes",
    "workout_type",
    "device_name",
    "suffer_score",
    "avg_watts",
    "weighted_avg_watts",
    "laps_json",
    "splits_json",
    "hr_zones_json",
    "calories",
    "avg_pace_sec_km",
    "moving_time_sec",
)
# Strava-only data: always taken from Strava.
_ALWAYS_FROM_STRAVA = ("best_efforts_json",)


def strava_extras(existing: ActualSession, strava: ActualSession) -> dict[str, Any]:
    """Columns to update on ``existing`` with values from the Strava copy."""
    fields: dict[str, Any] = {"strava_activity_id": strava.garmin_activity_id}
    for col in _FILL_IF_MISSING:
        if getattr(existing, col) in (None, "") and getattr(strava, col) not in (
            None,
            "",
        ):
            fields[col] = getattr(strava, col)
    for col in _ALWAYS_FROM_STRAVA:
        if getattr(strava, col) is not None:
            fields[col] = getattr(strava, col)
    return fields


def garmin_takeover(garmin: ActualSession) -> dict[str, Any]:
    """Columns to write on a Strava-created row when the Garmin copy arrives."""
    fields: dict[str, Any] = {
        "source": garmin.source.value,
        "garmin_activity_id": garmin.garmin_activity_id,
    }
    for col in (
        "session_type",
        "source_file",
        "hr_zones_json",
        "laps_json",
        "avg_cadence",
        "max_cadence",
        "descent_m",
        "name",
    ):
        value = getattr(garmin, col)
        if value not in (None, ""):
            fields[col] = value
    return fields
