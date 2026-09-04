"""Tests for Garmin pipeline module."""

from datetime import date, timedelta

import pytest

from arete.garmin.matcher import SessionMatcher
from arete.garmin.models import (
    ActivitySource,
    ActualSession,
    MatchConfidence,
    PlannedSession,
    SessionStatus,
    SessionType,
)
from arete.garmin.repository import GarminRepository

# ─────────────────────────────────────────────────────────────────────────
# Model Tests
# ─────────────────────────────────────────────────────────────────────────


class TestPlannedSession:
    """Tests for PlannedSession model."""

    def test_defaults(self):
        """Test default values."""
        session = PlannedSession()
        assert session.id is None
        assert session.sport == "running"
        assert session.session_type == SessionType.ENDURANCE
        assert session.status == SessionStatus.PENDING

    def test_to_dict(self):
        """Test conversion to dictionary."""
        session = PlannedSession(
            date=date(2024, 6, 15),
            session_type=SessionType.INTERVALS,
            target_duration_min=45,
            description="4x800m",
        )
        d = session.to_dict()
        assert d["date"] == date(2024, 6, 15)
        assert d["session_type"] == "intervals"
        assert d["target_duration_min"] == 45


class TestActualSession:
    """Tests for ActualSession model."""

    def test_defaults(self):
        """Test default values."""
        session = ActualSession()
        assert session.id is None
        assert session.sport == "running"
        assert session.source == ActivitySource.FIT_FILE

    def test_duration_min(self):
        """Test duration_min property returns formatted string."""
        session = ActualSession(duration_sec=3600)
        assert session.duration_min == "60:00"
        assert session.duration_min_raw == 60.0

    def test_distance_km(self):
        """Test distance_km property rounds to 2 decimals."""
        session = ActualSession(distance_m=10000)
        assert session.distance_km == 10.0
        # Test rounding
        session2 = ActualSession(distance_m=6686.229999)
        assert session2.distance_km == 6.69

    def test_avg_pace_min_km(self):
        """Test average pace formatting."""
        session = ActualSession(avg_pace_sec_km=300)  # 5:00/km
        assert session.avg_pace_min_km == "5:00"

        session2 = ActualSession(avg_pace_sec_km=330)  # 5:30/km
        assert session2.avg_pace_min_km == "5:30"


# ─────────────────────────────────────────────────────────────────────────
# Matcher Tests
# ─────────────────────────────────────────────────────────────────────────


class TestSessionMatcher:
    """Tests for SessionMatcher."""

    def test_exact_match(self):
        """Test matching with same date and type."""
        matcher = SessionMatcher()

        actual = ActualSession(
            date=date(2024, 6, 15),
            sport="running",
            duration_sec=2700,  # 45 min
        )

        planned = [
            PlannedSession(
                id=1,
                date=date(2024, 6, 15),
                session_type=SessionType.ENDURANCE,
                target_duration_min=45,
            )
        ]

        result = matcher.find_match(actual, planned)
        assert result.is_matched
        assert result.confidence == MatchConfidence.HIGH
        assert result.planned_session.id == 1

    def test_duration_deviation(self):
        """Test adherence calculation with duration deviation."""
        matcher = SessionMatcher()

        actual = ActualSession(
            date=date(2024, 6, 15),
            sport="running",
            duration_sec=2400,  # 40 min (vs 60 planned = 33% short)
        )

        planned = [
            PlannedSession(
                id=1,
                date=date(2024, 6, 15),
                session_type=SessionType.ENDURANCE,
                target_duration_min=60,
            )
        ]

        result = matcher.find_match(actual, planned)
        assert result.is_matched
        # 40/60 = 66.7% adherence (rounded to 70% by the algorithm)
        assert 65 <= result.adherence_score <= 75

    def test_no_match_different_date(self):
        """Test no match when date is too different."""
        from arete.garmin.matcher import MatchingConfig

        config = MatchingConfig(date_tolerance_days=1)
        matcher = SessionMatcher(config=config)

        actual = ActualSession(
            date=date(2024, 6, 20),
            sport="running",
            duration_sec=2700,
        )

        planned = [
            PlannedSession(
                id=1,
                date=date(2024, 6, 15),  # 5 days earlier
                session_type=SessionType.ENDURANCE,
                target_duration_min=45,
            )
        ]

        result = matcher.find_match(actual, planned)
        assert not result.is_matched
        assert result.confidence == MatchConfidence.NONE

    def test_best_match_selection(self):
        """Test selection of best match from multiple options."""
        matcher = SessionMatcher()

        actual = ActualSession(
            date=date(2024, 6, 15),
            sport="running",
            duration_sec=3600,  # 60 min
        )

        planned = [
            PlannedSession(
                id=1,
                date=date(2024, 6, 15),
                session_type=SessionType.RECOVERY,
                target_duration_min=30,  # Poor match
            ),
            PlannedSession(
                id=2,
                date=date(2024, 6, 15),
                session_type=SessionType.ENDURANCE,
                target_duration_min=60,  # Perfect match
            ),
        ]

        result = matcher.find_match(actual, planned)
        assert result.is_matched
        assert result.planned_session.id == 2  # Should pick the better match


