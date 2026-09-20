"""Tests for the semantic exercise matcher."""

from __future__ import annotations

from arete.data.exercise_matcher import (
    ACCEPT_SCORE,
    match_exercise,
    normalize_name,
    strip_accents,
)


class TestNormalize:
    def test_shorthand_expansion(self):
        assert normalize_name("DB Shoulder Press") == "dumbbell shoulder press"
        assert normalize_name("kb  RDL") == "kettlebell romanian deadlift"
        assert normalize_name("pulls ups") == "pull ups"


class TestMatchExercise:
    def test_exact_alias(self):
        m = match_exercise("bp")
        assert m.exercise_id == "bench_press" and m.score == 100

    def test_catalog_name_case_insensitive(self):
        assert match_exercise("Bench Press").exercise_id == "bench_press"

    def test_french_name(self):
        assert match_exercise("Développé couché").exercise_id == "bench_press"

    def test_typo_is_matched_or_suggested(self):
        m = match_exercise("bench pres")
        assert m.suggestions and m.suggestions[0].exercise_id == "bench_press"
        assert m.suggestions[0].score >= ACCEPT_SCORE

    def test_qualifier_words_do_not_break_match(self):
        m = match_exercise("heavy bench press")
        assert m.exercise_id == "bench_press"

    def test_unknown_returns_no_id_but_maybe_suggestions(self):
        m = match_exercise("zqx flurb")
        assert m.exercise_id is None
        assert all(s.score < ACCEPT_SCORE for s in m.suggestions)

    def test_empty(self):
        m = match_exercise("   ")
        assert m.exercise_id is None and m.suggestions == []


class TestFrenchSpelling:
    """A session written or dictated in French must reach the catalog."""

    def test_accented_name_matches(self):
        assert match_exercise("développé couché").exercise_id == "bench_press"

    def test_unaccented_name_matches_the_same_entry(self):
        assert match_exercise("developpe couche").exercise_id == "bench_press"

    def test_case_and_accents_together(self):
        assert match_exercise("Développé Couché").exercise_id == "bench_press"

    def test_strip_accents_leaves_ascii_untouched(self):
        assert strip_accents("bench press") == "bench press"

    def test_strip_accents_handles_every_french_diacritic(self):
        assert strip_accents("Élévations à côté où ça") == "Elevations a cote ou ca"

    def test_spoken_shapes_reach_the_catalog(self):
        for spoken, expected in [
            ("soulevé de terre", "deadlift"),
            ("tirage vertical", "lat_pulldown"),
            ("écartés", "pec_fly"),
            ("curl biceps", "ez_bar_curl"),
            ("tractions lestées", "weighted_pull_ups"),
            ("mollets debout", "calf_raises"),
        ]:
            assert match_exercise(spoken).exercise_id == expected, spoken
