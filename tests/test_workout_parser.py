"""Tests for workout_parser regex fallback, normalize, and abbreviation expansion."""

from __future__ import annotations

from datetime import date

import pytest

from arete.llm.workout_parser import (
    _expand_abbreviations,
    _normalize_workout_text,
    _parse_simple_format,
    parse_workout_text,
)


# ─── Helper ──────────────────────────────────────────────────────────


def _names(exercises: list[dict]) -> list[str]:
    """Extract exercise names from parsed result."""
    return [e["name"] for e in exercises]


def _first(exercises: list[dict]) -> dict:
    return exercises[0]


# ─── _normalize_workout_text ─────────────────────────────────────────


class TestNormalize:
    def test_smart_quotes_to_straight(self):
        # \u2019 (right single quote) → straight apostrophe
        assert _normalize_workout_text("r1\u201930") == "r1'30"

    def test_rest_typo_r_apostrophe_130(self):
        assert _normalize_workout_text("r'130") == "r1'30"

    def test_rest_typo_r_apostrophe_230(self):
        assert _normalize_workout_text("r'230") == "r2'30"

    def test_no_false_positive_on_normal_rest(self):
        assert _normalize_workout_text("r1'30") == "r1'30"


# ─── _expand_abbreviations ──────────────────────────────────────────


class TestExpandAbbreviations:
    ABBREVS = {
        "bp": "bench press",
        "ohp": "overhead press",
        "db": "dumbbell",
        "inc": "incline",
        "rdl": "romanian deadlift",
        "bss": "bulgarian split squat",
        "lat pd": "lat pulldown",
        "wg": "wide grip",
        "pec glued": "pec deck",
        "cgbp": "close grip bench press",
    }

    def test_simple_expansion(self):
        assert "bench press" in _expand_abbreviations("4x8 bp @80", self.ABBREVS)

    def test_multi_word_abbreviation(self):
        result = _expand_abbreviations("3x12 lat pd wg @45", self.ABBREVS)
        assert "lat pulldown" in result
        assert "wide grip" in result

    def test_longer_abbreviation_first(self):
        """'cgbp' should not be partially matched as 'bp'."""
        result = _expand_abbreviations("3x8 cgbp @60", self.ABBREVS)
        assert "close grip bench press" in result

    def test_case_insensitive(self):
        result = _expand_abbreviations("4x8 BP @80", self.ABBREVS)
        assert "bench press" in result

    def test_empty_abbreviations(self):
        assert _expand_abbreviations("4x8 bp @80", {}) == "4x8 bp @80"

    def test_no_partial_match(self):
        """'bp' should not match inside 'bps' or 'abp'."""
        result = _expand_abbreviations("bps and bp", {"bp": "bench press"})
        assert result == "bps and bench press"


# ─── _parse_simple_format: traditional pattern ──────────────────────


class TestTraditionalPattern:
    """'Exercise NxM @weight' format."""

    def test_basic(self):
        result = _parse_simple_format("Bench press 4x8 80kg")
        assert result is not None
        assert len(result) == 1
        ex = _first(result)
        assert ex["name"].lower() == "bench press"
        assert len(ex["sets"]) == 4
        assert ex["sets"][0]["reps"] == 8
        assert ex["sets"][0]["weight_kg"] == 80.0

    def test_failure_notation(self):
        result = _parse_simple_format("Dips 3xF")
        assert result is not None
        ex = _first(result)
        assert len(ex["sets"]) == 3
        assert ex["sets"][0]["reps"] is None
        assert ex["sets"][0]["is_failure"] is True

    def test_amrap(self):
        result = _parse_simple_format("Pull ups 4xamrap")
        assert result is not None
        ex = _first(result)
        assert ex["sets"][0]["is_failure"] is True
        assert ex["sets"][0]["reps"] is None

    def test_with_rpe(self):
        result = _parse_simple_format("Squat 3x5 @100kg RPE 8")
        assert result is not None
        ex = _first(result)
        assert ex["sets"][-1]["rpe"] == 8.0

    def test_rep_range(self):
        result = _parse_simple_format("Dips 3x8-10")
        assert result is not None
        ex = _first(result)
        assert ex["target_reps"] == "8-10"
        assert ex["sets"][0]["reps"] == 8


# ─── _parse_simple_format: terse pattern ────────────────────────────


class TestTersePattern:
    """'NxM @weight exercise' format (user's preferred notation)."""

    def test_basic_terse(self):
        result = _parse_simple_format("4x8 @80 bench press")
        assert result is not None
        ex = _first(result)
        assert ex["name"].lower() == "bench press"
        assert len(ex["sets"]) == 4
        assert ex["sets"][0]["weight_kg"] == 80.0

    def test_terse_with_rest(self):
        result = _parse_simple_format("4x10 @60 incline db press r2'")
        assert result is not None
        ex = _first(result)
        assert ex["sets"][0]["rest_sec"] == 120

    def test_terse_decimal_weight(self):
        result = _parse_simple_format("3x10 @22.5 db press")
        assert result is not None
        assert _first(result)["sets"][0]["weight_kg"] == 22.5


# ─── _parse_simple_format: rep-list pattern ──────────────────────────


class TestRepListPattern:
    """'(10,6,5) exercise @weight' format."""

    def test_basic_rep_list(self):
        result = _parse_simple_format("(10,6,5) squat @100")
        assert result is not None
        ex = _first(result)
        assert len(ex["sets"]) == 3
        assert ex["sets"][0]["reps"] == 10
        assert ex["sets"][1]["reps"] == 6
        assert ex["sets"][2]["reps"] == 5
        assert ex["sets"][0]["weight_kg"] == 100.0

    def test_rep_list_no_weight(self):
        result = _parse_simple_format("(10,8,6) pull ups")
        assert result is not None
        ex = _first(result)
        assert len(ex["sets"]) == 3
        assert ex["sets"][0]["weight_kg"] is None


