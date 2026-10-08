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


class TestCronDailySync:
    """Vercel Cron triggers the daily sync through /cron/daily-sync."""

    def test_closed_without_a_configured_secret(self, client: TestClient, monkeypatch):
        monkeypatch.delenv("CRON_SECRET", raising=False)
        assert client.get("/cron/daily-sync").status_code == 401

    def test_rejects_a_wrong_secret(self, client: TestClient, monkeypatch):
        monkeypatch.setenv("CRON_SECRET", "right")
        response = client.get(
            "/cron/daily-sync", headers={"Authorization": "Bearer wrong"}
        )
        assert response.status_code == 401

    def test_runs_the_sync_with_the_right_secret(self, client: TestClient, monkeypatch):
        from arete import scheduler

        monkeypatch.setenv("CRON_SECRET", "right")
        recorded: list[object] = []
        monkeypatch.setattr(scheduler, "daily_sync", lambda: {"garmin": "ok"})
        monkeypatch.setattr(scheduler, "record_run", recorded.append)
        monkeypatch.setattr(scheduler, "write_daily_briefing", lambda: "rules")
        response = client.get(
            "/cron/daily-sync", headers={"Authorization": "Bearer right"}
        )
        assert response.status_code == 200
        assert response.json() == {"garmin": "ok", "briefing": "rules"}
        assert len(recorded) == 1
