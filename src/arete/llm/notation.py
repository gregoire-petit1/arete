"""Writes parsed exercises back as the compact notation.

A dictation is read into the same structure a typed session produces; this
turns that structure back into text so the athlete proof-reads in the notation
they already know rather than in their own sentence. Round-tripping through the
grammar must be stable: what this writes, ``workout_grammar`` reads back.
"""

from __future__ import annotations

from typing import Any


def format_rest(seconds: int | None) -> str | None:
    """90 -> "r1'30", 180 -> "r3'", 45 -> "r0'45"."""
    if not seconds or seconds <= 0:
        return None
    minutes, rest = divmod(int(seconds), 60)
    return f"r{minutes}'" if rest == 0 else f"r{minutes}'{rest:02d}"


def format_weight(weight: float | None) -> str | None:
    """80.0 -> "@80", 12.5 -> "@12.5"."""
    if weight is None or weight <= 0:
        return None
    return f"@{int(weight)}" if float(weight).is_integer() else f"@{weight:g}"


def format_rpe(rpe: float | None) -> str | None:
    if rpe is None or rpe <= 0:
        return None
    return f"RPE {int(rpe)}" if float(rpe).is_integer() else f"RPE {rpe:g}"


def _reps_token(exercise: dict[str, Any]) -> str:
    """ "8", "8-10", "12e" or "amrap", as the grammar spells them."""
    first = exercise["sets"][0]
    if first.get("is_failure"):
        return "amrap"
    target = exercise.get("target_reps")
    if target:
        return str(target)
    reps = first.get("reps")
    return str(reps) if reps is not None else "amrap"


def exercise_to_notation(exercise: dict[str, Any]) -> str:
    """One parsed exercise -> one line of notation."""
    sets = exercise.get("sets") or []
    if not sets:
        return str(exercise.get("name", "")).strip()

    first = sets[0]
    parts = [str(exercise["name"]).strip(), f"{len(sets)}x{_reps_token(exercise)}"]
    for value in (
        format_weight(first.get("weight_kg")),
        format_rest(first.get("rest_sec")),
        format_rpe(first.get("rpe")),
    ):
        if value:
            parts.append(value)
    return " ".join(parts)


def to_notation(exercises: list[dict[str, Any]]) -> str:
    """Parsed exercises -> the text that goes back into the session box."""
    return "\n".join(exercise_to_notation(ex) for ex in exercises if ex)


__all__ = [
    "exercise_to_notation",
    "format_rest",
    "format_rpe",
    "format_weight",
    "to_notation",
]
