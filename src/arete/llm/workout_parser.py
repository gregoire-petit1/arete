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
import re
from dataclasses import dataclass
from datetime import date
from typing import Any

from arete.data.exercises_catalog import EXERCISES_CATALOG, EXERCISE_ALIASES
from arete.llm.provider import get_default_model, get_llm_client

logger = logging.getLogger(__name__)


@dataclass
class ParsedSet:
    """A parsed set from workout text."""

    set_number: int
    reps: int | None = None  # None for failure sets
    weight_kg: float | None = None
    rpe: float | None = None
    is_warmup: bool = False
    is_failure: bool = False
    rest_sec: int | None = None  # Rest time after set (parsed from r2', r1'30)


@dataclass
class ParsedExercise:
    """A parsed exercise from workout text."""

    name: str
    exercise_id: str | None  # Matched ID from catalog
    sets: list[ParsedSet]
    notes: str | None = None
    target_reps: str | None = None  # Rep range like "8-10" or "5"


@dataclass
class ParsedWorkout:
    """Complete parsed workout."""

    date: date
    name: str | None
    exercises: list[ParsedExercise]
    duration_min: int | None = None
    overall_rpe: float | None = None
    notes: str | None = None


def get_client():
    """Get LLM client via provider abstraction."""
    return get_llm_client()


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

    # First check EXERCISE_ALIASES dictionary
    if name_lower in EXERCISE_ALIASES:
        return EXERCISE_ALIASES[name_lower]

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


def _extract_date_from_text(text: str) -> tuple[date | None, str]:
    """Extract date from beginning of workout text.

    Supports formats:
    - "05/12/25:" or "05/12/2025:" (DD/MM/YY or DD/MM/YYYY)
    - "2025-12-05:" (ISO format)
    - "05-12-25:" (DD-MM-YY)

    Returns:
        Tuple of (extracted_date or None, text_without_date_line)
    """
    lines = text.strip().split("\n")
    if not lines:
        return None, text

    first_line = lines[0].strip()

    # Pattern: DD/MM/YY: or DD/MM/YYYY: at start of text
    date_pattern = r"^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*:?\s*$"
    match = re.match(date_pattern, first_line)

    if match:
        day = int(match.group(1))
        month = int(match.group(2))
        year = int(match.group(3))

        # Handle 2-digit years
        if year < 100:
            year += 2000 if year < 50 else 1900

        try:
            extracted_date = date(year, month, day)
            # Return text without the date line
            remaining_text = "\n".join(lines[1:])
            return extracted_date, remaining_text
        except ValueError:
            pass  # Invalid date, continue with original text

    return None, text


