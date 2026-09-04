"""Workout text parser: grammar first, LLM for what the grammar rejects.

Parses free-text workout logs into structured session data.
Example input:
    Bench press 4x8 80kg
    4x10 @60 incline db press r2'
    5x(8-10 pull ups @20kg, 15 dips) r1'30

Pipeline (see ``parse_workout_text``):
1. extract an optional leading date, normalize typos, expand user abbreviations;
2. parse every line with the Lark grammar (``arete.llm.workout_grammar``);
3. send only the lines the grammar rejected to the LLM (if enabled/available);
4. resolve exercise names against the catalog.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import date

from arete.data.exercises_catalog import EXERCISE_ALIASES, EXERCISES_CATALOG
from arete.llm.provider import get_default_model, get_llm_client
from arete.llm.workout_grammar import parse_workout_grammar, unparsed_lines

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


def _get_exercise_list_for_prompt() -> str:
    """Build compact exercise list for LLM context."""
    exercises = []
    for ex in EXERCISES_CATALOG[:50]:  # Limit to top 50 for token efficiency
        exercises.append(f"- {ex['id']}: {ex['name']} ({ex['name_fr']})")
    return "\n".join(exercises)


def _build_parser_prompt(
    workout_text: str,
    workout_date: str,
    abbreviations: dict[str, str] | None = None,
) -> tuple[str, str]:
    """Build system and user prompts for workout parsing."""

    exercise_list = _get_exercise_list_for_prompt()

    # Build abbreviations section for prompt
    abbrev_section = ""
    if abbreviations:
        abbrev_lines = "\n".join(f"  - {k} = {v}" for k, v in abbreviations.items())
        abbrev_section = f"""
USER ABBREVIATIONS (expand these in exercise names):
{abbrev_lines}
"""

    system_prompt = f"""Tu es un parser de séances de musculation/training. Tu dois extraire les exercices et sets d'un texte libre écrit en notation terse.

{abbrev_section}
EXERCICES CONNUS (utilise ces IDs quand possible):
{exercise_list}

FORMAT DE NOTATION DE L'UTILISATEUR:
Basique:
- Sets BEFORE exercise name: "2x8 @80 bench press" = 2 sets of 8 at 80kg bench press
- Traditional also works: "bench press 4x8 @80kg"
- "@weight" = weight in kg: "@80" = 80kg
- "@weighte" = weight EACH SIDE (unilateral machine): "shoulder press @50e" = 50kg per arm
- "e" after reps = each side: "10e db row" = 10 reps each side
- Rep range: "3x8-10" = 3 sets of 8 to 10 reps

Supersets & circuits:
- "Nx(exercise1, exercise2)" = superset: "10x(10 pull ups, 10 dips) r1'" = 10 rounds
- "4x(ex1, ex2) @weight r2'" = all exercises at same weight
- Different weights per exercise: "5x15e(cable extensions @5, cable pec fly @7.5)"
- "(exercise)" at END of another exercise's line = filler done DURING rest of that exercise
  Example: "4x8 t row @65 r1'30 (15e calves raises)" → t-row is main, calves during rest
  Return filler as separate exercise with notes: "filler during rest of t-row"
- "(exercise) NxM" on its OWN line = standalone finisher exercise, parse normally
  Example: "(dips) 3x amrap" → 3 sets of dips, reps: null, is_failure: true, notes: "finisher"
  IMPORTANT: everything the user writes was actually performed — never skip an exercise

Rep count variations:
- "(10,6,5) exercise @weight" = 3 sets of 10, 6, 5 reps at SAME weight
- Descending: "3@100, 1@105, 1@110 squat" = 3 sets with different weights
- Mixed: "4x8 @20, 3x8-10 @15, 2x10 @10, 1x amrap (pull ups, dips)" = different set schemes for SAME superset
- "2x5 @100, 2x6 @80, amrap@60 exercise" = mixed schemes same exercise

Drop sets & finishers:
- "N@w1 + N@w2 exercise" = drop set (no rest between): "10@20 + 10@14 db lateral raises"
  Return as ONE exercise with sets marked notes: "drop set"
- "+ amrap @weight" = finisher AMRAP at different weight: "3x5 @90 (+ amrap @60)"
  Return the AMRAP as an additional set with is_failure: true
- "amrap" or "N x amrap" = as many reps as possible: reps: null, is_failure: true

Pyramids:
- "pyramid @w1-w2-w3 amrap exercise" = pyramid weight, AMRAP each
- "+ reverse" = ascending then descending weight

