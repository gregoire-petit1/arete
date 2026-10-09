"""The morning's decisions applied to the plan, once, and taken back."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import pytest

from arete.dataio.db import connect
from arete.garmin.models import PlannedSession, SessionStatus, SessionType
from arete.garmin.repository import GarminRepository
from arete.services import plan_adaptation
from arete.services.coaching_rules import RuleFacts

#: Far enough ahead that no other test's "today" reaches it.
DAY = date.today() + timedelta(days=700)


def _facts(readiness: float | None, source: str = "garmin_training") -> RuleFacts:
    return RuleFacts(
        acwr=1.0,
        tsb=-5.0,
        readiness_score=readiness,
        fatigue_threshold=85,
        fitness_goal="build",
        readiness_source=source,
        readiness_measured_on=DAY,
    )


@pytest.fixture
def tempo():
    repo = GarminRepository()
    session_id = repo.create_planned_session(
        PlannedSession(
            date=DAY,
            sport="running",
            session_type=SessionType.TEMPO,
            target_duration_min=50,
            target_hr_zone="Z4",
            target_intensity="hard",
            description="3x10' au seuil",
        )
    )
    yield session_id
    con = connect()
    con.execute("DELETE FROM app.plan_decisions WHERE date = ?", [DAY])
    con.execute("DELETE FROM app.planned_sessions WHERE date = ?", [DAY])
    con.close()


def _adapt(readiness, **kwargs):
    with patch(
        "arete.services.coaching_rules.rule_facts", return_value=_facts(readiness)
    ):
        return plan_adaptation.adapt_today(DAY, **kwargs)


def test_a_middling_morning_eases_the_tempo_and_keeps_the_original(tempo):
    decisions = _adapt(70.0)
    assert [d.decision for d in decisions] == ["ease"]
    session = GarminRepository().get_planned_session(tempo)
    assert session is not None
    assert session.session_type == SessionType.ENDURANCE
    assert (session.target_hr_zone, session.target_duration_min) == ("Z2", 50)
    assert session.status == SessionStatus.MODIFIED
    assert decisions[0].original is not None
    assert decisions[0].original["session_type"] == "tempo"
    assert decisions[0].applied_at is not None


def test_a_second_run_the_same_day_decides_nothing_new(tempo):
    _adapt(70.0)
    again = _adapt(30.0)  # a worse reading later must not stack a second decision
    assert [d.decision for d in again] == ["ease"]


def test_revert_restores_the_session(tempo):
    decision = _adapt(70.0)[0]
    reverted = plan_adaptation.revert(decision.id)
    assert reverted.reverted_at is not None
    session = GarminRepository().get_planned_session(tempo)
    assert session is not None
    assert session.session_type == SessionType.TEMPO
    assert (session.target_hr_zone, session.status) == ("Z4", SessionStatus.PENDING)
    with pytest.raises(plan_adaptation.NothingToRevert):
        plan_adaptation.revert(decision.id)


def test_a_bad_morning_skips_the_session(tempo):
    assert [d.decision for d in _adapt(30.0)] == ["rest"]
    session = GarminRepository().get_planned_session(tempo)
    assert session is not None and session.status == SessionStatus.SKIPPED


def test_the_switch_off_writes_nothing_unless_asked(tempo):
    with patch.object(plan_adaptation, "auto_adapt_enabled", return_value=False):
        assert _adapt(30.0, respect_setting=True) == []
        assert [d.decision for d in _adapt(30.0, respect_setting=False)] == ["rest"]


def test_no_readiness_writes_nothing(tempo):
    assert _adapt(None) == []
    session = GarminRepository().get_planned_session(tempo)
    assert session is not None and session.status == SessionStatus.PENDING


def test_an_adapted_session_still_matches_the_run(tempo):
    from arete.garmin.models import ActualSession
    from arete.garmin.sync import auto_match

    _adapt(70.0)
    run = ActualSession(date=DAY, sport="running", duration_sec=50 * 60)
    repo = GarminRepository()
    actual_id = repo.create_actual_session(run)
    try:
        assert auto_match(repo, actual_id, run) == tempo
    finally:
        con = connect()
        con.execute("DELETE FROM app.actual_sessions WHERE id = ?", [actual_id])
        con.close()


def test_the_api_lists_adapts_and_reverts(tempo, router_client):
    from arete.api.plan import router

    client = router_client(router)
    with patch("arete.services.plan_adaptation.date") as fake_date:
        fake_date.today.return_value = DAY
        with patch(
            "arete.services.coaching_rules.rule_facts", return_value=_facts(50.0)
        ):
            adapted = client.post("/plan/today/adapt").json()
    assert [d["decision"] for d in adapted["decisions"]] == ["replace_easy"]
    decision_id = adapted["decisions"][0]["id"]
    assert client.post(f"/plan/decisions/{decision_id}/revert").status_code == 200
    assert client.post(f"/plan/decisions/{decision_id}/revert").status_code == 409
    assert client.post("/plan/decisions/999999/revert").status_code == 404
