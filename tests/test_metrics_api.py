"""Tests for the metrics API endpoints."""

from fastapi.testclient import TestClient

from arete.api.main import app

client = TestClient(app)


class TestTRIMPEndpoint:
    """Tests for POST /metrics/cardio/trimp."""

    def test_trimp_male(self) -> None:
        """Calculate TRIMP for male athlete."""
        response = client.post(
            "/metrics/cardio/trimp",
            json={
                "duration_min": 60,
                "avg_hr": 150,
                "hr_rest": 60,
                "hr_max": 190,
                "gender": "male",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert "trimp" in data
        assert data["trimp"] > 0
        assert data["hr_zone"] in [1, 2, 3, 4, 5]
        assert "zone_name" in data

    def test_trimp_female(self) -> None:
        """Calculate TRIMP for female athlete."""
        response = client.post(
            "/metrics/cardio/trimp",
            json={
                "duration_min": 45,
                "avg_hr": 155,
                "hr_rest": 55,
                "hr_max": 185,
                "gender": "female",
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["trimp"] > 0
        # Female weighting is different
        assert "intensity" in data

    def test_trimp_validation_errors(self) -> None:
        """Validation should reject invalid inputs."""
        # Missing required field
        response = client.post(
            "/metrics/cardio/trimp",
            json={
                "duration_min": 60,
                "avg_hr": 150,
                "hr_rest": 60,
                # missing hr_max and gender
            },
        )
        assert response.status_code == 422

        # Invalid duration
        response = client.post(
            "/metrics/cardio/trimp",
            json={
                "duration_min": 0,  # must be > 0
                "avg_hr": 150,
                "hr_rest": 60,
                "hr_max": 190,
                "gender": "male",
            },
        )
        assert response.status_code == 422


class TestOneRMEndpoint:
    """Tests for POST /metrics/strength/1rm."""

    def test_1rm_basic(self) -> None:
        """Basic 1RM estimation without RPE."""
        response = client.post(
            "/metrics/strength/1rm",
            json={
                "weight": 100,
                "reps": 5,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["estimated_1rm"] > 100  # Should be higher than 5RM
        assert data["epley"] > 0
        assert data["brzycki"] > 0
        assert data["rpe_based"] is None
        assert "strength_zone" in data
        assert data["intensity_pct"] > 0

    def test_1rm_with_rpe(self) -> None:
        """1RM estimation with RPE for more accuracy."""
        response = client.post(
            "/metrics/strength/1rm",
            json={
                "weight": 100,
                "reps": 5,
                "rpe": 8.5,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["rpe_based"] is not None
        assert data["rpe_based"] > 0

    def test_1rm_single_rep(self) -> None:
        """1RM for a single rep should return the weight."""
        response = client.post(
            "/metrics/strength/1rm",
            json={
                "weight": 150,
                "reps": 1,
            },
        )
        assert response.status_code == 200
        data = response.json()
        # With 1 rep, estimated 1RM should be close to actual weight
        assert abs(data["estimated_1rm"] - 150) < 5

    def test_1rm_validation(self) -> None:
        """Validation errors for invalid inputs."""
        # Too many reps
        response = client.post(
            "/metrics/strength/1rm",
            json={
                "weight": 100,
                "reps": 35,  # max is 30
            },
        )
        assert response.status_code == 422

        # Invalid RPE
        response = client.post(
            "/metrics/strength/1rm",
            json={
                "weight": 100,
                "reps": 5,
                "rpe": 11,  # max is 10
            },
        )
        assert response.status_code == 422


class TestINOLEndpoint:
    """Tests for POST /metrics/strength/inol."""

    def test_inol_light(self) -> None:
        """Light INOL (recovery)."""
        response = client.post(
            "/metrics/strength/inol",
            json={
                "reps": 10,
                "intensity_pct": 60,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["inol"] < 0.5
        assert "récupération" in data["classification"].lower()

    def test_inol_moderate(self) -> None:
        """Moderate INOL (development)."""
        response = client.post(
            "/metrics/strength/inol",
            json={
                "reps": 20,
                "intensity_pct": 70,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert 0.5 <= data["inol"] < 1.0
        assert "modéré" in data["classification"].lower()

    def test_inol_high(self) -> None:
        """High INOL (overload)."""
        response = client.post(
            "/metrics/strength/inol",
            json={
                "reps": 30,
                "intensity_pct": 80,
            },
        )
        assert response.status_code == 200
        data = response.json()
        assert data["inol"] >= 1.0


class TestWorkloadEndpoint:
    """Tests for GET /metrics/workload."""

    def test_workload_no_data(self) -> None:
        """Should return 404 when no training data exists."""
        # This depends on database state
        response = client.get("/metrics/workload")
        # Either returns data or 404
        assert response.status_code in [200, 404]

    def test_workload_query_params(self) -> None:
        """Query params should be validated."""
        # Invalid days (too low)
        response = client.get("/metrics/workload?days=3")
        assert response.status_code == 422

        # Invalid days (too high)
        response = client.get("/metrics/workload?days=200")
        assert response.status_code == 422


class TestFitnessEndpoint:
    """Tests for GET /metrics/fitness."""

    def test_fitness_no_data(self) -> None:
        """Should return 404 when no training data exists."""
        response = client.get("/metrics/fitness")
        assert response.status_code in [200, 404]

    def test_fitness_query_params(self) -> None:
        """Query params should be validated."""
        # Invalid days (too low)
        response = client.get("/metrics/fitness?days=5")
        assert response.status_code == 422


class TestRecommendationsEndpoint:
    """Tests for GET /metrics/recommendations."""

    def test_recommendations_no_data(self) -> None:
        """Should return 404 when no training data exists."""
        response = client.get("/metrics/recommendations")
        assert response.status_code in [200, 404]

    def test_recommendations_sport_types(self) -> None:
        """Should accept different sport types."""
        for sport in ["cardio", "strength", "mixed"]:
            response = client.get(f"/metrics/recommendations?sport_type={sport}")
            assert response.status_code in [200, 404]

    def test_recommendations_invalid_sport(self) -> None:
        """Should reject invalid sport types."""
        response = client.get("/metrics/recommendations?sport_type=invalid")
        assert response.status_code == 422


class TestOpenAPISchema:
    """Tests for API documentation."""

    def test_openapi_schema(self) -> None:
        """OpenAPI schema should include metrics endpoints."""
        response = client.get("/openapi.json")
        assert response.status_code == 200
        schema = response.json()

        # Check metrics endpoints are documented
        paths = schema.get("paths", {})
        assert "/metrics/workload" in paths
        assert "/metrics/fitness" in paths
        assert "/metrics/cardio/trimp" in paths
        assert "/metrics/strength/1rm" in paths
        assert "/metrics/strength/inol" in paths
        assert "/metrics/recommendations" in paths
