"""What the dictation writes back, the notation grammar must read."""

from __future__ import annotations

from arete.llm.notation import (
    exercise_to_notation,
    format_rest,
    format_rpe,
    format_weight,
    to_notation,
)
from arete.llm.speech_grammar import parse_dictation
from arete.llm.workout_grammar import parse_workout_grammar


class TestFormatters:
    def test_rest_in_whole_minutes(self):
        assert format_rest(180) == "r3'"

    def test_rest_with_seconds(self):
        assert format_rest(90) == "r1'30"

    def test_rest_under_a_minute(self):
        assert format_rest(45) == "r0'45"

    def test_no_rest(self):
        assert format_rest(None) is None
        assert format_rest(0) is None

    def test_whole_weight_has_no_decimal(self):
        assert format_weight(80.0) == "@80"

    def test_decimal_weight_is_kept(self):
        assert format_weight(12.5) == "@12.5"

    def test_bodyweight_writes_nothing(self):
        assert format_weight(None) is None

    def test_rpe(self):
        assert format_rpe(8.0) == "RPE 8"
        assert format_rpe(7.5) == "RPE 7.5"
        assert format_rpe(None) is None


class TestExerciseLine:
    def test_full_line(self):
        parsed = parse_dictation(
            "squat 5 séries de 5 à 100 kilos, 3 minutes de repos, RPE 8"
        )
        assert exercise_to_notation(parsed[0]) == "squat 5x5 @100 r3' RPE 8"

    def test_bodyweight_line(self):
        parsed = parse_dictation("tractions 3 séries de 10")
        assert exercise_to_notation(parsed[0]) == "tractions 3x10"

    def test_failure_line(self):
        parsed = parse_dictation("dips 3 séries jusqu'à l'échec")
        assert exercise_to_notation(parsed[0]) == "dips 3xamrap"

    def test_range_line(self):
        parsed = parse_dictation("presse 3 séries de 8 à 10 répétitions")
        assert exercise_to_notation(parsed[0]) == "presse 3x8-10"

    def test_unilateral_line(self):
        parsed = parse_dictation("fentes 3 séries de 12 de chaque côté")
        assert exercise_to_notation(parsed[0]) == "fentes 3x12e"


class TestRoundTrip:
    """A dictation written as notation must parse back to the same session."""

    DICTATIONS = [
        "squat 5 séries de 5 à 100 kilos, 3 minutes de repos, RPE 8",
        "développé couché 4 séries de 8 à 80 kilos",
        "tractions 3 séries de 10",
        "dips 3 séries jusqu'à l'échec",
        "presse 3 séries de 8 à 10 répétitions",
        "fentes 3 séries de 12 de chaque côté",
        "élévations latérales 3 séries de 15, 1 minute 30 de repos",
        "curl 3 séries de 10 à 12,5 kilos",
    ]

    def test_every_dictation_survives_the_round_trip(self):
        for dictation in self.DICTATIONS:
            spoken = parse_dictation(dictation)
            assert spoken, dictation
            typed = parse_workout_grammar(to_notation(spoken))
            assert typed, f"notation rejected by the grammar: {dictation!r}"
            assert len(typed) == len(spoken)
            for before, after in zip(spoken, typed, strict=True):
                assert after["name"] == before["name"]
                assert len(after["sets"]) == len(before["sets"])
                assert after["sets"][0]["reps"] == before["sets"][0]["reps"]
                assert after["sets"][0]["weight_kg"] == before["sets"][0]["weight_kg"]
                assert after["sets"][0]["rest_sec"] == before["sets"][0]["rest_sec"]
                assert after["sets"][0]["rpe"] == before["sets"][0]["rpe"]
                assert after["sets"][0]["is_failure"] == before["sets"][0]["is_failure"]

    def test_several_exercises_become_several_lines(self):
        spoken = parse_dictation(
            "squat 5 séries de 5 à 100 kilos puis tractions 3 séries de 10"
        )
        assert to_notation(spoken) == "squat 5x5 @100\ntractions 3x10"

    def test_empty_input(self):
        assert to_notation([]) == ""
