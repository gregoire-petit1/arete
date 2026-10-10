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

    def test_health_reports_the_schema_version(self, client: TestClient):
        from arete.dataio.init_duckdb import MIGRATIONS

        data = client.get("/health").json()
        assert data["database"] == "connected"
        assert data["schema_version"] == MIGRATIONS[-1][0]


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
        expected = {"athletes": {"1": {"sync": "ok"}}, "deferred": False}
        monkeypatch.setattr(scheduler, "run_scheduled_batch", lambda: expected)
        response = client.get(
            "/cron/daily-sync", headers={"Authorization": "Bearer right"}
        )
        assert response.status_code == 200
        assert response.json() == expected


def test_booting_the_app_leaves_the_heavy_stacks_out(tmp_path):
    """A cold serverless instance imports the app before its first request.

    The agent stack (LangChain, LangGraph, Deep Agents, LangSmith) took 1.4 s
    of the 1.5 s, and every route paid for it, /health included. It loads on
    the first coach request; Garmin's client and the workout grammars on
    their own routes.
    """
    import os
    import subprocess
    import sys

    heavy = [
        "deepagents",
        "langchain",
        "langchain_core",
        "langgraph",
        "langsmith",
        "anthropic",
        "openai",
        "garminconnect",
        "curl_cffi",
        "lark",
        "rapidfuzz",
        "pywebpush",
        "aiohttp",
        "clerk_backend_api",
        "jwt",
    ]
    code = (
        "import sys, arete.api.main; "
        f"print(sorted({{m.split('.')[0] for m in sys.modules}} & {set(heavy)!r}))"
    )
    env = {**os.environ, "ARETE_DB": str(tmp_path / "boot.duckdb")}
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, env=env
    )
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "[]"
