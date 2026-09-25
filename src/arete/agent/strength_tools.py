"""Strength toolkit — read a dictated session, then save it. In that order.

The first toolkit that writes training data, and the write is lossy by nature:
the parser only saves exercises the catalog matched confidently, and drops the
rest. A human filling the form sees that happen. An athlete dictating to a
coach reads one sentence, so the drop has to be in the transcript before
anything is written — hence two tools rather than one.

``read_workout`` is the dry run: it parses, reports what matched and what did
not, and touches nothing. ``save_workout`` writes. Both go through
``strength.logging_service``, the same code the Log page posts to, so the
athlete's abbreviations, the catalog matching and the planned-session
completion cannot drift between the two entry points.

Re-parsing in ``save_workout`` is deliberate: the parser is deterministic, so
passing the text again is cheaper and safer than carrying a parse handle
across turns.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any

from langchain_core.tools import BaseTool, tool

from arete.agent.tools import MAX_TOOL_OUTPUT_CHARS

#: Enough for a long session; past it the text is not a workout.
MAX_WORKOUT_TEXT_CHARS = 4_000


def _out(payload: Any) -> str:
    rendered = json.dumps(payload, ensure_ascii=False, default=str)
    if len(rendered) > MAX_TOOL_OUTPUT_CHARS:
        return json.dumps({"error": f"Result too large ({len(rendered)} chars)."})
    return rendered


def _error(message: str) -> str:
    return json.dumps({"error": message}, ensure_ascii=False)


def _checked(text: str, date_str: str) -> tuple[str, date | None] | str:
    """Validated (text, date), or an error payload."""
    if not text or not text.strip():
        return _error("text is empty; give the session as the athlete said it")
    if len(text) > MAX_WORKOUT_TEXT_CHARS:
        return _error(
            f"text too long ({len(text)} chars, max {MAX_WORKOUT_TEXT_CHARS})"
        )
    if not date_str:
        return text, None
    try:
        return text, date.fromisoformat(date_str)
    except ValueError:
        return _error(f"date_str must be YYYY-MM-DD, got {date_str!r}")


def _summarize(parsed: Any) -> dict[str, Any]:
    from arete.strength.logging_service import dropped_exercises

    dropped = dropped_exercises(parsed)
    return {
        "date": parsed.date.isoformat(),
        "name": parsed.name,
        "duration_min": parsed.duration_min,
        "overall_rpe": parsed.overall_rpe,
        "exercises": [
            {
                "name": exercise.name,
                "matched": exercise.exercise_id is not None,
                "sets": [
                    {
                        "reps": s.reps,
                        "weight_kg": s.weight_kg,
                        "rpe": s.rpe,
                        "warmup": s.is_warmup,
                    }
                    for s in exercise.sets
                ],
            }
            for exercise in parsed.exercises
        ],
        "not_recognised": [
            {"name": d.name, "did_you_mean": d.suggestions} for d in dropped
        ],
        "unparsed_lines": parsed.unparsed_lines,
    }


@tool
def read_workout(text: str, date_str: str = "") -> str:
    """Read a dictated strength session WITHOUT saving it: what the parser
    understood, and which exercises it did not recognise. Always call this
    before save_workout, and tell the athlete about anything in
    `not_recognised` or `unparsed_lines` — those would be lost on save.

    Args:
        text: The session as the athlete described it, in their own words.
        date_str: ISO date (YYYY-MM-DD) of the session; empty means today.
    """
    checked = _checked(text, date_str)
    if isinstance(checked, str):
        return checked
    workout_text, workout_date = checked
    try:
        from arete.strength.logging_service import parse_for_athlete

        parsed = parse_for_athlete(workout_text, workout_date=workout_date)
    except ValueError as exc:
        return _error(f"Nothing readable as an exercise: {exc}")
    except Exception as exc:
        return _error(f"{type(exc).__name__}: {exc}")
    return _out({"saved": False, **_summarize(parsed)})


@tool
def save_workout(text: str, date_str: str = "") -> str:
    """Save a dictated strength session. Exercises the catalog does not match
    are NOT saved — they come back in `not_recognised` and you must say so.
    Read it with read_workout first.

    Args:
        text: The session as the athlete described it, in their own words.
        date_str: ISO date (YYYY-MM-DD) of the session; empty means today.
    """
    checked = _checked(text, date_str)
    if isinstance(checked, str):
        return checked
    workout_text, workout_date = checked
    try:
        from arete.strength.logging_service import (
            parse_for_athlete,
            save_parsed_session,
        )

        parsed = parse_for_athlete(workout_text, workout_date=workout_date)
        outcome = save_parsed_session(parsed)
    except ValueError as exc:
        return _error(f"Nothing readable as an exercise: {exc}")
    except Exception as exc:
        return _error(f"{type(exc).__name__}: {exc}")

    return _out(
        {
            "saved": outcome.session_id is not None,
            "session_id": outcome.session_id,
            "saved_exercises": outcome.saved,
            "message": outcome.message,
            **{
                k: v
                for k, v in _summarize(parsed).items()
                if k in ("date", "name", "not_recognised", "unparsed_lines")
            },
        }
    )


STRENGTH_TOOLS: list[BaseTool] = [read_workout, save_workout]

STRENGTH_INSTRUCTIONS = """Toolkit `strength` chargé — enregistrer une séance de musculation dictée:
- `read_workout(text, date_str?)`: lit SANS rien écrire. Renvoie ce que le parser a compris, \
`not_recognised` (exercices que le catalogue ne reconnaît pas) et `unparsed_lines` (lignes illisibles).
- `save_workout(text, date_str?)`: enregistre. Les exercices non reconnus NE SONT PAS enregistrés.

Toujours dans cet ordre: `read_workout` d'abord, tu annonces à l'athlète ce qui a été compris \
et surtout ce qui ne l'a pas été, puis `save_workout` seulement après. Ce qui tombe dans \
`not_recognised` est perdu à l'enregistrement: ne l'enterre pas, cite les noms et propose \
les `did_you_mean` pour qu'il reformule.
Passe le texte tel que l'athlète l'a dit — ses abréviations sont résolues côté serveur. \
N'invente jamais une série, une charge ou un RPE qu'il n'a pas donné."""
