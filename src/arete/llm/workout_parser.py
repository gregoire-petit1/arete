"""LLM-based workout text parser.

Parses free-text workout logs into structured session data.
Example input:
    Bench press 4x8 80kg
    Incline DB 3x12 30kg
    Cable flies 3x15
    Triceps pushdown 4x12

Output: Structured StrengthSession with exercises and sets.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

# Groq uses OpenAI-compatible SDK
from openai import OpenAI as OpenAIClient

from arete.data.exercises_catalog import EXERCISES_CATALOG
from arete.llm.token_manager import get_token_manager

logger = logging.getLogger(__name__)

# Groq configuration
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "llama-3.3-70b-versatile"


@dataclass
class ParsedSet:
    """A parsed set from workout text."""

    set_number: int
    reps: int | None = None  # None for failure sets
    weight_kg: float | None = None
    rpe: float | None = None
    is_warmup: bool = False
    is_failure: bool = False


@dataclass
class ParsedExercise:
    """A parsed exercise from workout text."""

    name: str
    exercise_id: str | None  # Matched ID from catalog
    sets: list[ParsedSet]
    notes: str | None = None


@dataclass
class ParsedWorkout:
    """Complete parsed workout."""

    date: date
    name: str | None
    exercises: list[ParsedExercise]
    duration_min: int | None = None
    overall_rpe: float | None = None
    notes: str | None = None


def get_client() -> OpenAIClient | None:
    """Get Groq client via OpenAI-compatible SDK."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.warning("GROQ_API_KEY not set, LLM features disabled")
        return None
    return OpenAIClient(api_key=api_key, base_url=GROQ_BASE_URL)


def _get_exercise_list_for_prompt() -> str:
    """Build compact exercise list for LLM context."""
    exercises = []
    for ex in EXERCISES_CATALOG[:50]:  # Limit to top 50 for token efficiency
        exercises.append(f"- {ex['id']}: {ex['name']} ({ex['name_fr']})")
    return "\n".join(exercises)


def _build_parser_prompt(workout_text: str, workout_date: str) -> tuple[str, str]:
    """Build system and user prompts for workout parsing."""

    exercise_list = _get_exercise_list_for_prompt()

    system_prompt = f"""Tu es un parser de séances de musculation. Tu dois extraire les exercices et sets d'un texte libre.

EXERCICES CONNUS (utilise ces IDs quand possible):
{exercise_list}

RÈGLES:
1. Retourne UNIQUEMENT du JSON valide, sans texte avant/après
2. Parse les formats: "4x8", "3x10-12", "4x8 @80kg", "4x8 80kg RPE 8"
3. Si l'exercice n'est pas dans la liste, utilise exercise_id: null et garde le nom original
4. Convertis les poids en kg si nécessaire (lbs → kg * 0.453)
5. Détecte les warmup sets (échauffement, warmup, w/)
6. Pour les sets "to failure" ou "AMRAP", mets reps: null et is_failure: true

FORMAT JSON ATTENDU:
{{
  "name": "Push Day" ou null,
  "duration_min": 60 ou null,
  "overall_rpe": 7.5 ou null,
  "exercises": [
    {{
      "name": "Bench Press",
      "exercise_id": "bench_press" ou null,
      "sets": [
        {{"set_number": 1, "reps": 8, "weight_kg": 80, "rpe": null, "is_warmup": false, "is_failure": false}},
        {{"set_number": 2, "reps": null, "weight_kg": null, "rpe": null, "is_warmup": false, "is_failure": true}},
        ...
      ],
      "notes": null
    }}
  ],
  "notes": null
}}"""

    user_prompt = f"""Date: {workout_date}

Texte de la séance:
{workout_text}

Parse cette séance en JSON."""

    return system_prompt, user_prompt