Rest notation:
- "r1'30" = rest 1 min 30 sec
- "r2'" = rest 2 min
- "r'130" = TYPO for r1'30 (same meaning)
- "r0" or "no rest" = no rest between exercises

Cardio:
- "30' incline walk (13%, 4.5km/h)" = 30 min cardio with parameters
- "EF run 8.8km (5'53/km, 167 bpm)" = easy run with pace and HR
- "threshold run 3x8' @4'55-5'00 r2'" = running intervals
- "row erg 6x1' @1'28/500m r1'" = rowing intervals
- "6km treadmill run" = distance-based cardio
- Return cardio as exercise with name, notes with parameters, duration_min if available

Session labels:
- Lines like "pm : legs" or "am : EF run" are session context, use as session name
- "b&c" = back & chest, "sharms" = shoulders & arms, "mabs" = mobility & abs

Special:
- "1RM exercise @weight" = one rep max test
- "deload" = deload note, reduce weights
- "rattrapages : exercise" = exercises to catch up on (note only)
- "heavy street" or "street (exercises)" = calisthenics outdoor session

RÈGLES:
1. Retourne UNIQUEMENT du JSON valide, sans texte avant/après
2. EXPAND toutes les abréviations dans les noms d'exercices avant de retourner
3. Si l'exercice n'est pas dans la liste, utilise exercise_id: null et garde le nom COMPLET
4. Convertis les poids en kg si nécessaire (lbs → kg * 0.453)
5. Détecte les warmup sets (échauffement, warmup, w/)
6. Pour "failure", "amrap", "F": mets reps: null et is_failure: true
7. Pour les supersets "(ex1, ex2)", retourne chaque exercice séparément avec notes: "superset with <other>"
8. Pour les fillers "(exercise)" en fin de ligne d'un AUTRE exercice → exercice séparé avec notes: "filler during rest"
   Pour les "(exercise) NxM" sur une ligne SEULE → exercice finisher normal, notes: "finisher". Ne jamais ignorer un exercice.
9. Pour les drop sets "N@w1 + N@w2", un seul exercice avec tous les sets et notes: "drop set"
10. Pour "@weighte", stocke le poids par coté et ajoute notes: "weight per side"

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
        {{"set_number": 2, "reps": null, "weight_kg": null, "rpe": null, "is_warmup": false, "is_failure": true}}
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

    # Pattern: DD/MM/YY: or DD/MM/YYYY: at start of text, optionally followed
    # by the first exercise on the same line ("05/12/25: Bench press 4x8 80kg")
    date_pattern = r"^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\s*:?\s*(.*)$"
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
            # Return text without the date prefix
            rest_of_line = match.group(4).strip()
            remaining_lines = ([rest_of_line] if rest_of_line else []) + lines[1:]
            return extracted_date, "\n".join(remaining_lines)
        except ValueError:
            pass  # Invalid date, continue with original text

    return None, text


def _normalize_workout_text(text: str) -> str:
    """Normalize common typos and shorthand in workout text.

    Fixes:
    - r'130 → r1'30 (rest typo: apostrophe before digits)
    - r'230 → r2'30
    - Curly/smart quotes → straight quotes
    """
    result = text
    # Normalize smart quotes to straight
    result = result.replace("\u2019", "'").replace("\u2018", "'")

    # Fix rest typo: r'NNN → rN'NN (3+ digit rest after apostrophe)
    # e.g., r'130 → r1'30, r'230 → r2'30
    result = re.sub(
        r"\br'(\d)(\d{2})\b",
        r"r\1'\2",
        result,
    )

    return result


def _expand_abbreviations(text: str, abbreviations: dict[str, str]) -> str:
    """Expand user abbreviations in workout text.

    Uses word-boundary matching to avoid partial replacements.
    Longer abbreviations are expanded first to prevent conflicts.
    """
    if not abbreviations:
        return text

    result = text
    # Sort by length descending to expand longer abbreviations first
    for abbrev, full in sorted(
        abbreviations.items(), key=lambda x: len(x[0]), reverse=True
    ):
        pattern = r"\b" + re.escape(abbrev) + r"\b"
        result = re.sub(pattern, full, result, flags=re.IGNORECASE)
    return result


