"""Tests for the data layer (repository, ingestion)."""

import pytest


@pytest.mark.usefixtures("setup_test_db")
class TestRepository:
    """Tests for repository functions."""

    def test_create_and_get_session(self):
        """Should create and retrieve a session."""
        from datetime import date

        from arete.dataio import repository as repo

        session = repo.create_session(
            session_date=date(2025, 12, 1),
            objective="Test session",
            duration=45,
            fatigue=3,
            rpe_avg7d=5.0,
        )
        assert session["objective"] == "Test session"
        assert session["duration"] == 45
        assert "id" in session

        # Retrieve it
        retrieved = repo.get_session(session["id"])
        assert retrieved is not None
        assert retrieved["id"] == session["id"]

    def test_delete_session(self):
        """Should delete a session."""
        from datetime import date

        from arete.dataio import repository as repo

        session = repo.create_session(
            session_date=date(2025, 12, 1),
            objective="To delete",
            duration=30,
            fatigue=2,
            rpe_avg7d=None,
        )
        session_id = session["id"]

        # Delete
        result = repo.delete_session(session_id)
        assert result is True

        # Should not exist anymore
        assert repo.get_session(session_id) is None

        # Deleting again should return False
        result = repo.delete_session(session_id)
        assert result is False

    def test_list_sessions_pagination(self):
        """Should paginate sessions correctly."""
        from datetime import date

        from arete.dataio import repository as repo

        # Create a few sessions
        for i in range(5):
            repo.create_session(
                session_date=date(2025, 12, i + 1),
                objective=f"Session {i}",
                duration=30 + i * 10,
                fatigue=i % 5,
                rpe_avg7d=None,
            )

        total, items = repo.list_sessions(skip=0, limit=3)
        assert total >= 5
        assert len(items) == 3

        total2, items2 = repo.list_sessions(skip=3, limit=3)
        assert len(items2) <= 3


@pytest.mark.usefixtures("setup_test_db")
class TestObjectivesRepository:
    """Tests for objectives repository functions."""

    def test_create_and_list_objectives(self):
        """Should create and list objectives."""
        from arete.dataio import repository as repo

        obj = repo.create_objective(
            sport="Cycling",
            name="Century ride",
            priority=1,
        )
        assert obj["sport"] == "Cycling"
        assert "id" in obj

        total, items = repo.list_objectives(skip=0, limit=10)
        assert total >= 1
        assert any(o["name"] == "Century ride" for o in items)


@pytest.mark.usefixtures("setup_test_db")
class TestRecordsRepository:
    """Tests for personal records repository functions."""

    def test_create_and_update_record(self):
        """Should create and update a personal record."""
        from arete.dataio import repository as repo

        record = repo.create_record(
            sport="Running",
            event="10k",
            performance=2400.0,
            unit="seconds",
        )
        assert record["performance"] == 2400.0

        # Update it
        updated = repo.update_record(
            record["id"],
            sport="Running",
            event="10k",
            performance=2350.0,
            unit="seconds",
        )
        assert updated is not None
        assert updated["performance"] == 2350.0