def _match_exercise_fuzzy(name: str) -> str | None:
    """Try to match exercise name to catalog ID."""
    name_lower = name.lower().strip()

    # Common abbreviations/aliases - use word boundaries
    aliases = [
        (r"\bdb\b", "dumbbell"),
        (r"\bbb\b", "barbell"),
        (r"\bpulls ups\b", "pull ups"),
        (r"\bpull up\b", "pull ups"),
        (r"\bchin up\b", "chin ups"),
        (r"\bdip\b", "dips"),
        (r"\bohp\b", "overhead press"),
        (r"\brdl\b", "romanian deadlift"),
        (r"\bsldl\b", "stiff leg deadlift"),
    ]

    # Expand abbreviations using regex word boundaries
    expanded = name_lower
    for pattern, replacement in aliases:
        expanded = re.sub(pattern, replacement, expanded)

    # Direct match on name or name_fr
    for ex in EXERCISES_CATALOG:
        if expanded == ex["name"].lower() or expanded == ex["name_fr"].lower():
            return ex["id"]
        if name_lower == ex["name"].lower() or name_lower == ex["name_fr"].lower():
            return ex["id"]

    # Partial match with expanded name
    for ex in EXERCISES_CATALOG:
        if expanded in ex["name"].lower() or expanded in ex["name_fr"].lower():
            return ex["id"]
        if ex["name"].lower() in expanded or ex["name_fr"].lower() in expanded:
            return ex["id"]

    # Partial match with original name
    for ex in EXERCISES_CATALOG:
        if name_lower in ex["name"].lower() or name_lower in ex["name_fr"].lower():
            return ex["id"]
        if ex["name"].lower() in name_lower or ex["name_fr"].lower() in name_lower:
            return ex["id"]

    return None


