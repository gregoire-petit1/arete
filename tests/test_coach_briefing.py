"""The daily briefing: produced once, stored, always with a floor under it.

The agent is never called for real here — these tests are about the contract
around it: the rule engine stays the floor, a failure stays visible without
reaching the dashboard, and the day's briefing is produced once.
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import pytest

from arete.coach.briefing import generate_briefing, get_or_create_briefing
from arete.coach.repository import BriefingRepository


@pytest.fixture
def repo():
    return BriefingRepository()


@pytest.fixture(autouse=True)
def clean_day(repo):
    """Each test owns its own day, so they cannot see each other's rows."""
    day = date(2031, 1, 1)
    repo.delete_for_day(day)
    yield day
    repo.delete_for_day(day)


@pytest.fixture
def enabled():
    with patch("arete.coach.briefing.briefing_enabled", return_value=True):
        yield


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class TestRepository:
    def test_a_failed_run_is_stored_but_never_served(self, repo, clean_day):
        repo.create(
            text="floor",
            briefing_date=clean_day,
            status="failed",
            source="agent",
            error="model is away",
        )
        assert repo.get_for_day(clean_day) is None
        assert [b.status for b in repo.list_recent()][0] == "failed"

    def test_a_later_success_wins_over_an_earlier_one(self, repo, clean_day):
        repo.create(text="first", briefing_date=clean_day, source="rules")
        repo.create(text="second", briefing_date=clean_day, source="agent")
        assert repo.get_for_day(clean_day).text == "second"

    def test_days_do_not_bleed_into_each_other(self, repo, clean_day):
        repo.create(text="yesterday", briefing_date=clean_day - timedelta(days=1))
        assert repo.get_for_day(clean_day) is None
        repo.delete_for_day(clean_day - timedelta(days=1))


# ---------------------------------------------------------------------------
# Producer
# ---------------------------------------------------------------------------


class TestGenerate:
    def test_the_agent_text_is_stored_with_the_rules_priority(
        self, repo, clean_day, enabled
    ):
        # The card's colour must not depend on a model.
        with (
            patch("arete.coach.briefing._run_agent", return_value="Ta charge monte."),
            patch("arete.coach.briefing._rule_floor", return_value=("floor", "alert")),
        ):
            b = generate_briefing(target_date=clean_day)
        assert b.text == "Ta charge monte."
        assert b.source == "agent"
        assert b.priority == "alert"

    def test_a_failed_run_falls_back_to_the_floor_and_records_why(
        self, repo, clean_day, enabled
    ):
        with (
            patch(
                "arete.coach.briefing._run_agent",
                side_effect=RuntimeError("model is away"),
            ),
            patch("arete.coach.briefing._rule_floor", return_value=("floor", "info")),
        ):
            b = generate_briefing(target_date=clean_day)

        assert b.text == "floor"
        assert b.source == "rules"
        rows = [r for r in repo.list_recent() if r.date == clean_day]
        failed = [r for r in rows if r.status == "failed"]
        assert failed and "model is away" in failed[0].error

    def test_disabled_stores_the_floor_without_calling_the_agent(self, clean_day):
        with (
            patch("arete.coach.briefing.briefing_enabled", return_value=False),
            patch("arete.coach.briefing._rule_floor", return_value=("floor", "info")),
            patch("arete.coach.briefing._run_agent") as run,
        ):
            b = generate_briefing(target_date=clean_day)
        run.assert_not_called()
        assert b.source == "rules"

    def test_a_broken_rule_engine_still_yields_something(self, clean_day):
        # The floor has a floor: the dashboard is never empty.
        with (
            patch("arete.coach.briefing.briefing_enabled", return_value=False),
            patch(
                "arete.api.ai_tips.daily_rule_tip", side_effect=RuntimeError("no data")
            ),
        ):
            b = generate_briefing(target_date=clean_day)
        assert b.text and b.priority == "info"

    def test_an_overlong_briefing_is_refused(self, clean_day, enabled):
        from arete.coach.briefing import MAX_BRIEFING_CHARS

        class _Msg:
            text = "x" * (MAX_BRIEFING_CHARS + 1)

        with (
            patch("arete.agent.execution.invoke_agent") as build,
            patch("arete.coach.briefing._rule_floor", return_value=("floor", "info")),
        ):
            build.return_value = {"messages": [_Msg()]}
            b = generate_briefing(target_date=clean_day)
        # Refused, so the floor is served and the failure is on record.
        assert b.source == "rules"

    def test_an_empty_answer_is_refused(self, clean_day, enabled):
        class _Msg:
            text = "   "

        with (
            patch("arete.agent.execution.invoke_agent") as build,
            patch("arete.coach.briefing._rule_floor", return_value=("floor", "info")),
        ):
            build.return_value = {"messages": [_Msg()]}
            b = generate_briefing(target_date=clean_day)
        assert b.source == "rules"


