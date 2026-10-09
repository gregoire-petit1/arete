"""Briefings and feedback kept from real runs still meet the text checks.

The corpus lives in ``data/agent/corpus.jsonl``, out of git (the repository is
public and the texts are personal training data). Fill it with
``scripts/export_coach_runs.py``; without it this test is skipped.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from coach_text_checks import briefing_problems, feedback_problems

CORPUS = Path(__file__).resolve().parents[1] / "data" / "agent" / "corpus.jsonl"
CHECKS = {"briefing": briefing_problems, "feedback": feedback_problems}


def _entries() -> list[dict]:
    if not CORPUS.exists():
        return []
    return [json.loads(line) for line in CORPUS.read_text().splitlines() if line]


@pytest.mark.skipif(not _entries(), reason=f"no corpus at {CORPUS}")
@pytest.mark.parametrize(
    "entry", _entries(), ids=lambda e: f"{e['profile']}-{e.get('date', '')}"
)
def test_a_kept_answer_meets_the_checks(entry):
    assert CHECKS[entry["profile"]](entry["text"]) == []
