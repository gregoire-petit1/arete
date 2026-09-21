"""A session dictated in French must land on the same structure as one typed."""

from __future__ import annotations

import pytest

from arete.data.exercise_matcher import match_exercise
from arete.llm.speech_grammar import (
    normalize_speech,
    parse_dictation,
    split_sentences,
    unparsed_dictation,
)


def one(text: str) -> dict:
    """The single exercise a dictation is expected to yield."""
    parsed = parse_dictation(text)
    assert parsed, f"not parsed: {text!r}"
    assert len(parsed) == 1, f"expected one exercise, got {len(parsed)}"
    return parsed[0]


class TestNormalization:
    def test_numbers_written_out_become_digits(self):
        assert "4 séries de 8" in normalize_speech("quatre séries de huit")

    def test_small_numbers_are_converted_too(self):
        # "deux minutes" must not stay in letters, it is never an article here
        assert "2 minutes" in normalize_speech("deux minutes de repos")

    def test_eighty_and_ninety_survive_french_spelling(self):
        assert "80" in normalize_speech("quatre-vingts kilos")
        assert "90" in normalize_speech("quatre-vingt-dix kilos")

    def test_fillers_are_dropped_from_the_name_only(self):
        # what the athlete said is handed back untouched; only the name is cleaned
        assert one("euh alors j'ai fait du squat 3 séries de 5")["name"] == "squat"

    def test_failure_phrases_collapse_to_one_token(self):
        for phrase in ("jusqu'à l'échec", "au max", "jusqu'à l'epuisement"):
            assert "FAILURETOKEN" in normalize_speech(f"dips 3 séries {phrase}")

    def test_typographic_apostrophe_is_handled(self):
        assert "FAILURETOKEN" in normalize_speech("dips 3 séries jusqu’à l’échec")


class TestSets:
    def test_series_de(self):
        assert len(one("développé couché 4 séries de 8")["sets"]) == 4

    def test_fois(self):
        assert len(one("tractions 3 fois 10")["sets"]) == 3

    def test_compact_notation_spoken_aloud(self):
        exercise = one("rowing barre 4x10")
        assert len(exercise["sets"]) == 4
        assert exercise["sets"][0]["reps"] == 10

    def test_rep_range(self):
        exercise = one("presse 3 séries de 8 à 10 répétitions")
        assert exercise["target_reps"] == "8-10"
        assert exercise["sets"][0]["reps"] == 8

    def test_to_failure(self):
        exercise = one("dips 3 séries jusqu'à l'échec")
        assert exercise["sets"][0]["is_failure"] is True
        assert exercise["sets"][0]["reps"] is None

    def test_timed_sets_are_left_unread_rather_than_guessed(self):
        # counting a 60 s plank as 60 reps, or as a set to failure, would be wrong
        assert parse_dictation("gainage 3 fois 60 secondes") is None
        assert unparsed_dictation("gainage 3 fois 60 secondes") == [
            "gainage 3 fois 60 secondes"
        ]


class TestWeight:
    def test_a_kilos(self):
        assert one("squat 3 séries de 5 à 100 kilos")["sets"][0]["weight_kg"] == 100.0

    def test_avec(self):
        assert (
            one("squat 3 séries de 5 avec 100 kilos")["sets"][0]["weight_kg"] == 100.0
        )

    def test_unit_may_be_dropped(self):
        assert one("squat 3 séries de 5 à 100")["sets"][0]["weight_kg"] == 100.0

    def test_bodyweight_leaves_no_load(self):
        assert (
            one("dips au poids de corps 4 séries de 12")["sets"][0]["weight_kg"] is None
        )

    def test_decimal_load(self):
        assert one("curl 3 séries de 10 à 12,5 kilos")["sets"][0]["weight_kg"] == 12.5


class TestRest:
    def test_minutes(self):
        assert (
            one("squat 5 séries de 5, 3 minutes de repos")["sets"][0]["rest_sec"] == 180
        )

    def test_minutes_and_seconds(self):
        exercise = one("élévations latérales 3 séries de 15, 1 minute 30 de repos")
        assert exercise["sets"][0]["rest_sec"] == 90

    def test_seconds_only(self):
        exercise = one("mollets debout 4 séries de 20, 45 secondes de repos")
        assert exercise["sets"][0]["rest_sec"] == 45

    def test_rest_word_first(self):
        exercise = one("développé militaire 5 séries de 5, repos 3 minutes")
        assert exercise["sets"][0]["rest_sec"] == 180