# ─── _parse_simple_format: finisher pattern ──────────────────────────


class TestFinisherPattern:
    """'(exercise) NxM' standalone finisher format."""

    def test_finisher_amrap(self):
        result = _parse_simple_format("(dips) 3x amrap")
        assert result is not None
        ex = _first(result)
        assert ex["name"].lower() == "dips"
        assert len(ex["sets"]) == 3
        assert ex["sets"][0]["reps"] is None
        assert ex["sets"][0]["is_failure"] is True
        assert ex["notes"] == "finisher"

    def test_finisher_with_reps(self):
        result = _parse_simple_format("(pull ups) 4x8 @20")
        assert result is not None
        ex = _first(result)
        assert ex["name"].lower() == "pull ups"
        assert len(ex["sets"]) == 4
        assert ex["sets"][0]["reps"] == 8
        assert ex["sets"][0]["weight_kg"] == 20.0
        assert ex["notes"] == "finisher"

    def test_finisher_no_weight(self):
        result = _parse_simple_format("(burpees) 5x10")
        assert result is not None
        ex = _first(result)
        assert ex["name"].lower() == "burpees"
        assert len(ex["sets"]) == 5
        assert ex["sets"][0]["weight_kg"] is None

    def test_finisher_not_confused_with_rep_list(self):
        """(10,6,5) should match rep-list, not finisher."""
        result = _parse_simple_format("(10,6,5) squat @100")
        assert result is not None
        ex = _first(result)
        # Rep-list: 3 sets with different reps
        assert ex["sets"][0]["reps"] == 10
        assert ex["sets"][1]["reps"] == 6


# ─── _parse_simple_format: circuit pattern ───────────────────────────


class TestCircuitPattern:
    def test_basic_circuit(self):
        result = _parse_simple_format("5x(8 pull ups, 10 dips) r2'")
        assert result is not None
        assert len(result) == 2
        assert result[0]["sets"][0]["reps"] == 8
        assert len(result[0]["sets"]) == 5

    def test_circuit_global_weight(self):
        result = _parse_simple_format("4x(8 bench, 8 rows) @60")
        assert result is not None
        for ex in result:
            assert ex["sets"][0]["weight_kg"] == 60.0


# ─── _parse_simple_format: rest notation ─────────────────────────────


class TestRestNotation:
    def test_standalone_rest_applied_to_previous(self):
        result = _parse_simple_format("Bench press 4x8 80kg\nr2'")
        assert result is not None
        ex = _first(result)
        assert ex["sets"][-1]["rest_sec"] == 120

    def test_rest_with_seconds(self):
        result = _parse_simple_format("Bench press 4x8 80kg\nr1'30")
        assert result is not None
        ex = _first(result)
        assert ex["sets"][-1]["rest_sec"] == 90


# ─── _parse_simple_format: multi-exercise session ───────────────────


class TestMultiExercise:
    def test_full_session(self):
        text = "Bench press 4x8 80kg\n3x10 @22.5 db press\n(dips) 3x amrap"
        result = _parse_simple_format(text)
        assert result is not None
        assert len(result) == 3
        assert result[0]["name"].lower() == "bench press"
        assert result[1]["name"].lower() == "db press"
        assert result[2]["name"].lower() == "dips"
        assert result[2]["sets"][0]["is_failure"] is True


# ─── _parse_simple_format: descending/pyramid ───────────────────────


class TestDescendingPattern:
    def test_descending_sets(self):
        result = _parse_simple_format("3@100, 1@105, 1@110 squat")
        assert result is not None
        ex = _first(result)
        assert len(ex["sets"]) == 3  # 3@100=1set(3reps), 1@105=1set, 1@110=1set
        assert ex["sets"][0]["reps"] == 3
        assert ex["sets"][0]["weight_kg"] == 100.0
        assert ex["sets"][1]["reps"] == 1
        assert ex["sets"][1]["weight_kg"] == 105.0
        assert ex["sets"][2]["weight_kg"] == 110.0


# ─── parse_workout_text (integration, no LLM) ───────────────────────


class TestParseWorkoutTextNoLLM:
    """Test the full parse_workout_text with use_llm=False."""

    def test_basic_with_abbreviations(self):
        result = parse_workout_text(
            "4x8 bp @80",
            use_llm=False,
            abbreviations={"bp": "bench press"},
        )
        assert result.exercises[0].name == "bench press"
        assert len(result.exercises[0].sets) == 4

    def test_normalize_applied(self):
        """Smart quotes and rest typos should be fixed before parsing."""
        result = parse_workout_text(
            "Bench press 4x8 80kg\nr\u2019130",
            use_llm=False,
        )
        assert result.exercises[0].sets[-1].rest_sec == 90

    def test_date_extraction_inline(self):
        """Date prefix on the same line as the first exercise (DD/MM/YY)."""
        result = parse_workout_text(
            "05/12/25: Bench press 4x8 80kg",
            use_llm=False,
        )
        assert result.date == date(2025, 12, 5)
        assert result.exercises[0].name.lower() == "bench press"
        assert len(result.exercises[0].sets) == 4

    def test_date_extraction_own_line(self):
        """Date alone on the first line."""
        result = parse_workout_text(
            "05/12/2025:\nBench press 4x8 80kg",
            use_llm=False,
        )
        assert result.date == date(2025, 12, 5)
        assert len(result.exercises) == 1

    def test_empty_text(self):
        with pytest.raises(ValueError, match="no exercises found"):
            parse_workout_text("", use_llm=False)