def _parse_simple_format(text: str) -> list[dict] | None:
    """Try to parse simple formats without LLM (fallback/fast path).

    Formats supported:
    - "Bench press 4x8 80kg"
    - "Squat 3x5 @100kg RPE 8"
    - "Pull ups 4x10"
    - "Dips 3x failure" or "Dips 3xfailure"
    - "Pull ups 4xF" or "Dips 3xAMRAP" (failure notation)
    - Circuit format: "5x(8 pull ups @20kg, 10 dips) r2'" - with rest time
    - Descending sets: "3@100, 1@105, 1@110 bench press"
    - Notation with "e" for each side: "15e db row"
    - EMOM format: "EMOM 20' (odd: 10 pull ups, even: 10 chin ups)"
    """
    lines = [l.strip() for l in text.strip().split("\n") if l.strip()]
    if not lines:
        return None

    exercises: list[dict] = []
    pending_rest_sec: int | None = None  # Rest time to apply to previous exercise

    # Pattern for circuit format: 5x(...) or 5x[...] with optional rest r2' or r1'30
    circuit_pattern = r"^(\d+)x\s*[\(\[](.+?)[\)\]](?:\s*r(\d+)'(\d+)?)?$"

    # Pattern for rest time notation: r2' or r1'30 or r'130 (typo) (standalone on a line)
    rest_pattern = r"^r'?(\d+)'?(\d+)?$"

    # Pattern for individual exercise in circuit: "8-10 pull ups @20kg", "10e dips", "15 db lateral raises @20"
    # Now supports "e" suffix for each side (unilateral)
    exercise_pattern = (
        r"(\d+)(?:-(\d+))?e?\s+(.+?)(?:\s*@\s*(\d+(?:\.\d+)?)\s*(?:kg)?)?$"
    )

    # Alternative pattern: "exercise name NxM @weight" (traditional)
    # Supports: "Pull ups 4x8", "Dips 3xF", "Bench 4x8-10 @80kg", "Rows 3xAMRAP", "5x20 leg raises"
    # Name must not contain @ to avoid matching mixed format lines
    traditional_pattern = r"^([^@]+?)\s+(\d+)x(F|f|failure|AMRAP|amrap|\d+)(?:-(\d+))?e?\s*(?:@?\s*(\d+(?:\.\d+)?)\s*(?:kg|lbs?)?)?\s*(?:RPE\s*(\d+(?:\.\d+)?))?\s*(?:r(\d+)'(\d+)?)?$"

    # Reversed pattern: "5x20 leg raises" (sets x reps before exercise name)
    reversed_pattern = r"^(\d+)x(\d+)(?:-(\d+))?e?\s+(.+?)(?:\s*@?\s*(\d+(?:\.\d+)?)\s*(?:kg|lbs?)?)?\s*(?:r(\d+)'(\d+)?)?$"

    # Descending/pyramid pattern: "3@100, 1@105, 1@110 bench press" or "6@80kg, 4@100kg bench"
    descending_pattern = r"^((?:\d+@\d+(?:\.\d+)?(?:kg)?,?\s*)+)\s*(.+?)(?:\s*r(\d+)'(\d+)?)?(?:\s*[-–]\s*rpe\s*[\d.-]+)?$"

    # EMOM pattern: "EMOM 20' (odd: 10 pull ups, even: 10 chin ups)"
    emom_pattern = r"^EMOM\s*(\d+)['\"]?\s*\((.+)\)$"
    # Colon-separated: "bench press : 6@80kg, 4@100kg, 2x1@110kg r2'30"
    # Name : sets_part rest rpe
    colon_pattern = (
        r"^(.+?)\s*:\s*(.+?)(?:\s*r(\d+)'(\d+)?)?(?:\s*[-–]\s*rpe\s*[\d.-]+)?$"
    )

    # Mixed sets pattern for parsing "6@80kg, 4@100, 2x8@100, 3x1@110" etc.
    mixed_set_pattern = r"(\d+)(?:x(\d+))?@(\d+(?:\.\d+)?)(?:kg)?"
    for line in lines:
        # Skip empty lines or pure cardio descriptions
        if not line or line.startswith("25'") or "/km" in line or "/500m" in line:
            continue

        # Skip cardio interval format: "5x1'@1'35/500m row erg"
        if re.search(r"\d+x\d+'@", line) or re.search(r"\d+'\d+/500m", line):
            continue

        # Check for standalone rest notation: r2' or r1'30 or r'130
        rest_match = re.match(rest_pattern, line.lower().replace("'", "'"))
        if rest_match:
            minutes = int(rest_match.group(1))
            seconds = int(rest_match.group(2)) if rest_match.group(2) else 0
            pending_rest_sec = minutes * 60 + seconds
            # Apply to last set of previous exercise
            if exercises and exercises[-1]["sets"]:
                exercises[-1]["sets"][-1]["rest_sec"] = pending_rest_sec
            continue

        # Try circuit format first: 5x(exercise1, exercise2, ...) r2'
        circuit_match = re.match(circuit_pattern, line, re.IGNORECASE)
        if circuit_match:
            num_rounds = int(circuit_match.group(1))
            circuit_content = circuit_match.group(2)
            rest_min = circuit_match.group(3)
            rest_sec_extra = circuit_match.group(4)

            # Calculate rest time between rounds
            circuit_rest_sec = None
            if rest_min:
                circuit_rest_sec = int(rest_min) * 60
                if rest_sec_extra:
                    circuit_rest_sec += int(rest_sec_extra)

            # Split exercises by comma
            exercise_parts = [p.strip() for p in circuit_content.split(",")]

            for part in exercise_parts:
                # Parse each exercise in the circuit
                ex_match = re.match(exercise_pattern, part.strip(), re.IGNORECASE)
                if ex_match:
                    reps_min_str = ex_match.group(1)
                    reps_max_str = ex_match.group(2)  # For range like 8-10
                    name = ex_match.group(3).strip()
                    weight = float(ex_match.group(4)) if ex_match.group(4) else None

                    # Handle "failure" keyword in name
                    is_failure = "failure" in name.lower() or "amrap" in name.lower()
                    reps = None if is_failure else int(reps_min_str)
                    if is_failure:
                        name = re.sub(
                            r"\b(failure|amrap)\b", "", name, flags=re.IGNORECASE
                        ).strip()

                    # Build target_reps string (e.g., "8-10" or "8")
                    circuit_target_reps: str | None = reps_min_str
                    if reps_max_str:
                        circuit_target_reps = f"{reps_min_str}-{reps_max_str}"

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
                                "rest_sec": circuit_rest_sec
                                if i < num_rounds - 1
                                else None,
                            }
                        )

                    exercises.append(
                        {
                            "name": name,
                            "exercise_id": exercise_id,
                            "sets": sets,
                            "notes": None,
                            "target_reps": circuit_target_reps,
                        }
                    )
            continue

        # Try traditional format: "Bench press 4x8 80kg" or "Pull ups 4xF" or "Dips 3x8-10"
        match = re.match(traditional_pattern, line, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            num_sets = int(match.group(2))
            reps_str = match.group(3)
            reps_max_str = match.group(4)  # For range like 8-10
            weight = float(match.group(5)) if match.group(5) else None
            rpe = float(match.group(6)) if match.group(6) else None
            rest_min = match.group(7)
            rest_sec_extra = match.group(8)

            # Check for failure notation: F, f, failure, AMRAP
            is_failure = reps_str.lower() in ("f", "failure", "amrap")
            reps = None if is_failure else int(reps_str)

            # Build target_reps string
            target_reps: str | None = None
            if not is_failure:
                target_reps = reps_str
                if reps_max_str:
                    target_reps = f"{reps_str}-{reps_max_str}"

            # Calculate rest time
            rest_sec = None
            if rest_min:
                rest_sec = int(rest_min) * 60
                if rest_sec_extra:
                    rest_sec += int(rest_sec_extra)

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
                        "rest_sec": rest_sec if i < num_sets - 1 else None,
                    }
                )

            exercises.append(
                {
                    "name": name,
                    "exercise_id": exercise_id,
                    "sets": sets,
                    "notes": None,
                    "target_reps": target_reps,
                }
            )
            continue

        # Try reversed format: "5x20 leg raises"
        reversed_match = re.match(reversed_pattern, line, re.IGNORECASE)
        if reversed_match:
            num_sets = int(reversed_match.group(1))
            reps_str = reversed_match.group(2)
            reps_max_str = reversed_match.group(3)
            name = reversed_match.group(4).strip()
            weight = float(reversed_match.group(5)) if reversed_match.group(5) else None
            rest_min = reversed_match.group(6)
            rest_sec_extra = reversed_match.group(7)

            reps = int(reps_str)
            target_reps = reps_str
            if reps_max_str:
                target_reps = f"{reps_str}-{reps_max_str}"

            rest_sec = None
            if rest_min:
                rest_sec = int(rest_min) * 60
                if rest_sec_extra:
                    rest_sec += int(rest_sec_extra)

            exercise_id = _match_exercise_fuzzy(name)

            sets = []
            for i in range(num_sets):
                sets.append(
                    {
                        "set_number": i + 1,
                        "reps": reps,
                        "weight_kg": weight,
                        "rpe": None,
                        "is_warmup": False,
                        "is_failure": False,
                        "rest_sec": rest_sec if i < num_sets - 1 else None,
                    }
                )

            exercises.append(
                {
                    "name": name,
                    "exercise_id": exercise_id,
                    "sets": sets,
                    "notes": None,
                    "target_reps": target_reps,
                }
            )
            continue

        # Try descending/pyramid pattern: "3@100, 1@105, 1@110 bench press r2'"
        descending_match = re.match(descending_pattern, line, re.IGNORECASE)
        if descending_match:
            sets_part = descending_match.group(1)
            name = descending_match.group(2).strip()
            rest_min = descending_match.group(3)
            rest_sec_extra = descending_match.group(4)

            # Parse individual sets: "3@100, 1@105, 1@110"
            set_pattern = r"(\d+)@(\d+(?:\.\d+)?)"
            set_matches = re.findall(set_pattern, sets_part)

            if set_matches:
                rest_sec = None
                if rest_min:
                    rest_sec = int(rest_min) * 60
                    if rest_sec_extra:
                        rest_sec += int(rest_sec_extra)

                exercise_id = _match_exercise_fuzzy(name)
                sets = []
                set_number = 1

                for reps_str, weight_str in set_matches:
                    sets.append(
                        {
                            "set_number": set_number,
                            "reps": int(reps_str),
                            "weight_kg": float(weight_str),
                            "rpe": None,
                            "is_warmup": False,
                            "is_failure": False,
                            "rest_sec": rest_sec,
                        }
                    )
                    set_number += 1

                exercises.append(
                    {
                        "name": name,
                        "exercise_id": exercise_id,
                        "sets": sets,
                        "notes": None,
                        "target_reps": None,
                    }
                )
                continue

        # Try EMOM pattern: "EMOM 20' (odd: 10 pull ups, even: 10 chin ups)"
        emom_match = re.match(emom_pattern, line, re.IGNORECASE)
        if emom_match:
            duration_min = int(emom_match.group(1))
            content = emom_match.group(2)

            # Parse "odd: X exercise, even: Y exercise"
            parts = re.split(r",\s*", content)
            for part in parts:
                # Match "odd: 10 pull ups" or "even: 10 chin ups"
                part_match = re.match(
                    r"(?:odd|even):\s*(\d+)\s+(.+)", part.strip(), re.IGNORECASE
                )
                if part_match:
                    reps = int(part_match.group(1))
                    name = part_match.group(2).strip()
                    exercise_id = _match_exercise_fuzzy(name)

                    # EMOM: half the minutes = number of sets for each exercise
                    num_sets = duration_min // 2

                    sets = []
                    for i in range(num_sets):
                        sets.append(
                            {
                                "set_number": i + 1,
                                "reps": reps,
                                "weight_kg": None,
                                "rpe": None,
                                "is_warmup": False,
                                "is_failure": False,
                                "rest_sec": 60,  # EMOM = every minute
                            }
                        )

                    exercises.append(
                        {
                            "name": name,
                            "exercise_id": exercise_id,
                            "sets": sets,
                            "notes": f"EMOM {duration_min}'",
                            "target_reps": str(reps),
                        }
                    )
            continue

        # Try colon-separated format: "bench press : 6@80kg, 4@100kg, 2x1@110kg r2'30"
        colon_match = re.match(colon_pattern, line, re.IGNORECASE)
        if colon_match:
            name = colon_match.group(1).strip()
            sets_part = colon_match.group(2).strip()
            rest_min = colon_match.group(3)
            rest_sec_extra = colon_match.group(4)

            rest_sec = None
            if rest_min:
                rest_sec = int(rest_min) * 60
                if rest_sec_extra:
                    rest_sec += int(rest_sec_extra)

            exercise_id = _match_exercise_fuzzy(name)

            # Parse mixed sets: "6@80kg, 4@100kg, 2x1@110kg" or "10@90, 2x8@100"
            sets = []
            set_number = 1

            # Split by comma OR space before a digit followed by x or @
            set_parts = re.split(r",\s*|\s+(?=\d+[x@])", sets_part)
            for part in set_parts:
                # Try "NxM@weight" format (e.g., "3x1@110" or "2x8@100")
                nxm_match = re.match(r"(\d+)x(\d+)@(\d+(?:\.\d+)?)", part.strip())
                if nxm_match:
                    num_sets = int(nxm_match.group(1))
                    reps = int(nxm_match.group(2))
                    weight = float(nxm_match.group(3))
                    for _ in range(num_sets):
                        sets.append(
                            {
                                "set_number": set_number,
                                "reps": reps,
                                "weight_kg": weight,
                                "rpe": None,
                                "is_warmup": False,
                                "is_failure": False,
                                "rest_sec": rest_sec if set_number == 1 else None,
                            }
                        )
                        set_number += 1
                    continue

                # Try "N@weight" format (e.g., "6@80kg" or "4@100")
                single_match = re.match(r"(\d+)@(\d+(?:\.\d+)?)", part.strip())
                if single_match:
                    reps = int(single_match.group(1))
                    weight = float(single_match.group(2))
                    sets.append(
                        {
                            "set_number": set_number,
                            "reps": reps,
                            "weight_kg": weight,
                            "rpe": None,
                            "is_warmup": False,
                            "is_failure": False,
                            "rest_sec": rest_sec if set_number == 1 else None,
                        }
                    )
                    set_number += 1

            if sets:
                exercises.append(
                    {
                        "name": name,
                        "exercise_id": exercise_id,
                        "sets": sets,
                        "notes": None,
                        "target_reps": None,
                    }
                )
                continue

        # Try mixed format without colon: "horizontal pull 10@90, 2x8@100kg r1'30"
        # Exercise name (letters/spaces) followed by sets in N@weight format
        mixed_match = re.match(
            r"^([a-zA-Z][a-zA-Z\s]+?)\s+(\d+@\d+(?:\.\d+)?(?:kg)?(?:[,\s]+(?:\d+x)?\d+@\d+(?:\.\d+)?(?:kg)?)*)\s*(?:r(\d+)'(\d+)?)?$",
            line,
            re.IGNORECASE,
        )
        if mixed_match:
            name = mixed_match.group(1).strip()
            sets_part = mixed_match.group(2).strip()
            rest_min = mixed_match.group(3)
            rest_sec_extra = mixed_match.group(4)

            rest_sec = None
            if rest_min:
                rest_sec = int(rest_min) * 60
                if rest_sec_extra:
                    rest_sec += int(rest_sec_extra)

            exercise_id = _match_exercise_fuzzy(name)

            sets = []
            set_number = 1

            # Split by comma OR space before a digit followed by x or @
            set_parts = re.split(r",\s*|\s+(?=\d+[x@])", sets_part)
            for part in set_parts:
                # Try "NxM@weight" format
                nxm_match = re.match(r"(\d+)x(\d+)@(\d+(?:\.\d+)?)", part.strip())
                if nxm_match:
                    num_sets = int(nxm_match.group(1))
                    reps = int(nxm_match.group(2))
                    weight = float(nxm_match.group(3))
                    for _ in range(num_sets):
                        sets.append(
                            {
                                "set_number": set_number,
                                "reps": reps,
                                "weight_kg": weight,
                                "rpe": None,
                                "is_warmup": False,
                                "is_failure": False,
                                "rest_sec": rest_sec if set_number == 1 else None,
                            }
                        )
                        set_number += 1
                    continue

                # Try "N@weight" format
                single_match = re.match(r"(\d+)@(\d+(?:\.\d+)?)", part.strip())
                if single_match:
                    reps = int(single_match.group(1))
                    weight = float(single_match.group(2))
                    sets.append(
                        {
                            "set_number": set_number,
                            "reps": reps,
                            "weight_kg": weight,
                            "rpe": None,
                            "is_warmup": False,
                            "is_failure": False,
                            "rest_sec": rest_sec if set_number == 1 else None,
                        }
                    )
                    set_number += 1

            if sets:
                exercises.append(
                    {
                        "name": name,
                        "exercise_id": exercise_id,
                        "sets": sets,
                        "notes": None,
                        "target_reps": None,
                    }
                )
                continue

    if exercises:
        return exercises
    return None