class TestRpe:
    def test_explicit_rpe(self):
        assert one("squat 3 séries de 5 RPE 8")["sets"][0]["rpe"] == 8.0

    def test_out_of_ten(self):
        assert one("squat 3 séries de 5 à 8 sur 10")["sets"][0]["rpe"] == 8.0


class TestUnilateral:
    def test_each_side_is_noted(self):
        exercise = one("fentes 3 séries de 12 de chaque côté")
        assert exercise["target_reps"] == "12e"
        assert exercise["notes"] == "each side"

    def test_each_arm_counts_too(self):
        assert one("curl marteau 3 séries de 10 chaque bras")["notes"] == "each side"


class TestNames:
    def test_name_keeps_its_own_preposition(self):
        assert one("soulevé de terre 5 séries de 3 à 140 kilos")["name"] == (
            "soulevé de terre"
        )

    def test_leading_article_is_dropped(self):
        assert one("du développé couché 4 séries de 8")["name"] == "développé couché"

    def test_name_reaches_the_catalog(self):
        exercise = one("développé couché 4 séries de 8 à 80 kilos")
        assert match_exercise(exercise["name"]).exercise_id == "bench_press"


class TestSeveralExercises:
    def test_puis_separates(self):
        parsed = parse_dictation(
            "développé couché 4 séries de 8 à 80 kilos puis tractions 3 séries de 10"
        )
        assert [e["name"] for e in parsed] == ["développé couché", "tractions"]

    def test_et_separates(self):
        parsed = parse_dictation("squat 3 séries de 5 et tractions 4 séries de 6")
        assert len(parsed) == 2

    def test_comma_after_the_name_does_not_split(self):
        assert len(parse_dictation("développé couché, 4 séries de 8 à 80 kilos")) == 1

    def test_full_session(self):
        parsed = parse_dictation(
            "squat 5 séries de 5 à 100 kilos, 3 minutes de repos, RPE 8. "
            "Ensuite développé couché 4 séries de 8 à 80 kilos. "
            "Je finis par des dips 3 séries jusqu'à l'échec"
        )
        assert len(parsed) == 3
        assert parsed[0]["sets"][0]["rest_sec"] == 180
        assert parsed[2]["sets"][0]["is_failure"] is True


class TestWhatItRefuses:
    def test_a_name_alone_is_not_a_session_line(self):
        assert parse_dictation("développé couché") is None

    def test_a_name_with_only_a_weight_is_not_enough(self):
        assert parse_dictation("squat à 100 kilos") is None

    def test_empty_input(self):
        assert parse_dictation("") is None
        assert parse_dictation("   ") is None

    def test_prose_is_refused_rather_than_invented(self):
        assert parse_dictation("je me sens bien aujourd'hui") is None

    @pytest.mark.parametrize(
        "sentence",
        [
            "je ne sais plus trop ce que j'ai fait",
            "il faisait chaud dans la salle",
        ],
    )
    def test_unreadable_sentences_are_reported_verbatim(self, sentence):
        text = f"squat 3 séries de 5. {sentence}"
        missed = unparsed_dictation(text)
        assert len(missed) == 1
        assert sentence.split()[0] in missed[0]

    def test_nothing_missed_on_a_clean_dictation(self):
        assert unparsed_dictation("squat 3 séries de 5 à 100 kilos") == []


class TestSplitSentences:
    def test_quantity_only_chunk_joins_the_previous_one(self):
        chunks = split_sentences("développé couché, 4 séries de 8, 2 minutes de repos")
        assert len(chunks) == 1

    def test_each_named_chunk_stands_alone(self):
        chunks = split_sentences("squat 3 séries de 5. tractions 4 séries de 6")
        assert len(chunks) == 2


class TestFranglais:
    """A gym session is spoken in both languages, often in the same sentence."""

    def test_english_name_french_quantities(self):
        exercise = one("bench press 4 séries de 8 à 80 kilos")
        assert exercise["name"] == "bench press"
        assert exercise["sets"][0]["weight_kg"] == 80.0

    def test_english_keywords(self):
        exercise = one("bench press 4 sets of 8 at 80 kg")
        assert len(exercise["sets"]) == 4
        assert exercise["sets"][0]["reps"] == 8
        assert exercise["sets"][0]["weight_kg"] == 80.0

    def test_english_rest(self):
        assert (
            one("bench press 4 séries de 8, rest 2 minutes")["sets"][0]["rest_sec"]
            == 120
        )

    def test_english_failure(self):
        assert one("dips 3 séries to failure")["sets"][0]["is_failure"] is True
        assert one("pull ups 3 sets amrap")["sets"][0]["is_failure"] is True

    def test_english_each_side(self):
        assert one("lunges 3 séries de 12 each side")["notes"] == "each side"

    def test_english_bodyweight(self):
        assert one("dips bodyweight 4 sets of 12")["sets"][0]["weight_kg"] is None

    def test_then_separates_exercises(self):
        parsed = parse_dictation(
            "squat 5 séries de 5 à 100 kilos then bench press 4 sets of 8"
        )
        assert [e["name"] for e in parsed] == ["squat", "bench press"]


