"""Measures the grammar against a corpus of dictations.

The corpus is the asset that survives a change of approach: it says what the
grammar reads today, and it will say the same about a model if one ever
replaces it. Real dictations are added to ``tests/data/dictations.jsonl`` as
they are recorded; the file starts with realistic sentences.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from arete.data.exercise_matcher import match_exercise
from arete.llm.notation import to_notation
from arete.llm.speech_grammar import parse_dictation

CORPUS = Path(__file__).parent / "data" / "dictations.jsonl"
# Below this, the grammar has stopped being useful and needs new rules.
MIN_READ_RATIO = 0.9
MIN_MATCH_RATIO = 0.9


def load() -> list[dict]:
    if not CORPUS.exists():
        return []
    return [
        json.loads(line)
        for line in CORPUS.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


@pytest.fixture(scope="module")
def corpus() -> list[dict]:
    entries = load()
    assert entries, "the dictation corpus is empty"
    return entries


class TestCorpus:
    def test_every_dictation_yields_its_exercises(self, corpus):
        failures = [
            entry["transcript"]
            for entry in corpus
            if len(parse_dictation(entry["transcript"]) or []) != entry["exercises"]
        ]
        read = len(corpus) - len(failures)
        assert read / len(corpus) >= MIN_READ_RATIO, (
            f"{read}/{len(corpus)} dictations read. Not read: {failures}"
        )

    def test_notation_matches_what_is_expected(self, corpus):
        for entry in corpus:
            if "notation" not in entry:
                continue
            parsed = parse_dictation(entry["transcript"])
            if not parsed:
                continue
            assert to_notation(parsed) == entry["notation"], entry["transcript"]

    def test_exercise_names_reach_the_catalog(self, corpus):
        names = [
            exercise["name"]
            for entry in corpus
            for exercise in parse_dictation(entry["transcript"]) or []
        ]
        matched = [name for name in names if match_exercise(name).exercise_id]
        unmatched = sorted(set(names) - set(matched))
        assert len(matched) / len(names) >= MIN_MATCH_RATIO, (
            f"{len(matched)}/{len(names)} matched. Missing from the catalog: {unmatched}"
        )