# ─────────────────────────────────────────────────────────────────────────
# Repository Tests
# ─────────────────────────────────────────────────────────────────────────


@pytest.fixture
def repo():
    """Get repository instance."""
    return GarminRepository()


class TestGarminRepository:
    """Tests for GarminRepository."""

    def test_create_and_get_planned_session(self, repo):
        """Test creating and retrieving a planned session."""
        session = PlannedSession(
            date=date.today(),
            sport="running",
            session_type=SessionType.TEMPO,
            target_duration_min=40,
            description="Tempo test",
        )

        session_id = repo.create_planned_session(session)
        assert session_id is not None
        assert isinstance(session_id, int)

        retrieved = repo.get_planned_session(session_id)
        assert retrieved is not None
        assert retrieved.date == date.today()
        assert retrieved.session_type == SessionType.TEMPO
        assert retrieved.target_duration_min == 40

        # Cleanup
        repo.delete_planned_session(session_id)

    def test_list_planned_sessions(self, repo):
        """Test listing planned sessions with filters."""
        # Create test sessions
        today = date.today()
        ids = []

        for i in range(3):
            session = PlannedSession(
                date=today + timedelta(days=i),
                session_type=SessionType.ENDURANCE,
                target_duration_min=45 + i * 15,
            )
            ids.append(repo.create_planned_session(session))

        # List all
        sessions = repo.list_planned_sessions(limit=10)
        assert len(sessions) >= 3

        # Filter by date range
        sessions = repo.list_planned_sessions(
            start_date=today,
            end_date=today + timedelta(days=1),
        )
        assert len(sessions) >= 2

        # Cleanup
        for session_id in ids:
            repo.delete_planned_session(session_id)

    def test_update_planned_session_status(self, repo):
        """Test updating session status."""
        session = PlannedSession(
            date=date.today(),
            session_type=SessionType.ENDURANCE,
        )
        session_id = repo.create_planned_session(session)

        # Update status
        success = repo.update_planned_session_status(session_id, SessionStatus.COMPLETED)
        assert success

        # Verify
        updated = repo.get_planned_session(session_id)
        assert updated.status == SessionStatus.COMPLETED

        # Cleanup
        repo.delete_planned_session(session_id)

    def test_create_and_get_actual_session(self, repo):
        """Test creating and retrieving an actual session."""
        session = ActualSession(
            date=date.today(),
            sport="running",
            duration_sec=2700,
            distance_m=8000,
            avg_hr=145,
            source=ActivitySource.FIT_FILE,
        )

        session_id = repo.create_actual_session(session)
        assert session_id is not None

        retrieved = repo.get_actual_session(session_id)
        assert retrieved is not None
        assert retrieved.date == date.today()
        assert retrieved.duration_sec == 2700
        assert retrieved.avg_hr == 145

        # Cleanup
        repo.delete_actual_session(session_id)

    def test_match_actual_to_planned(self, repo):
        """Test matching actual session to planned session."""
        # Create planned session
        planned = PlannedSession(
            date=date.today(),
            session_type=SessionType.ENDURANCE,
            target_duration_min=45,
        )
        planned_id = repo.create_planned_session(planned)

        # Create actual session
        actual = ActualSession(
            date=date.today(),
            duration_sec=2700,
        )
        actual_id = repo.create_actual_session(actual)

        # Match them
        success = repo.update_actual_session_match(actual_id, planned_id, adherence_score=95.0)
        assert success

        # Verify
        updated = repo.get_actual_session(actual_id)
        assert updated.planned_session_id == planned_id
        assert updated.adherence_score == 95.0

        # Cleanup
        repo.delete_actual_session(actual_id)
        repo.delete_planned_session(planned_id)

    def test_get_matches_summary(self, repo):
        """Test getting match summary statistics."""
        summary = repo.get_matches_summary()

        assert "total_planned" in summary
        assert "total_actual" in summary
        assert "total_matched" in summary
        assert "total_unmatched" in summary
        assert "adherence_rate" in summary

    def test_get_potential_matches(self, repo):
        """Test getting potential matches for an actual session."""
        # Create planned session for today
        planned = PlannedSession(
            date=date.today(),
            session_type=SessionType.ENDURANCE,
            target_duration_min=60,
        )
        planned_id = repo.create_planned_session(planned)

        # Create actual session
        actual = ActualSession(date=date.today(), duration_sec=3600)

        # Get potential matches
        matches = repo.get_potential_matches(actual)
        assert len(matches) >= 1
        assert any(m.id == planned_id for m in matches)

        # Cleanup
        repo.delete_planned_session(planned_id)


