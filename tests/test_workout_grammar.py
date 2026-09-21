"""Tests for the Lark-based workout grammar (same corpus as the regex parser)."""

from __future__ import annotations

from arete.llm.workout_grammar import parse_line, unparsed_lines
from arete.llm.workout_grammar import (
    parse_workout_grammar as _parse_simple_format,
)

# ─── Helper ──────────────────────────────────────────────────────────


def _names(exercises: list[dict]) -> list[str]:
    """Extract exercise names from parsed result."""
    return [e["name"] for e in exercises]


def _first(exercises: list[dict]) -> dict:
    return exercises[0]


# ─── _normalize_workout_text ─────────────────────────────────────────


# ─── _expand_abbreviations ──────────────────────────────────────────


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


# ─── real sessions (regression corpus) ───────────────────────────────


class TestRealSessions:
    def test_circuit_session_with_ranges_and_rest(self):
        text = (
            "5x(8-10 weighted pull ups @20kg, 15 db lateral raises @20) r2'\n"
            "5x(10 chin ups, 15 dips) r1'30"
        )
        result = _parse_simple_format(text)
        assert result is not None
        assert _names(result) == [
            "weighted pull ups",
            "db lateral raises",
            "chin ups",
            "dips",
        ]
        assert result[0]["target_reps"] == "8-10"
        assert result[0]["sets"][0]["weight_kg"] == 20.0
        assert result[1]["sets"][0]["weight_kg"] == 20.0
        assert result[2]["sets"][0]["rest_sec"] == 90

    def test_mixed_form(self):
        result = _parse_simple_format("horizontal pull 2x8@100kg r1'30")
        assert result is not None
        ex = _first(result)
        assert ex["name"] == "horizontal pull"
        assert [s["weight_kg"] for s in ex["sets"]] == [100.0, 100.0]
        assert ex["sets"][0]["rest_sec"] == 90

    def test_colon_form_mixed_specs(self):
        result = _parse_simple_format("bench press : 6@80kg, 4@100kg, 2x1@110kg r2'30")
        assert result is not None
        ex = _first(result)
        assert [s["reps"] for s in ex["sets"]] == [6, 4, 1, 1]
        assert [s["weight_kg"] for s in ex["sets"]] == [80.0, 100.0, 110.0, 110.0]
        assert ex["target_reps"] is None  # heterogeneous reps

    def test_descending_with_trailing_name_and_rest(self):
        result = _parse_simple_format(
            "3@100, 1@105, 1@110, 1@115, 1@120 heavy bench press r2'"
        )
        ex = _first(result)
        assert ex["name"] == "heavy bench press"
        assert len(ex["sets"]) == 5
        assert ex["sets"][-1]["weight_kg"] == 120.0

    def test_sets_then_name_then_weight(self):
        ex = _first(_parse_simple_format("3x5 pause bench @80 r2'"))
        assert ex["name"] == "pause bench"
        assert ex["sets"][0]["weight_kg"] == 80.0

    def test_unilateral_in_circuit(self):
        result = _parse_simple_format("5x(10 kb RDL @32kg, 15e db rows @22.5kg) r2'")
        assert result[1]["name"] == "db rows"
        assert result[1]["sets"][0]["reps"] == 15
        assert result[1]["notes"] == "each side"

    def test_circuit_head_default_reps(self):
        result = _parse_simple_format("5x15e(db row @22.5, lunges)")
        assert [e["sets"][0]["reps"] for e in result] == [15, 15]
        assert result[0]["sets"][0]["weight_kg"] == 22.5

    def test_emom(self):
        result = _parse_simple_format("EMOM 20' (odd: 10 pull ups, even: 10 chin ups)")
        assert _names(result) == ["pull ups", "chin ups"]
        assert all(len(e["sets"]) == 10 for e in result)
        assert result[0]["notes"] == "EMOM 20'"
        assert result[0]["sets"][0]["rest_sec"] == 60

    def test_cardio_line_is_rejected_not_misparsed(self):
        text = "5x1'@1'35/500m row erg"
        assert _parse_simple_format(text) is None
        assert unparsed_lines(text) == [text]

    def test_unparseable_lines_are_reported_but_rest_is_kept(self):
        text = "Bench press 4x8 80kg\nsome free text note\nr2'"
        result = _parse_simple_format(text)
        assert len(result) == 1
        assert result[0]["sets"][-1]["rest_sec"] == 120
        assert unparsed_lines(text) == ["some free text note"]


class TestFrenchExerciseNames:
    """The grammar must read a session written in French, accents included."""

    def test_accented_name_is_parsed(self):
        parsed = parse_line("développé couché 4x8 @80")
        assert parsed and parsed[0]["name"] == "développé couché"
        assert len(parsed[0]["sets"]) == 4
        assert parsed[0]["sets"][0]["weight_kg"] == 80.0

    def test_unaccented_name_is_parsed(self):
        parsed = parse_line("developpe couche 4x8 @80")
        assert parsed and parsed[0]["name"] == "developpe couche"

    def test_french_name_with_rest_and_rpe(self):
        parsed = parse_line("élévations latérales 3x15 r1'30 RPE 8")
        assert parsed and parsed[0]["name"] == "élévations latérales"
        assert parsed[0]["sets"][0]["rest_sec"] == 90
        assert parsed[0]["sets"][0]["rpe"] == 8.0

    def test_ascii_notation_still_parses(self):
        parsed = parse_line("bench press 4x8 @80")
        assert parsed and parsed[0]["name"] == "bench press"
