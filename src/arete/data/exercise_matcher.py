"""Semantic matching of free-text exercise names against the catalog.

Deterministic and dependency-light (rapidfuzz). Replaces the LLM fallback of the
workout parser: when a name is not an exact alias, we return the closest catalog
entries with a score so the UI can auto-accept confident matches and propose
the rest to the user.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz, process

from arete.data.exercises_catalog import (
    EXERCISE_ALIASES,
    EXERCISES_BY_ID,
    EXERCISES_CATALOG,
)

# Score (0-100) above which a match is accepted without asking the user.
ACCEPT_SCORE = 88
# Below this score we do not even suggest.
SUGGEST_SCORE = 60
MAX_SUGGESTIONS = 3

# Common shorthand expanded before matching (word-boundary, case-insensitive).
_SHORTHAND = [
    (r"\bdb\b", "dumbbell"),
    (r"\bbb\b", "barbell"),
    (r"\bkb\b", "kettlebell"),
    (r"\bohp\b", "shoulder press"),
    (r"\brdl\b", "romanian deadlift"),
    (r"\bsldl\b", "stiff leg deadlift"),
    (r"\bbss\b", "bulgarian split squat"),
    (r"\bpulls? ups?\b", "pull ups"),
    (r"\bchin ups?\b", "chin ups"),
    (r"\bdips?\b", "dips"),
    (r"\bpush ups?\b", "push ups"),
]


@dataclass
class Suggestion:
    exercise_id: str
    name: str
    score: int


@dataclass
class ExerciseMatch:
    exercise_id: str | None
    score: int
    suggestions: list[Suggestion] = field(default_factory=list)

    @property
    def matched(self) -> bool:
        return self.exercise_id is not None


def normalize_name(raw: str) -> str:
    text = raw.lower().strip()
    text = re.sub(r"[_\-]+", " ", text)
    for pattern, replacement in _SHORTHAND:
        text = re.sub(pattern, replacement, text)
    return re.sub(r"\s+", " ", text).strip()


def _candidates() -> dict[str, str]:
    """Searchable label -> exercise id (names, French names, aliases)."""
    labels: dict[str, str] = {}
    for ex in EXERCISES_CATALOG:
        labels[ex["name"].lower()] = ex["id"]
        labels[ex["name_fr"].lower()] = ex["id"]
        labels[ex["id"].replace("_", " ")] = ex["id"]
    for alias, ex_id in EXERCISE_ALIASES.items():
        labels.setdefault(alias.lower(), ex_id)
    return labels


_LABELS = _candidates()
_LABEL_LIST = list(_LABELS)


def match_exercise(raw_name: str) -> ExerciseMatch:
    """Best catalog match for a free-text exercise name."""
    if not raw_name or not raw_name.strip():
        return ExerciseMatch(None, 0)

    lowered = raw_name.lower().strip()
    normalized = normalize_name(raw_name)

    # 1. exact alias / name (either spelling)
    for key in (lowered, normalized):
        if key in _LABELS:
            ex_id = _LABELS[key]
            return ExerciseMatch(ex_id, 100, [_suggestion(ex_id, 100)])

    # 2. fuzzy: token-based so word order and extra qualifiers matter little
    results = process.extract(
        normalized,
        _LABEL_LIST,
        scorer=fuzz.token_set_ratio,
        limit=12,
    )
    best_by_id: dict[str, int] = {}
    for label, score, _ in results:
        ex_id = _LABELS[label]
        if int(score) > best_by_id.get(ex_id, -1):
            best_by_id[ex_id] = int(score)
    ranked = sorted(best_by_id.items(), key=lambda kv: -kv[1])
    suggestions = [
        _suggestion(ex_id, score)
        for ex_id, score in ranked[:MAX_SUGGESTIONS]
        if score >= SUGGEST_SCORE
    ]
    if suggestions and suggestions[0].score >= ACCEPT_SCORE:
        return ExerciseMatch(
            suggestions[0].exercise_id, suggestions[0].score, suggestions
        )
    return ExerciseMatch(None, suggestions[0].score if suggestions else 0, suggestions)


def _suggestion(ex_id: str, score: int) -> Suggestion:
    return Suggestion(ex_id, EXERCISES_BY_ID[ex_id]["name"], score)
