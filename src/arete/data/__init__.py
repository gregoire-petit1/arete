"""Data module for Arete - exercise catalogs and seeding utilities."""

from arete.data.exercise_matcher import ExerciseMatch, match_exercise
from arete.data.exercises_catalog import (
    EXERCISE_ALIASES,
    EXERCISES_BY_ID,
    EXERCISES_CATALOG,
    MUSCLES,
    calculate_muscle_volume,
    get_exercise,
    get_muscles_for_exercise,
    resolve_exercise_name,
)

__all__ = [
    "ExerciseMatch",
    "match_exercise",
    "EXERCISES_CATALOG",
    "EXERCISES_BY_ID",
    "EXERCISE_ALIASES",
    "MUSCLES",
    "get_exercise",
    "get_muscles_for_exercise",
    "calculate_muscle_volume",
    "resolve_exercise_name",
]
