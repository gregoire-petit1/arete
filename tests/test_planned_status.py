"""Manual status changes on planned sessions and the richer actual-session payload."""

from __future__ import annotations

from datetime import date, datetime

import pytest

from arete.api.garmin import router
from arete.garmin.models import (
    ActivitySource,
    ActualSession,
    PlannedSession,
    SessionStatus,
    SessionType,
)
from arete.garmin.repository import GarminRepository


@pytest.fixture
def client(router_client):
    return router_client(router)


@pytest.fixture
def repo():
    return GarminRepository()


class TestPlannedStatus:
    def test_patch_marks_completed_then_pending(self, client, repo):
        pid = repo.create_planned_session(
            PlannedSession(
                date=date(2031, 7, 1), sport="running", session_type=SessionType.TEMPO
            )
        )
        try:
            resp = client.patch(f"/garmin/planned/{pid}", json={"status": "completed"})
            assert resp.status_code == 200
            assert resp.json()["status"] == "completed"

            resp = client.patch(f"/garmin/planned/{pid}", json={"status": "pending"})
            assert resp.json()["status"] == "pending"
        finally:
            repo.delete_planned_session(pid)

    def test_patch_unknown_session(self, client):
        assert (
            client.patch(
                "/garmin/planned/999999", json={"status": "skipped"}
            ).status_code
            == 404
        )

    def test_patch_rejects_unknown_status(self, client):
        assert (
            client.patch("/garmin/planned/1", json={"status": "napping"}).status_code
            == 422
        )


class TestActualSessionPayload:
    def test_exposes_the_fields_the_ui_reads(self, client, repo):
        sid = repo.create_actual_session(
            ActualSession(
                date=date(2031, 7, 2),
                sport="running",
                session_type="running",
                name="Sortie test",
                duration_sec=3300,
                moving_time_sec=3250,
                distance_m=10400.0,
                avg_hr=166,
                avg_pace_sec_km=300,
                ascent_m=120.0,
                calories=700,
                source=ActivitySource.GARMIN_CONNECT,
                garmin_activity_id="42",
                start_time=datetime(2031, 7, 2, 18, 30),
            )
        )
        try:
            resp = client.get(
                "/garmin/actual?start_date=2031-07-02&end_date=2031-07-02"
            )
            assert resp.status_code == 200
            body = next(s for s in resp.json() if s["id"] == sid)
            assert body["name"] == "Sortie test"
            assert body["duration_sec"] == 3300
            assert body["avg_pace_sec_km"] == 300
            assert body["duration_min"] == "55:00" and body["avg_pace"] == "5:00"
            assert body["distance_km"] == 10.4 and body["calories"] == 700
            assert body["garmin_activity_id"] == "42"
            assert body["strava_activity_id"] is None
        finally:
            repo.delete_actual_session(sid)


class TestManualCardioEntry:
    def test_creates_and_matches_the_plan(self, client, repo):
        pid = repo.create_planned_session(
            PlannedSession(
                date=date(2031, 8, 3),
                sport="running",
                session_type=SessionType.ENDURANCE,
                target_duration_min=50,
            )
        )
        try:
            resp = client.post(
                "/garmin/actual",
                json={
                    "date": "2031-08-03",
                    "sport": "running",
                    "name": "Footing sans montre",
                    "duration_min": 50,
                    "distance_km": 10.0,
                    "avg_hr": 145,
                    "rpe": 5,
                },
            )
            assert resp.status_code == 201
            body = resp.json()
            assert body["source"] == "manual"
            assert body["duration_sec"] == 3000
            assert body["avg_pace_sec_km"] == 300  # 50 min for 10 km
            assert body["planned_session_id"] == pid

            planned = repo.get_planned_session(pid)
            assert planned is not None and planned.status == SessionStatus.COMPLETED
            repo.delete_actual_session(body["id"])
        finally:
            repo.delete_planned_session(pid)

    def test_rejects_impossible_duration(self, client):
        resp = client.post(
            "/garmin/actual", json={"date": "2031-08-03", "duration_min": 0}
        )
        assert resp.status_code == 422
