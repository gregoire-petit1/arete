"""Strength toolkit: the first toolkit that writes, and the write is lossy.

The parser only saves exercises the catalog matched confidently. A human at
the form sees the others greyed out; an athlete dictating reads one sentence.
So what gets dropped has to be reported — before the save, and again after it.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from arete.agent.capabilities.registry import CAPABILITIES, STRENGTH_INSTRUCTIONS
from arete.agent.tools.strength import (
    MAX_WORKOUT_TEXT_CHARS,
    STRENGTH_TOOLS,
    read_workout,
    save_workout,
)
from arete.strength.repository import StrengthRepository

# One line the grammar reads and the catalog matches, one it cannot place.
KNOWN = "3x10 @80 bench press"
UNKNOWN = "4x12 @40 zercher goblet thruster machine"


@pytest.fixture
def day():
    """A date of this test's own, cleaned up after."""
    target = date.today() + timedelta(days=500)
    yield target
    repo = StrengthRepository()
    for session in repo.list_sessions(start_date=target, end_date=target):
        if session.id:
            repo.delete_session(session.id)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_registered_with_its_three_tools():
    toolkit = CAPABILITIES["strength"]
    assert {t.name for t in toolkit.tools} == {
        "read_workout",
        "save_workout",
        "get_strength_progress",
    }
    assert "get_strength_progress" in toolkit.read_tools
    assert toolkit.instructions == STRENGTH_INSTRUCTIONS
    assert {t.name for t in STRENGTH_TOOLS} == {t.name for t in toolkit.tools}


def test_the_instructions_put_the_dry_run_first():
    assert "read_workout" in STRENGTH_INSTRUCTIONS
    assert "not_recognised" in STRENGTH_INSTRUCTIONS


# ---------------------------------------------------------------------------
# read_workout: a dry run that writes nothing
# ---------------------------------------------------------------------------


def test_reading_reports_what_it_understood(day):
    out = json.loads(read_workout.invoke({"text": KNOWN, "date_str": day.isoformat()}))
    assert out["saved"] is False
    assert out["date"] == day.isoformat()
    assert out["exercises"][0]["matched"] is True
    assert len(out["exercises"][0]["sets"]) == 3


def test_reading_writes_nothing(day):
    read_workout.invoke({"text": KNOWN, "date_str": day.isoformat()})
    assert StrengthRepository().list_sessions(start_date=day, end_date=day) == []


def test_an_unmatched_exercise_is_named_not_swallowed(day):
    out = json.loads(
        read_workout.invoke(
            {"text": f"{KNOWN}\n{UNKNOWN}", "date_str": day.isoformat()}
        )
    )
    names = [d["name"] for d in out["not_recognised"]]
    assert names, f"the drop went unreported: {out}"
    # The athlete needs something to answer with.
    assert "did_you_mean" in out["not_recognised"][0]


def test_unreadable_text_is_an_error_not_a_silent_empty(day):
    out = json.loads(read_workout.invoke({"text": "il faisait beau ce matin"}))
    assert "error" in out


# ---------------------------------------------------------------------------
# save_workout: writes, and still reports the loss
# ---------------------------------------------------------------------------


def test_saving_persists_the_session(day):
    out = json.loads(save_workout.invoke({"text": KNOWN, "date_str": day.isoformat()}))
    assert out["saved"] is True
    assert out["session_id"]
    assert out["saved_exercises"]
    stored = StrengthRepository().list_sessions(start_date=day, end_date=day)
    assert len(stored) == 1


def test_saving_still_names_what_it_left_out(day):
    out = json.loads(
        save_workout.invoke(
            {"text": f"{KNOWN}\n{UNKNOWN}", "date_str": day.isoformat()}
        )
    )
    assert out["saved"] is True
    assert out["not_recognised"], f"saved silently dropping an exercise: {out}"
    assert "left out" in out["message"]


def test_nothing_matched_means_nothing_saved(day):
    out = json.loads(
        save_workout.invoke({"text": UNKNOWN, "date_str": day.isoformat()})
    )
    assert out["saved"] is False
    assert out["session_id"] is None
    assert StrengthRepository().list_sessions(start_date=day, end_date=day) == []


# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------


def test_a_bad_date_says_which_format():
    out = json.loads(read_workout.invoke({"text": KNOWN, "date_str": "25/09/2026"}))
    assert "YYYY-MM-DD" in out["error"]


def test_empty_text_is_refused():
    assert "error" in json.loads(read_workout.invoke({"text": "   "}))
    assert "error" in json.loads(save_workout.invoke({"text": ""}))


def test_an_essay_is_refused_before_parsing():
    out = json.loads(save_workout.invoke({"text": "x" * (MAX_WORKOUT_TEXT_CHARS + 1)}))
    assert "too long" in out["error"]


# ---------------------------------------------------------------------------
# The reason the save path was extracted: one behaviour, two entry points
# ---------------------------------------------------------------------------


class TestRouteAndToolAgree:
    """The Log page and the coach must write the same session.

    The save logic used to live inside the route body. A second copy for the
    agent would have drifted — different abbreviations, different catalog
    matching, a planned session completed on one path and not the other.
    """

    def test_same_text_gives_the_same_exercises(self, day, client):
        from_route = client.post(
            "/strength/sessions/parse",
            json={"text": f"{KNOWN}\n{UNKNOWN}", "date": day.isoformat()},
        ).json()
        from_tool = json.loads(
            read_workout.invoke(
                {"text": f"{KNOWN}\n{UNKNOWN}", "date_str": day.isoformat()}
            )
        )

        assert [e["name"] for e in from_route["exercises"]] == [
            e["name"] for e in from_tool["exercises"]
        ]
        assert [e["exercise_matched"] for e in from_route["exercises"]] == [
            e["matched"] for e in from_tool["exercises"]
        ]

    def test_saving_through_either_path_completes_the_planned_session(
        self, day, monkeypatch
    ):
        from arete.strength import logging_service

        completed: list[date] = []
        monkeypatch.setattr(
            logging_service, "complete_planned_strength", completed.append
        )
        save_workout.invoke({"text": KNOWN, "date_str": day.isoformat()})
        assert completed == [day]
