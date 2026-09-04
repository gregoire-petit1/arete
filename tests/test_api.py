"""Tests for the API endpoints."""

from fastapi.testclient import TestClient


class TestHealth:
    """Tests for /health endpoint."""

    def test_health_returns_ok(self, client: TestClient):
        """Health endpoint should return status ok with database info."""
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "database" in data


class TestPlanJour:
    """Tests for /plan/jour endpoint."""

    def test_plan_jour_returns_seance(self, client: TestClient):
        """Plan jour should return a session plan (stub for now)."""
        payload = {
            "date": "2025-12-01",
            "objectif": "10k_sub45",
            "dispo_min": 60,
            "fatigue": 3,
            "rpe_moy7j": 5.5,
        }
        response = client.post("/plan/jour", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert "seance" in data
        assert "cible" in data


class TestLogRecent:
    """Tests for /log/recent endpoint."""

    def test_log_recent_default_limit(self, client: TestClient):
        """Log recent should return rows with default limit."""
        response = client.get("/log/recent")
        assert response.status_code == 200
        data = response.json()
        assert "rows" in data
        assert isinstance(data["rows"], list)

    def test_log_recent_custom_limit(self, client: TestClient):
        """Log recent should respect custom limit parameter."""
        response = client.get("/log/recent?n=2")
        assert response.status_code == 200
        data = response.json()
        assert "rows" in data
        assert len(data["rows"]) <= 2

    def test_log_recent_invalid_limit_uses_default(self, client: TestClient):
        """Invalid n values should use safe defaults."""
        response = client.get("/log/recent?n=-5")
        assert response.status_code == 200

        response = client.get("/log/recent?n=999")
        assert response.status_code == 200


class TestSessions:
    """Tests for /sessions CRUD endpoints."""

    def test_create_session(self, client: TestClient):
        """Should create a new session."""
        payload = {
            "date": "2025-12-01",
            "objective": "Endurance",
            "duration": 60,
            "fatigue": 3,
            "rpe_avg7d": 5.0,
        }
        response = client.post("/plan/day", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["objective"] == "Endurance"
        assert data["duration"] == 60
        assert "id" in data

    def test_list_sessions(self, client: TestClient):
        """Should list sessions with pagination."""
        response = client.get("/sessions")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "items" in data
        assert isinstance(data["items"], list)

    def test_get_session_not_found(self, client: TestClient):
        """Should return 404 for non-existent session."""
        response = client.get("/sessions/99999")
        assert response.status_code == 404


class TestUser:
    """Tests for /user CRUD endpoints."""

    def test_create_and_get_user(self, client: TestClient):
        """Should create and retrieve user."""
        # Clean up any existing user first via API (delete if exists)
        from arete.dataio.db import connect

        con = connect(read_only=False)
        try:
            con.execute("DELETE FROM app.users")
        finally:
            con.close()

        payload = {
            "sex": "M",
            "age": 30,
            "height": 180.0,
            "weight": 75.0,
            "desired_training_load": 10.0,
        }
        response = client.post("/user", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["sex"] == "M"
        assert data["age"] == 30
        assert "bmi" in data
        assert data["bmi"] is not None

        # Get user
        response = client.get("/user")
        assert response.status_code == 200
        assert response.json()["sex"] == "M"

    def test_create_user_already_exists(self, client: TestClient):
        """Should return 400 if user already exists."""
        payload = {
            "sex": "F",
            "age": 25,
            "height": 165.0,
            "weight": 60.0,
        }
        # First creation might succeed or fail depending on state
        client.post("/user", json=payload)
        # Second creation should definitely fail
        response = client.post("/user", json=payload)
        assert response.status_code == 400


class TestObjectives:
    """Tests for /objectives CRUD endpoints."""

    def test_create_objective(self, client: TestClient):
        """Should create a new objective."""
        payload = {
            "sport": "Running",
            "name": "Marathon sub-3h",
            "priority": 2,
        }
        response = client.post("/objectives", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["sport"] == "Running"
        assert data["name"] == "Marathon sub-3h"
        assert data["priority"] == 2

    def test_list_objectives(self, client: TestClient):
        """Should list objectives."""
        response = client.get("/objectives")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "items" in data


class TestRecords:
    """Tests for /records CRUD endpoints."""

    def test_create_record(self, client: TestClient):
        """Should create a new personal record."""
        payload = {
            "sport": "Running",
            "event": "5k",
            "performance": 1200.0,
            "unit": "seconds",
        }
        response = client.post("/records", json=payload)
        assert response.status_code == 200
        data = response.json()
        assert data["sport"] == "Running"
        assert data["event"] == "5k"

    def test_list_records(self, client: TestClient):
        """Should list personal records."""
        response = client.get("/records")
        assert response.status_code == 200
        data = response.json()
        assert "total" in data
        assert "items" in data