def _parse_simple_format(text: str) -> list[dict] | None:
    """Try to parse simple formats without LLM (fallback/fast path).

    Formats supported:
    - "Bench press 4x8 80kg"
    - "Squat 3x5 @100kg RPE 8"
    - "Pull ups 4x10"
    - "Dips 3x failure" or "Dips 3xfailure"
    - Circuit format: "5x(8 pull ups @20kg, 10 dips)" - multiplier applies to all exercises
    """
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    if not lines:
        return None

    exercises = []

    # Pattern for circuit format: 5x(...) or 5x[...]
    circuit_pattern = r"^(\d+)x\s*[\(\[](.+?)[\)\]]"

    # Pattern for individual exercise: "exercise name sets x reps @weight"
    # Supports: "8-10 pull ups @20kg", "10 dips", "15 db lateral raises @20"
    exercise_pattern = r"(\d+)(?:-\d+)?\s+(.+?)(?:\s*@\s*(\d+(?:\.\d+)?)\s*(?:kg)?)?$"

    # Alternative pattern: "exercise name NxM @weight" (traditional)
    traditional_pattern = r"^(.+?)\s+(\d+)x(failure|\d+)(?:-\d+)?\s*(?:@?\s*(\d+(?:\.\d+)?)\s*(?:kg|lbs?)?)?\s*(?:RPE\s*(\d+(?:\.\d+)?))?"

    for line in lines:
        # Skip rest notation lines
        if line.lower().startswith("r") and "'" in line:
            continue

        # Try circuit format first: 5x(exercise1, exercise2, ...)
        circuit_match = re.match(circuit_pattern, line, re.IGNORECASE)
        if circuit_match:
            num_rounds = int(circuit_match.group(1))
            circuit_content = circuit_match.group(2)

            # Split exercises by comma
            exercise_parts = [p.strip() for p in circuit_content.split(",")]

            for part in exercise_parts:
                # Parse each exercise in the circuit
                ex_match = re.match(exercise_pattern, part.strip(), re.IGNORECASE)
                if ex_match:
                    reps_str = ex_match.group(1)
                    name = ex_match.group(2).strip()
                    weight = float(ex_match.group(3)) if ex_match.group(3) else None

                    # Handle "failure" keyword
                    is_failure = "failure" in name.lower()
                    reps = None if is_failure else int(reps_str)
                    if is_failure:
                        name = name.replace("failure", "").strip()

                    exercise_id = _match_exercise_fuzzy(name)

                    sets = []
                    for i in range(num_rounds):
                        sets.append(
                            {
                                "set_number": i + 1,
                                "reps": reps,
                                "weight_kg": weight,
                                "rpe": None,
                                "is_warmup": False,
                                "is_failure": is_failure,
                            }
                        )

                    exercises.append(
                        {"name": name, "exercise_id": exercise_id, "sets": sets, "notes": None}
                    )
            continue

        # Try traditional format: "Bench press 4x8 80kg"
        match = re.match(traditional_pattern, line, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            num_sets = int(match.group(2))
            reps_str = match.group(3)
            is_failure = reps_str.lower() == "failure"
            reps = None if is_failure else int(reps_str)
            weight = float(match.group(4)) if match.group(4) else None
            rpe = float(match.group(5)) if match.group(5) else None

            # Check for lbs and convert
            if weight and "lbs" in line.lower():
                weight = round(weight * 0.453, 1)

            exercise_id = _match_exercise_fuzzy(name)

            sets = []
            for i in range(num_sets):
                sets.append(
                    {
                        "set_number": i + 1,
                        "reps": reps,
                        "weight_kg": weight,
                        "rpe": rpe if i == num_sets - 1 else None,
                        "is_warmup": False,
                        "is_failure": is_failure,
                    }
                )

            exercises.append(
                {"name": name, "exercise_id": exercise_id, "sets": sets, "notes": None}
            )

    if exercises:
        return exercises
    return None


def parse_workout_text(
    text: str, workout_date: date | None = None, use_llm: bool = True
) -> ParsedWorkout:
    """Parse workout text into structured data.

    Args:
        text: Free-form workout text
        workout_date: Date of workout (defaults to today)
        use_llm: Whether to use LLM for parsing (falls back to regex if False)

    Returns:
        ParsedWorkout with exercises and sets
    """
    if workout_date is None:
        workout_date = date.today()

    date_str = workout_date.isoformat()

    # Try simple parsing first (fast path)
    simple_result = _parse_simple_format(text)

    # If regex parser succeeded, use it directly (saves LLM tokens)
    # Only fall back to LLM if regex failed or use_llm is explicitly requested
    # and regex didn't find anything
    if simple_result:
        logger.info(f"Regex parser found {len(simple_result)} exercises, skipping LLM")
        return ParsedWorkout(
            date=workout_date,
            name=None,
            exercises=[
                ParsedExercise(
                    name=ex["name"],
                    exercise_id=ex["exercise_id"],
                    sets=[ParsedSet(**s) for s in ex["sets"]],
                    notes=ex["notes"],
                )
                for ex in simple_result
            ],
        )

    # Regex failed, try LLM if available
    if not use_llm:
        raise ValueError("Simple parsing failed and LLM is disabled")

    # Use LLM for complex parsing
    client = get_client()
    if not client:
        raise ValueError("GROQ_API_KEY not set and simple parsing failed")

    # Check token budget
    token_manager = get_token_manager()
    can_proceed, reason = token_manager.can_make_request(DEFAULT_MODEL, 800)
    if not can_proceed:
        raise ValueError(f"Token budget exceeded and simple parsing failed: {reason}")

    system_prompt, user_prompt = _build_parser_prompt(text, date_str)

    try:
        response = client.chat.completions.create(
            model=DEFAULT_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=800,
            temperature=0.1,  # Low temperature for consistent parsing
        )

        # Track token usage
        if response.usage:
            token_manager.record_usage(
                model=DEFAULT_MODEL,
                prompt_tokens=response.usage.prompt_tokens,
                completion_tokens=response.usage.completion_tokens,
            )

        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty response from LLM")

        # Parse JSON from response
        # Handle markdown code blocks
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]

        parsed = json.loads(content.strip())

        # Convert to dataclasses
        exercises = []
        for ex_data in parsed.get("exercises", []):
            sets = []
            for s in ex_data.get("sets", []):
                sets.append(
                    ParsedSet(
                        set_number=s.get("set_number", 1),
                        reps=s.get("reps"),  # None for failure sets
                        weight_kg=s.get("weight_kg"),
                        rpe=s.get("rpe"),
                        is_warmup=s.get("is_warmup", False),
                        is_failure=s.get("is_failure", False),
                    )
                )

            # Try to match exercise if LLM didn't
            exercise_id = ex_data.get("exercise_id")
            if not exercise_id:
                exercise_id = _match_exercise_fuzzy(ex_data.get("name", ""))

            exercises.append(
                ParsedExercise(
                    name=ex_data.get("name", "Unknown"),
                    exercise_id=exercise_id,
                    sets=sets,
                    notes=ex_data.get("notes"),
                )
            )

        return ParsedWorkout(
            date=workout_date,
            name=parsed.get("name"),
            exercises=exercises,
            duration_min=parsed.get("duration_min"),
            overall_rpe=parsed.get("overall_rpe"),
            notes=parsed.get("notes"),
        )

    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse LLM response as JSON: {e}")
        # Fallback to simple parsing
        if simple_result:
            return ParsedWorkout(
                date=workout_date,
                name=None,
                exercises=[
                    ParsedExercise(
                        name=ex["name"],
                        exercise_id=ex["exercise_id"],
                        sets=[ParsedSet(**s) for s in ex["sets"]],
                        notes=ex["notes"],
                    )
                    for ex in simple_result
                ],
            )
        raise ValueError(f"Failed to parse workout: {e}")
    except Exception as e:
        logger.error(f"Workout parsing error: {e}")
        raise