# ─────────────────────────────────────────────────────────────────────────
# Integration Tests
# ─────────────────────────────────────────────────────────────────────────


class TestGarminIntegration:
    """Integration tests for Garmin pipeline."""

    def test_full_workflow(self, repo):
        """Test complete workflow: plan -> execute -> match -> analyze."""
        # 1. Coach creates a training plan
        planned_sessions = [
            PlannedSession(
                date=date.today(),
                session_type=SessionType.ENDURANCE,
                target_duration_min=60,
                target_intensity="moderate",
                description="Easy long run",
                source="coach",
            ),
            PlannedSession(
                date=date.today() + timedelta(days=1),
                session_type=SessionType.INTERVALS,
                target_duration_min=45,
                target_intensity="hard",
                description="6x400m",
                source="coach",
            ),
        ]

        planned_ids = [repo.create_planned_session(s) for s in planned_sessions]

        # 2. Athlete executes the first workout (slightly different)
        actual = ActualSession(
            date=date.today(),
            sport="running",
            duration_sec=3300,  # 55 min instead of 60
            distance_m=10500,
            avg_hr=142,
            max_hr=158,
            source=ActivitySource.FIT_FILE,
        )

        actual_id = repo.create_actual_session(actual)

        # 3. Match actual to planned
        matcher = SessionMatcher()
        potential_matches = repo.get_potential_matches(actual)
        match = matcher.find_match(actual, potential_matches)

        assert match.is_matched
        assert match.confidence in [MatchConfidence.HIGH, MatchConfidence.MEDIUM]
        assert match.adherence_score > 80  # Should be good adherence

        # 4. Save the match
        repo.update_actual_session_match(actual_id, match.planned_session.id, match.adherence_score)
        repo.update_planned_session_status(match.planned_session.id, SessionStatus.COMPLETED)

        # 5. Check summary
        summary = repo.get_matches_summary()
        assert summary["total_matched"] >= 1
        assert summary["adherence_rate"] > 0

        # Cleanup
        repo.delete_actual_session(actual_id)
        for pid in planned_ids:
            repo.delete_planned_session(pid)
