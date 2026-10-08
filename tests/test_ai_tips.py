"""Tests for /tips endpoints (post-session feedback)."""

from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import pytest

from arete.api.ai_tips import router


@pytest.fixture
def client(router_client):
    return router_client(router)


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


@pytest.fixture
def rules_only():
    """Keep the agent out of tests about the rule-based facts.

    The feedback path runs the coaching agent now; these tests are about the
    numbers underneath it, so they assert on the floor.
    """
    with patch(
        "arete.coaching.enrich_session_feedback",
        side_effect=lambda text, highlights: (text, "rules"),
    ):
        yield


class TestPostSessionStrength:
    """POST /tips/post-session with session_type=strength."""

    @pytest.fixture(autouse=True)
    def _floor(self, rules_only):
        pass

    @patch("arete.services.coaching_rules.StrengthRepository")
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

    @patch("arete.services.coaching_rules.StrengthRepository")
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
    @pytest.fixture(autouse=True)
    def _floor(self, rules_only):
        pass

    """POST /tips/post-session with session_type=cardio."""

    @patch("arete.services.coaching_rules.GarminRepository")
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

    @patch("arete.services.coaching_rules.GarminRepository")
    def test_cardio_not_found(self, mock_repo_cls, client):
        repo = mock_repo_cls.return_value
        repo.get_actual_session.return_value = None

        resp = client.post(
            "/tips/post-session",
            json={"session_type": "cardio", "session_id": 999},
        )
        assert resp.status_code == 404

    @patch("arete.services.coaching_rules.GarminRepository")
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


class TestTipUsesSettings:
    """The threshold and the goal come from the athlete's settings, not constants."""

    def test_readiness_is_read_against_the_athletes_threshold(self):
        from arete.services.coaching_rules import generate_daily_tip

        tip, priority = generate_daily_tip(1.0, 0.0, 82.0, fatigue_threshold=75)
        assert "82/100" in tip and "75" in tip
        assert priority == "info"

    def test_readiness_below_threshold_falls_through(self):
        from arete.services.coaching_rules import generate_daily_tip

        tip, _ = generate_daily_tip(1.0, 0.0, 82.0, fatigue_threshold=90)
        assert "ACWR 1.00" in tip

    def test_goal_closes_the_balanced_load_tip(self):
        from arete.services.coaching_rules import GOAL_ADVICE, generate_daily_tip

        for goal, advice in GOAL_ADVICE.items():
            tip, _ = generate_daily_tip(1.0, 0.0, None, fitness_goal=goal)
            assert advice in tip

    def test_unknown_goal_falls_back_to_build(self):
        from arete.services.coaching_rules import GOAL_ADVICE, generate_daily_tip

        tip, _ = generate_daily_tip(1.0, 0.0, None, fitness_goal="whatever")
        assert GOAL_ADVICE["build"] in tip

    def test_the_rule_floor_passes_settings_through(self):
        from unittest.mock import patch

        from arete.services.coaching_rules import daily_rule_tip

        with patch(
            "arete.services.coaching_rules.get_user_settings",
            return_value={"fatigue_threshold": 60, "fitness_goal": "recovery"},
        ):
            tip, _ = daily_rule_tip()
        assert isinstance(tip, str) and tip


class TestDailyEndpoint:
    """GET /tips/daily now reads the day's briefing, producing it once."""

    def test_serves_the_stored_briefing_without_producing_another(self, client):
        from datetime import date
        from unittest.mock import patch

        from arete.services.coaching_repository import BriefingRepository

        repo = BriefingRepository()
        repo.delete_for_day(date.today())
        repo.create(
            text="Ta charge monte vite.",
            priority="warning",
            source="agent",
            briefing_date=date.today(),
        )
        try:
            with patch("arete.services.briefing.generate_briefing") as produce:
                body = client.get("/tips/daily").json()
            produce.assert_not_called()
        finally:
            repo.delete_for_day(date.today())

        assert body["tip"] == "Ta charge monte vite."
        assert body["priority"] == "warning"
        assert body["source"] == "agent"
        assert body["generated_at"]

    def test_produces_one_when_the_day_has_none(self, client):
        from datetime import date
        from unittest.mock import patch

        from arete.services.coaching_repository import BriefingRepository

        repo = BriefingRepository()
        repo.delete_for_day(date.today())
        try:
            with (
                patch("arete.services.briefing.briefing_enabled", return_value=True),
                patch("arete.coaching.run_briefing", return_value="Écrit ce matin."),
                patch(
                    "arete.services.briefing._rule_floor",
                    return_value=("floor", "info"),
                ),
            ):
                body = client.get("/tips/daily").json()
        finally:
            repo.delete_for_day(date.today())

        assert body["tip"] == "Écrit ce matin."
        assert body["source"] == "agent"

    def test_a_dead_model_still_answers_with_the_rule_text(self, client):
        from datetime import date
        from unittest.mock import patch

        from arete.services.coaching_repository import BriefingRepository

        repo = BriefingRepository()
        repo.delete_for_day(date.today())
        try:
            with (
                patch("arete.services.briefing.briefing_enabled", return_value=True),
                patch(
                    "arete.coaching.run_briefing",
                    side_effect=RuntimeError("model is away"),
                ),
            ):
                resp = client.get("/tips/daily")
        finally:
            repo.delete_for_day(date.today())

        assert resp.status_code == 200
        body = resp.json()
        assert body["source"] == "rules"
        assert body["tip"]


class TestLowLoadIsNotSilence:
    """An athlete training under their chronic load still gets a reading."""

    def test_undertrained_acwr_has_its_own_tip(self):
        from arete.services.coaching_rules import generate_daily_tip

        tip, priority = generate_daily_tip(0.41, -8.2, 65.5)
        assert "ACWR 0.41" in tip
        assert priority == "info"

    def test_generic_tip_only_without_any_metric(self):
        from arete.services.coaching_rules import generate_daily_tip

        tip, _ = generate_daily_tip(None, None, None)
        assert "Enregistre tes séances" in tip