class TestQuantitiesFirst:
    """ "3 séries de 10 tractions" is as natural out loud as the other order."""

    def test_french(self):
        exercise = one("3 séries de 10 tractions")
        assert exercise["name"] == "tractions"
        assert len(exercise["sets"]) == 3
        assert exercise["sets"][0]["reps"] == 10

    def test_english(self):
        exercise = one("4 sets of 8 bench press")
        assert exercise["name"] == "bench press"
        assert len(exercise["sets"]) == 4

    def test_name_between_quantities(self):
        exercise = one("5 séries de 5 squat à 100 kilos")
        assert exercise["name"] == "squat"
        assert exercise["sets"][0]["weight_kg"] == 100.0


class TestWhatWhisperActuallyWrites:
    """Transcriptions from real audio, not from imagination."""

    def test_sentences_broken_by_punctuation_are_rejoined(self):
        # Whisper ends a sentence after the exercise name
        heard = "Développer coucher.  4 séries de 8 à 80 kg, 2 minutes de repos."
        exercise = one(heard)
        assert exercise["name"] == "développer coucher"
        assert len(exercise["sets"]) == 4
        assert exercise["sets"][0]["weight_kg"] == 80.0
        assert exercise["sets"][0]["rest_sec"] == 120

    def test_rest_written_as_the_french_reste(self):
        parsed = parse_dictation("bench press 4 séries de 8 à 80 kg. Reste 2 minutes.")
        assert len(parsed) == 1
        assert parsed[0]["sets"][0]["rest_sec"] == 120

    def test_a_lone_rest_sentence_joins_the_exercise_before_it(self):
        parsed = parse_dictation("squat 3 séries de 5. repos 3 minutes")
        assert len(parsed) == 1
        assert parsed[0]["sets"][0]["rest_sec"] == 180

    def test_mangled_rpe(self):
        for spelling in ("RP-E8", "RPE-8", "rpe8", "RPE 8"):
            parsed = parse_dictation(f"squat 5 séries de 5 à 110 kg, {spelling}")
            assert parsed, spelling
            assert parsed[0]["sets"][0]["rpe"] == 8.0, spelling

    def test_misheard_name_still_reaches_the_catalog(self):
        from arete.data.exercise_matcher import match_exercise

        # "développé couché" comes back as "développer coucher"
        assert match_exercise("développer coucher").exercise_id == "bench_press"
        # and the plural is often dropped
        assert match_exercise("traction").exercise_id == "pull_ups"


class TestSetsBeforeTheName:
    """ "4 séries de bench press à 80 kg pour 8 répétitions" — how it comes out."""

    def test_name_after_series_de(self):
        exercise = one("4 séries de bench press à 80 kg pour 8 répétitions")
        assert exercise["name"] == "bench press"
        assert len(exercise["sets"]) == 4
        assert exercise["sets"][0]["reps"] == 8
        assert exercise["sets"][0]["weight_kg"] == 80.0

    def test_pour_introduces_the_reps(self):
        assert one("3 séries de dips pour 10 répétitions")["sets"][0]["reps"] == 10

    def test_english_for(self):
        assert one("3 sets of dips for 10 reps")["sets"][0]["reps"] == 10

    def test_the_whole_dictation(self):
        parsed = parse_dictation(
            "J'ai fait 4 séries de bench press à 80 kg pour 8 répétitions. "
            "3 séries de traction lestée à 20 kg. pour 6 répétitions, "
            "et 4 séries de dips à 20 kilos pour 10 répétitions."
        )
        assert [e["name"] for e in parsed] == [
            "bench press",
            "traction lestée",
            "dips",
        ]
        assert [len(e["sets"]) for e in parsed] == [4, 3, 4]
        assert [e["sets"][0]["reps"] for e in parsed] == [8, 6, 10]
        assert [e["sets"][0]["weight_kg"] for e in parsed] == [80.0, 20.0, 20.0]

    def test_weighted_pull_ups_singular_reaches_the_catalog(self):
        from arete.data.exercise_matcher import match_exercise

        assert match_exercise("traction lestée").exercise_id == "weighted_pull_ups"
