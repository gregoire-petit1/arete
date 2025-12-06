"""Data module for Arete - exercise catalogs and seeding utilities."""

from arete.data.exercises_catalog import (
    EXERCISES_CATALOG,
    EXERCISES_BY_ID,
    EXERCISE_ALIASES,
    MUSCLES,
    get_exercise,
    get_muscles_for_exercise,
    calculate_muscle_volume,
    resolve_exercise_name,
)

__all__ = [
    "EXERCISES_CATALOG",
    "EXERCISES_BY_ID",
    "EXERCISE_ALIASES",
    "MUSCLES",
    "get_exercise",
    "get_muscles_for_exercise",
    "calculate_muscle_volume",
    "resolve_exercise_name",
]
