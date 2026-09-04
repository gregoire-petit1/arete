"""Tests for workout_parser: normalize, abbreviations, grammar/LLM orchestration."""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace
from unittest.mock import patch

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


# ─── grammar-first orchestration with the LLM ────────────────────────


def _fake_client(payload: dict):
    """OpenAI-like client whose chat completion returns ``payload`` as JSON."""
    message = SimpleNamespace(content=json.dumps(payload))
    response = SimpleNamespace(choices=[SimpleNamespace(message=message)])
    completions = SimpleNamespace(create=lambda **_: response)
    return SimpleNamespace(chat=SimpleNamespace(completions=completions))


class TestGrammarFirst:
    def test_llm_not_called_when_grammar_covers_everything(self):
        with patch("arete.llm.workout_parser.get_llm_client") as get_client:
            result = parse_workout_text(
                "Bench press 4x8 80kg\n(dips) 3x amrap", use_llm=True
            )
        get_client.assert_not_called()
        assert [e.name for e in result.exercises] == ["Bench press", "dips"]
        assert result.exercises[0].exercise_id is not None  # catalog match kept

    def test_llm_only_sees_rejected_lines(self):
        payload = {
            "exercises": [
                {
                    "name": "farmer walk",
                    "sets": [{"set_number": 1, "reps": 1, "weight_kg": 32}],
                }
            ],
            "duration_min": 45,
        }
        client = _fake_client(payload)
        prompts: list[str] = []
        with (
            patch("arete.llm.workout_parser.get_llm_client", return_value=client),
            patch("arete.llm.workout_parser.get_default_model", return_value="m"),
            patch(
                "arete.llm.workout_parser._build_parser_prompt",
                side_effect=lambda text, *a, **k: prompts.append(text) or ("sys", text),
            ),
        ):
            result = parse_workout_text(
                "Bench press 4x8 80kg\nfarmer walk 2 lengths heavy", use_llm=True
            )
        assert prompts == ["farmer walk 2 lengths heavy"]
        assert [e.name for e in result.exercises] == ["Bench press", "farmer walk"]
        assert result.duration_min == 45

    def test_llm_failure_keeps_grammar_result(self):
        with patch("arete.llm.workout_parser.get_llm_client", return_value=None):
            result = parse_workout_text(
                "Bench press 4x8 80kg\nsome free text", use_llm=True
            )
        assert len(result.exercises) == 1
