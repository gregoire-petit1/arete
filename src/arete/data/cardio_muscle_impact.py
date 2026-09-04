"""Pseudo muscle volume per minute of cardio activity.

Used by the strength volume-by-muscle heatmap to credit cardio sessions.
Keys are Arete sport names (see ``arete.dataio.queries`` for spellings);
values are arbitrary "volume units" per minute for primary/secondary muscles.
"""

from __future__ import annotations

_LEGS_RUN = {
    "primary": {"quads": 15, "calves": 12, "glutes": 10},
    "secondary": {"hamstrings": 8, "hip_flexors": 6, "tibialis": 4, "core": 3},
}
_LEGS_TRAIL = {
    "primary": {"quads": 18, "calves": 14, "glutes": 12},
    "secondary": {"hamstrings": 10, "hip_flexors": 8, "tibialis": 5, "core": 5},
}
_ROWING = {
    "primary": {"lats": 15, "quads": 12, "glutes": 10},
    "secondary": {
        "biceps": 8,
        "hamstrings": 6,
        "rhomboids": 6,
        "forearms": 4,
        "core": 5,
    },
}
_CYCLING = {
    "primary": {"quads": 12, "glutes": 10},
    "secondary": {"hamstrings": 6, "calves": 4, "hip_flexors": 3},
}

CARDIO_MUSCLE_IMPACT: dict[str, dict[str, dict[str, int]]] = {
    "running": _LEGS_RUN,
    "run": _LEGS_RUN,
    "treadmill_running": _LEGS_RUN,
    "trail_running": _LEGS_TRAIL,
    "trail_run": _LEGS_TRAIL,
    "rowing": _ROWING,
    "indoor_rowing": _ROWING,
    "cycling": _CYCLING,
    "ride": _CYCLING,
    "indoor_cycling": _CYCLING,
    "virtual_ride": _CYCLING,
}
