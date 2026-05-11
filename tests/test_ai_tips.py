"""Tests for /tips endpoints (post-session feedback)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from arete.api.ai_tips import router


@pytest.fixture()
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


# ─── Strength tests ──────────────────────────────────────────────────


def _make_strength_session(exercises=None, overall_rpe=7):
    """Build a minimal mock StrengthSession."""
    session = MagicMock()
    session.date = date(2025, 5, 10)
    session.overall_rpe = overall_rpe
    session.exercises = exercises or []
    return session


def _make_exercise(muscle_value: str, sets_data: list[tuple[int, float]]):
    """Create a mock SessionExercise with sets.

    sets_data: list of (reps, weight_kg) tuples.
    """
    ex = MagicMock()
    ex.exercise = MagicMock()
    ex.exercise.primary_muscle = MagicMock()
    ex.exercise.primary_muscle.value = muscle_value

    sets = []
    for reps, weight in sets_data:
        s = MagicMock()
        s.is_warmup = False
        s.reps = reps
        s.weight_kg = weight
        sets.append(s)
    ex.sets = sets
    return ex


class TestPostSessionStrength:
    """POST /tips/post-session with session_type=strength."""

    @patch("arete.api.ai_tips.StrengthRepository")
    def test_strength_feedback_with_volume(self, mock_repo_cls, client):
        repo = mock_repo_cls.return_value
        exercises = [
            _make_exercise("chest", [(10, 80), (10, 80), (8, 85)]),
        ]
        repo.get_session.return_value = _make_strength_session(exercises)
        repo.get_volume_by_muscle.return_value = {"chest": 6000.0}

        resp = client.post(
            "/tips/post-session",
            json={"session_type": "strength", "session_id": 1},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "feedback" in data
        assert "pectoraux" in data["feedback"].lower() or any(
            "pectoraux" in h.lower() for h in data["highlights"]
        )
        assert len(data["highlights"]) >= 1

    @patch("arete.api.ai_tips.StrengthRepository")
    def test_strength_not_found(self, mock_repo_cls, client):
        repo = mock_repo_cls.return_value
        repo.get_session.return_value = None

        resp = client.post(
            "/tips/post-session",
            json={"session_type": "strength", "session_id": 999},
        )
        assert resp.status_code == 404


# ─── Cardio tests ────────────────────────────────────────────────────


def _make_actual_session(
    avg_hr=145,
    max_hr=172,
    avg_pace_sec_km=330,
    distance_m=10000,
    calories=650,
    sport="running",
    duration_sec=3600,
):
    session = MagicMock()
    session.sport = sport
    session.duration_sec = duration_sec
    session.avg_hr = avg_hr
    session.max_hr = max_hr
    session.avg_pace_sec_km = avg_pace_sec_km
    session.distance_m = distance_m
    session.calories = calories
    return session


class TestPostSessionCardio:
    """POST /tips/post-session with session_type=cardio."""

    @patch("arete.api.ai_tips.GarminRepository")
    def test_cardio_feedback_with_hr_and_pace(self, mock_repo_cls, client):
        repo = mock_repo_cls.return_value
        repo.get_actual_session.return_value = _make_actual_session()

        resp = client.post(
            "/tips/post-session",
            json={"session_type": "cardio", "session_id": 42},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "running" in data["feedback"].lower()
        assert any("bpm" in h for h in data["highlights"])
        assert any("/km" in h for h in data["highlights"])

    @patch("arete.api.ai_tips.GarminRepository")
    def test_cardio_not_found(self, mock_repo_cls, client):
        repo = mock_repo_cls.return_value
        repo.get_actual_session.return_value = None

        resp = client.post(
            "/tips/post-session",
            json={"session_type": "cardio", "session_id": 999},
        )
        assert resp.status_code == 404

    @patch("arete.api.ai_tips.GarminRepository")
    def test_cardio_no_hr_data(self, mock_repo_cls, client):
        repo = mock_repo_cls.return_value
        repo.get_actual_session.return_value = _make_actual_session(
            avg_hr=None,
            max_hr=None,
            avg_pace_sec_km=None,
            distance_m=None,
            calories=None,
        )

        resp = client.post(
            "/tips/post-session",
            json={"session_type": "cardio", "session_id": 10},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "Séance complétée" in data["highlights"][0]
