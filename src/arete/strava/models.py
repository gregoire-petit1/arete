"""Strava activity models and mapping to ActualSession."""

from __future__ import annotations

import json
from datetime import datetime

from arete.garmin.models import ActualSession, ActivitySource

_SPORT_MAP: dict[str, str] = {
    "Run": "run",
    "TrailRun": "trail_run",
    "Ride": "ride",
    "VirtualRide": "virtual_ride",
    "Swim": "swim",
    "Hike": "hike",
    "Walk": "walk",
    "WeightTraining": "weight_training",
    "Workout": "workout",
    "Yoga": "yoga",
    "CrossFit": "crossfit",
    "Rowing": "rowing",
    "Elliptical": "elliptical",
}

_RUNNING_TYPES = {"Run", "TrailRun", "VirtualRun"}


def strava_activity_to_actual_session(
    activity: dict,
    hr_zones: dict | None = None,
) -> ActualSession:
    """Convert a raw Strava activity dict to an ActualSession."""
    strava_type = activity.get("type", "Workout")
    sport = _SPORT_MAP.get(strava_type, strava_type.lower())

    start_str = activity.get("start_date_local") or activity["start_date"]
    start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))

    avg_speed = activity.get("average_speed")
    avg_pace_sec_km = None
    if avg_speed and avg_speed > 0:
        avg_pace_sec_km = int(round(1000 / avg_speed))

    raw_cadence = activity.get("average_cadence")
    cadence = None
    if raw_cadence is not None:
        cadence = (
            int(raw_cadence * 2) if strava_type in _RUNNING_TYPES else int(raw_cadence)
        )

    latlng = activity.get("start_latlng") or []

    return ActualSession(
        date=start_dt.date(),
        sport=sport,
        duration_sec=activity["elapsed_time"],
        distance_m=activity.get("distance"),
        calories=activity.get("calories"),
        avg_hr=(
            int(activity["average_heartrate"])
            if activity.get("average_heartrate")
            else None
        ),
        max_hr=(
            int(activity["max_heartrate"]) if activity.get("max_heartrate") else None
        ),
        avg_pace_sec_km=avg_pace_sec_km,
        avg_speed_mps=avg_speed,
        max_speed_mps=activity.get("max_speed"),
        ascent_m=activity.get("total_elevation_gain"),
        start_lat=latlng[0] if len(latlng) > 0 else None,
        start_lon=latlng[1] if len(latlng) > 1 else None,
        avg_cadence=cadence,
        source=ActivitySource.STRAVA,
        garmin_activity_id=str(activity["id"]),
        start_time=start_dt,
        name=activity.get("name"),
        notes=activity.get("description"),
        moving_time_sec=activity.get("moving_time"),
        suffer_score=activity.get("suffer_score"),
        workout_type=str(activity["workout_type"])
        if activity.get("workout_type") is not None
        else None,
        device_name=activity.get("device_name"),
        avg_watts=int(activity["average_watts"])
        if activity.get("average_watts")
        else None,
        weighted_avg_watts=int(activity["weighted_average_watts"])
        if activity.get("weighted_average_watts")
        else None,
        laps_json=json.dumps(activity["laps"]) if activity.get("laps") else None,
        splits_json=json.dumps(activity["splits_metric"])
        if activity.get("splits_metric")
        else None,
        best_efforts_json=json.dumps(activity["best_efforts"])
        if activity.get("best_efforts")
        else None,
        hr_zones_json=json.dumps(hr_zones) if hr_zones else None,
    )
