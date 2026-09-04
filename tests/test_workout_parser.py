"""Tests for workout_parser: normalize, abbreviations, grammar/LLM orchestration."""

from __future__ import annotations

from datetime import date

import pytest

from arete.llm.workout_parser import (
    _expand_abbreviations,
    _normalize_workout_text,
    parse_workout_text,
)

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


# ─── parse_workout_text (integration, no LLM) ───────────────────────


class TestParseWorkoutTextNoLLM:
    """Test the full parse_workout_text with ."""

    def test_basic_with_abbreviations(self):
        result = parse_workout_text(
            "4x8 bp @80",
            abbreviations={"bp": "bench press"},
        )
        assert result.exercises[0].name == "bench press"
        assert len(result.exercises[0].sets) == 4

    def test_normalize_applied(self):
        """Smart quotes and rest typos should be fixed before parsing."""
        result = parse_workout_text(
            "Bench press 4x8 80kg\nr\u2019130",
        )
        assert result.exercises[0].sets[-1].rest_sec == 90

    def test_date_extraction_inline(self):
        """Date prefix on the same line as the first exercise (DD/MM/YY)."""
        result = parse_workout_text(
            "05/12/25: Bench press 4x8 80kg",
        )
        assert result.date == date(2025, 12, 5)
        assert result.exercises[0].name.lower() == "bench press"
        assert len(result.exercises[0].sets) == 4

    def test_date_extraction_own_line(self):
        """Date alone on the first line."""
        result = parse_workout_text(
            "05/12/2025:\nBench press 4x8 80kg",
        )
        assert result.date == date(2025, 12, 5)
        assert len(result.exercises) == 1

    def test_empty_text(self):
        with pytest.raises(ValueError, match="no exercises found"):
            parse_workout_text("")


# ─── grammar + semantic matching orchestration ────────────────────────


class TestParseWorkoutOrchestration:
    def test_catalog_match_and_score(self):
        result = parse_workout_text("Bench press 4x8 80kg\n(dips) 3x amrap")
        assert [e.name for e in result.exercises] == ["Bench press", "dips"]
        assert result.exercises[0].exercise_id == "bench_press"
        assert result.exercises[0].match_score == 100
        assert result.unparsed_lines == []

    def test_unparsed_lines_are_reported_not_lost(self):
        result = parse_workout_text("Bench press 4x8 80kg\nfarmer walk 2 lengths heavy")
        assert len(result.exercises) == 1
        assert result.unparsed_lines == ["farmer walk 2 lengths heavy"]

    def test_unknown_name_keeps_suggestions(self):
        result = parse_workout_text("3x10 @20 incline dumbell pres")
        ex = result.exercises[0]
        assert ex.exercise_id in (None, "incline_dumbbell_press", "incline_bench_press")
        assert ex.suggestions, "typo'd name should still produce catalog suggestions"