def _parse_with_llm(
    text: str, date_str: str, abbreviations: dict[str, str] | None
) -> tuple[list[ParsedExercise], dict] | None:
    """Ask the LLM to structure ``text``. Returns (exercises, session_meta) or None."""
    client = get_llm_client()
    if not client:
        return None
    try:
        system_prompt, user_prompt = _build_parser_prompt(
            text, date_str, abbreviations=abbreviations
        )
        response = client.chat.completions.create(
            model=get_default_model(),
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            max_tokens=1200,
            temperature=0.1,  # Low temperature for consistent parsing
        )
        content = response.choices[0].message.content
        if not content:
            raise ValueError("Empty response from LLM")

        # Strip markdown fences and common JSON slips
        if "```json" in content:
            content = content.split("```json")[1].split("```")[0]
        elif "```" in content:
            content = content.split("```")[1].split("```")[0]
        content = re.sub(r",(\s*[}\]])", r"\1", content.strip())
        content_lines = content.split("\n")
        while content_lines and not content_lines[-1].strip().endswith(
            ("}", "]", '"', ",")
        ):
            content_lines.pop()
        parsed = json.loads("\n".join(content_lines).strip())

        exercises = []
        for ex_data in parsed.get("exercises", []):
            sets = [
                ParsedSet(
                    set_number=st.get("set_number", 1),
                    reps=st.get("reps"),
                    weight_kg=st.get("weight_kg"),
                    rpe=st.get("rpe"),
                    is_warmup=st.get("is_warmup", False),
                    is_failure=st.get("is_failure", False),
                )
                for st in ex_data.get("sets", [])
            ]
            name = ex_data.get("name", "Unknown")
            exercises.append(
                ParsedExercise(
                    name=name,
                    exercise_id=ex_data.get("exercise_id")
                    or _match_exercise_fuzzy(name),
                    sets=sets,
                    notes=ex_data.get("notes"),
                )
            )
        meta = {
            "name": parsed.get("name"),
            "duration_min": parsed.get("duration_min"),
            "overall_rpe": parsed.get("overall_rpe"),
            "notes": parsed.get("notes"),
        }
        return exercises, meta
    except (json.JSONDecodeError, ValueError, KeyError) as e:
        logger.warning(f"LLM parsing failed ({e})")
    except Exception as e:
        logger.warning(f"LLM unavailable ({e})")
    return None


def parse_workout_text(
    text: str,
    workout_date: date | None = None,
    use_llm: bool = True,
    abbreviations: dict[str, str] | None = None,
) -> ParsedWorkout:
    """Parse workout text into structured data.

    Grammar first (deterministic, see ``workout_grammar``); the LLM is only
    asked about the lines the grammar rejects, and only when ``use_llm`` is
    true and a provider is configured.

    Args:
        text: Free-form workout text (can start with a date like "05/12/25:")
        workout_date: Date of workout (defaults to extracted date or today)
        use_llm: Whether the LLM may be used for unparseable lines
        abbreviations: User-defined abbreviation mapping (e.g. {"bp": "bench press"})

    Raises:
        ValueError: when no exercise could be extracted at all.
    """
    extracted_date, text = _extract_date_from_text(text)
    if workout_date is None:
        workout_date = extracted_date or date.today()

    text = _expand_abbreviations(_normalize_workout_text(text), abbreviations or {})

    exercises: list[ParsedExercise] = [
        ParsedExercise(
            name=ex["name"],
            exercise_id=ex["exercise_id"] or _match_exercise_fuzzy(ex["name"]),
            sets=[ParsedSet(**st) for st in ex["sets"]],
            notes=ex["notes"],
            target_reps=ex["target_reps"],
        )
        for ex in parse_workout_grammar(text) or []
    ]
    leftovers = unparsed_lines(text)
    if exercises:
        logger.info(
            f"Grammar parsed {len(exercises)} exercises, {len(leftovers)} line(s) left"
        )

    meta: dict = {}
    if leftovers and use_llm:
        llm_result = _parse_with_llm(
            "\n".join(leftovers), workout_date.isoformat(), abbreviations
        )
        if llm_result:
            llm_exercises, meta = llm_result
            logger.info(f"LLM parsed {len(llm_exercises)} exercises from leftovers")
            exercises.extend(llm_exercises)
        else:
            logger.info(f"Unparsed lines kept out of the session: {leftovers}")

    if not exercises:
        raise ValueError("Failed to parse workout text: no exercises found")

    return ParsedWorkout(
        date=workout_date,
        name=meta.get("name"),
        exercises=exercises,
        duration_min=meta.get("duration_min"),
        overall_rpe=meta.get("overall_rpe"),
        notes=meta.get("notes"),
    )
