"""The day's decision for a planned session, read against the readiness bands."""

from __future__ import annotations

import pytest
from coach_text_checks import RAW_FIELDS

from arete.services.adaptation import AdaptationInput, Decision, evaluate


def _input(**overrides) -> AdaptationInput:
    values = {
        "session_type": "tempo",
        "sport": "running",
        "status": "pending",
        "target_duration_min": 45,
        "target_hr_zone": "Z4",
        "target_intensity": "hard",
        "description": "3x10' au seuil",
        "readiness": 85.0,
        "readiness_source": "garmin_training",
        "acwr": 1.0,
        "tsb": 0.0,
        "fitness_goal": "build",
    }
    values.update(overrides)
    return AdaptationInput(**values)


@pytest.mark.parametrize(
    ("score", "decision"),
    [
        (80, Decision.KEEP),
        (79, Decision.EASE),
        (60, Decision.EASE),
        (59, Decision.REPLACE_EASY),
        (40, Decision.REPLACE_EASY),
        (39, Decision.REST),
    ],
)
def test_bands_for_a_hard_session(score, decision):
    result = evaluate(_input(readiness=float(score)))
    assert result is not None and result.decision == decision


def test_an_eased_tempo_keeps_its_duration_in_z2():
    result = evaluate(_input(readiness=70.0))
    assert result is not None
    assert result.adapted == {
        "session_type": "endurance",
        "target_hr_zone": "Z2",
        "target_intensity": "easy",
    }


def test_a_replaced_session_is_30_minutes_of_z1():
    result = evaluate(_input(readiness=50.0))
    assert result is not None
    assert result.adapted["target_duration_min"] == 30
    assert result.adapted["target_hr_zone"] == "Z1"
    assert "3x10' au seuil" in result.adapted["description"]


def test_an_easy_session_is_kept_at_a_middling_readiness():
    result = evaluate(_input(session_type="endurance", readiness=70.0))
    assert result is not None and result.decision == Decision.KEEP


def test_acwr_overrides_a_high_readiness():
    result = evaluate(_input(readiness=90.0, acwr=1.6))
    assert result is not None and result.decision == Decision.REST
    assert "1.60" in result.reason


def test_deep_fatigue_or_a_recovery_goal_eases_a_tempo_at_90():
    for overrides in ({"tsb": -30.0}, {"fitness_goal": "recovery"}):
        result = evaluate(_input(readiness=90.0, **overrides))
        assert result is not None and result.decision == Decision.EASE


@pytest.mark.parametrize(
    "overrides",
    [
        {"session_type": "strength", "sport": "strength"},
        {"session_type": "hypertrophy"},
        {"status": "completed"},
        {"status": "skipped"},
        {"sport": "hiking"},
        {"readiness": None},
    ],
)
def test_out_of_scope_sessions_get_no_decision(overrides):
    assert evaluate(_input(**overrides)) is None


def test_race_day_is_kept():
    result = evaluate(_input(session_type="race", readiness=30.0, acwr=2.0))
    assert result is not None and result.decision == Decision.KEEP


def test_reasons_are_french_numbers_with_their_source():
    for score, source, said in [
        (70.0, "garmin_training", "Garmin 70/100"),
        (55.0, "garmin", "VFC, sommeil) 55/100"),
        (30.0, "model", "estimée par la charge 30/100"),
    ]:
        result = evaluate(_input(readiness=score, readiness_source=source))
        assert result is not None and said in result.reason
        assert not any(field in result.reason for field in RAW_FIELDS)