class TestGetOrCreate:
    def test_the_day_is_produced_once(self, clean_day, enabled):
        with (
            patch("arete.coach.briefing._run_agent", return_value="written") as run,
            patch("arete.coach.briefing._rule_floor", return_value=("floor", "info")),
        ):
            first = get_or_create_briefing(target_date=clean_day)
            second = get_or_create_briefing(target_date=clean_day)

        assert run.call_count == 1
        assert first.id == second.id
        assert second.text == "written"

    def test_the_trigger_is_recorded(self, repo, clean_day, enabled):
        with (
            patch("arete.coach.briefing._run_agent", return_value="written"),
            patch("arete.coach.briefing._rule_floor", return_value=("floor", "info")),
        ):
            b = get_or_create_briefing(target_date=clean_day, trigger="scheduler")
        assert b.trigger == "scheduler"


# ---------------------------------------------------------------------------
# The journal the briefing writes into every morning must stay bounded
# ---------------------------------------------------------------------------


class TestLedgerRotation:
    @pytest.fixture
    def ledger(self, tmp_path, monkeypatch):
        from arete.agent import filesystem as fs

        root = tmp_path / "memory"
        root.mkdir()
        monkeypatch.setattr(fs, "memory_root", lambda: root)
        return root / fs.SESSIONS_LEDGER

    def _entries(self, count: int) -> str:
        return "".join(
            f"## 2026-09-{i:02d} — séance {i}\n" + "x" * 900 + "\n\n"
            for i in range(1, count + 1)
        )

    def test_a_small_ledger_is_left_alone(self, ledger):
        from arete.agent.filesystem import rotate_sessions_ledger

        ledger.write_text(self._entries(3), encoding="utf-8")
        before = ledger.read_text(encoding="utf-8")
        assert rotate_sessions_ledger() is None
        assert ledger.read_text(encoding="utf-8") == before

    def test_an_overgrown_ledger_is_split_on_an_entry(self, ledger):
        from arete.agent.filesystem import (
            MAX_SESSIONS_LEDGER_CHARS,
            rotate_sessions_ledger,
        )

        ledger.write_text(self._entries(60), encoding="utf-8")
        archive = rotate_sessions_ledger()

        assert archive is not None and archive.exists()
        kept = ledger.read_text(encoding="utf-8")
        assert len(kept) < MAX_SESSIONS_LEDGER_CHARS
        # Never mid-entry: half a session reads as a different session.
        assert kept.startswith("## ")
        # Nothing is lost, it just moved.
        assert "séance 1\n" in archive.read_text(encoding="utf-8")

    def test_rotation_is_idempotent(self, ledger):
        from arete.agent.filesystem import rotate_sessions_ledger

        ledger.write_text(self._entries(60), encoding="utf-8")
        assert rotate_sessions_ledger() is not None
        assert rotate_sessions_ledger() is None

    def test_a_missing_ledger_is_not_an_error(self, ledger):
        from arete.agent.filesystem import rotate_sessions_ledger

        assert rotate_sessions_ledger() is None


# ---------------------------------------------------------------------------
# Post-session feedback: same floor contract, plus a journal entry
# ---------------------------------------------------------------------------


class TestSessionFeedback:
    def test_the_agent_text_wins_when_the_run_succeeds(self):
        from arete.coach.session_feedback import enrich_session_feedback

        with patch(
            "arete.coach.session_feedback._run_agent", return_value="Belle séance."
        ):
            text, source = enrich_session_feedback("Séance terminée.", ["10 km"])
        assert (text, source) == ("Belle séance.", "agent")

    def test_a_failed_run_returns_the_rule_text(self):
        from arete.coach.session_feedback import enrich_session_feedback

        with patch(
            "arete.coach.session_feedback._run_agent",
            side_effect=RuntimeError("model is away"),
        ):
            text, source = enrich_session_feedback("Séance terminée.", ["10 km"])
        # An athlete who just uploaded a session gets an answer either way.
        assert (text, source) == ("Séance terminée.", "rules")

    def test_the_highlights_reach_the_agent_as_facts(self):
        from arete.coach.session_feedback import enrich_session_feedback

        with patch("arete.coach.session_feedback._run_agent", return_value="ok") as run:
            enrich_session_feedback("Séance terminée.", ["10 km", "FC 150"])
        facts = run.call_args[0][0]
        assert "Séance terminée." in facts
        assert "- 10 km" in facts and "- FC 150" in facts

    def test_no_highlights_is_not_an_empty_bullet_list(self):
        from arete.coach.session_feedback import enrich_session_feedback

        with patch("arete.coach.session_feedback._run_agent", return_value="ok") as run:
            enrich_session_feedback("Séance terminée.", [])
        assert run.call_args[0][0] == "Séance terminée."

    def test_an_overlong_answer_is_refused(self):
        from arete.coach.session_feedback import MAX_FEEDBACK_CHARS, _run_agent

        class _Msg:
            text = "x" * (MAX_FEEDBACK_CHARS + 1)

        with patch("arete.agent.execution.invoke_agent") as build:
            build.return_value = {"messages": [_Msg()]}
            with pytest.raises(RuntimeError, match="too long"):
                _run_agent("facts")
