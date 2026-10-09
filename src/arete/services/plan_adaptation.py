"""Apply the morning's decisions to today's plan, and take them back.

``adaptation.evaluate`` decides; this module reads the facts, claims one
decision per session and day, writes the planned session and keeps what it
replaced so the athlete can revert in one tap. Called by the daily run (after
the health sync, before the briefing) and by ``POST /plan/today/adapt``.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any

from arete.dataio.settings import get_user_settings
from arete.garmin.models import PlannedSession, SessionStatus
from arete.garmin.repository import GarminRepository
from arete.services.adaptation import AdaptationInput, Decision, evaluate
from arete.services.plan_repository import (
    AlreadyDecided,
    PlanDecision,
    PlanDecisionRepository,
)

logger = logging.getLogger(__name__)

#: The planning fields a decision may overwrite, saved before it does.
_PLAN_FIELDS = (
    "session_type",
    "target_duration_min",
    "target_hr_zone",
    "target_intensity",
    "description",
    "status",
)


def _snapshot(session: PlannedSession) -> dict[str, Any]:
    return {
        "session_type": session.session_type.value,
        "target_duration_min": session.target_duration_min,
        "target_hr_zone": session.target_hr_zone,
        "target_intensity": session.target_intensity,
        "description": session.description,
        "status": session.status.value,
    }


def auto_adapt_enabled(user_id: int = 1) -> bool:
    return bool((get_user_settings(user_id) or {}).get("auto_adapt_enabled", True))


def adapt_today(
    target_date: date | None = None, *, respect_setting: bool = True
) -> list[PlanDecision]:
    """Decide once for each of the day's planned sessions; the day's decisions.

    ``respect_setting`` is the daily run's: with the switch off it writes
    nothing. An explicit request from the athlete ignores it.
    """
    from arete.services.coaching_rules import rule_facts

    day = target_date or date.today()
    decisions = PlanDecisionRepository()
    if respect_setting and not auto_adapt_enabled():
        return decisions.list_for_day(day)

    planned_repo = GarminRepository()
    sessions = planned_repo.list_planned_sessions(
        start_date=day, end_date=day, status=None, limit=10, ascending=True
    )
    decided = {d.planned_session_id for d in decisions.list_for_day(day)}
    pending = [s for s in sessions if s.id is not None and s.id not in decided]
    if not pending:
        return decisions.list_for_day(day)

    facts = rule_facts(day)
    for session in pending:
        assert session.id is not None
        outcome = evaluate(
            AdaptationInput(
                session_type=session.session_type.value,
                sport=session.sport,
                status=session.status.value,
                target_duration_min=session.target_duration_min,
                target_hr_zone=session.target_hr_zone,
                target_intensity=session.target_intensity,
                description=session.description,
                readiness=facts.readiness_score,
                readiness_source=facts.readiness_source,
                acwr=facts.acwr,
                tsb=facts.tsb,
                fitness_goal=facts.fitness_goal,
            )
        )
        if outcome is None:
            continue
        try:
            decision = decisions.create(
                day=day,
                planned_session_id=session.id,
                decision=outcome.decision.value,
                reason=outcome.reason,
                readiness_score=facts.readiness_score,
                readiness_source=facts.readiness_source,
                acwr=facts.acwr,
                original=_snapshot(session),
                adapted=outcome.adapted or None,
            )
        except AlreadyDecided:
            continue  # another run claimed it first: its decision stands
        if outcome.decision in (Decision.EASE, Decision.REPLACE_EASY):
            planned_repo.update_planned_session_fields(
                session.id, **outcome.adapted, status=SessionStatus.MODIFIED
            )
        elif outcome.decision == Decision.REST:
            planned_repo.update_planned_session_fields(
                session.id, status=SessionStatus.SKIPPED
            )
        decisions.mark(decision.id, "applied_at")
        logger.info(
            "Plan decision for session %s: %s (%s)",
            session.id,
            outcome.decision.value,
            outcome.reason,
        )
    return decisions.list_for_day(day)


class NothingToRevert(Exception):
    """The decision was a keep, or has been reverted already."""


def revert(decision_id: int) -> PlanDecision:
    """Put the planned session back as it was before the decision.

    Raises ``LookupError`` for an unknown id and ``NothingToRevert`` for a
    keep or a decision already reverted. A copy already scheduled on Garmin
    is forgotten here (its ids cleared) so the athlete can send the original.
    """
    decisions = PlanDecisionRepository()
    decision = decisions.get(decision_id)
    if decision is None:
        raise LookupError(f"decision {decision_id}")
    if decision.reverted_at is not None or decision.decision == Decision.KEEP.value:
        raise NothingToRevert(f"decision {decision_id}")
    original = {k: v for k, v in (decision.original or {}).items() if k in _PLAN_FIELDS}
    GarminRepository().update_planned_session_fields(
        decision.planned_session_id,
        **original,
        garmin_workout_id=None,
        garmin_schedule_id=None,
        garmin_pushed_at=None,
    )
    decisions.mark(decision.id, "reverted_at")
    reverted = decisions.get(decision.id)
    assert reverted is not None
    return reverted