def parse_workout_text(
    text: str, workout_date: date | None = None, use_llm: bool = True
) -> ParsedWorkout:
    """Parse workout text into structured data.

    Args:
        text: Free-form workout text (can start with date like "05/12/25:")
        workout_date: Date of workout (defaults to extracted date or today)
        use_llm: Whether to use LLM for parsing (falls back to regex if False)

    Returns:
        ParsedWorkout with exercises and sets
    """
    # Try to extract date from text if not provided
    extracted_date, cleaned_text = _extract_date_from_text(text)

    if workout_date is None:
        workout_date = extracted_date or date.today()

    # Use cleaned text (without date line) for parsing
    text = cleaned_text

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
        raise ValueError("LLM not configured and simple parsing failed")

    model = get_default_model()
    system_prompt, user_prompt = _build_parser_prompt(text, date_str)

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=800,
            temperature=0.1,  # Low temperature for consistent parsing
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

        # Clean up common LLM issues
        content = content.strip()
        # Remove trailing commas before } or ]
        content = re.sub(r",(\s*[}\]])", r"\1", content)
        # Fix unterminated strings by removing incomplete lines at end
        lines = content.split("\n")
        while lines and not lines[-1].strip().endswith(("}", "]", '"', ",")):
            lines.pop()
        content = "\n".join(lines)

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
