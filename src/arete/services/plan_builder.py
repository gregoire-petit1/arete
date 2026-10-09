"""A goal's periodised plan: read the athlete, generate, write, take back.

``features.plan_generator`` builds the weeks; this module supplies what it
needs (recent running volume and frequency, rest days, VDOT paces) and
owns the write rules: generated sessions are ``source='plan'`` and linked to
the goal; regenerating replaces only the goal's future pending sessions; a
day that already holds another planned session is left alone.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import date, timedelta
from typing import Any

from arete.dataio.db import connect
from arete.dataio.queries import RUNNING_SPORTS, sql_in
from arete.dataio.settings import get_user_settings
from arete.features.plan_generator import PlanInputs, WeekPlan, generate_plan
from arete.features.running import training_paces
from arete.garmin.models import PlannedSession, SessionStatus, SessionType
from arete.garmin.repository import GarminRepository
from arete.services.goals import Goal, get_goal

_WEEKDAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)
HISTORY_DAYS = 28
DEFAULT_RUNS_PER_WEEK = 4


def _recent_running(con, today: date) -> tuple[float, int]:
    """(running minutes per week, running sessions per week) over 4 weeks."""
    row = con.execute(
        f"""
        SELECT COALESCE(SUM(duration_sec), 0) / 60.0, COUNT(*)
        FROM app.actual_sessions
        WHERE user_id = 1 AND sport IN ({sql_in(RUNNING_SPORTS)})
          AND date >= ? AND date < ?
        """,
        [today - timedelta(days=HISTORY_DAYS), today],
    ).fetchone()
    minutes, count = row or (0.0, 0)
    weeks = HISTORY_DAYS / 7
    return float(minutes) / weeks, round(int(count) / weeks)


def plan_inputs(goal: Goal, today: date | None = None) -> PlanInputs:
    from arete.services.metrics import current_vdot

    today = today or date.today()
    settings = get_user_settings() or {}
    con = connect()
    try:
        minutes, runs = _recent_running(con, today)
        vdot = current_vdot(con)
    finally:
        con.close()
    rest = frozenset(
        _WEEKDAYS.index(d)
        for d in settings.get("rest_day_preference") or []
        if d in _WEEKDAYS
    )
    goal_sessions = int(settings.get("weekly_training_goal") or DEFAULT_RUNS_PER_WEEK)
    runs = max(3, min(runs or DEFAULT_RUNS_PER_WEEK, 6, goal_sessions))
    return PlanInputs(
        start=today + timedelta(days=1),  # today belongs to the daily adaptation
        race_date=goal.race_date,
        distance_km=goal.distance_km,
        weekly_minutes_now=minutes,
        sessions_per_week=runs,
        rest_days=rest,
        paces=training_paces(vdot[0]) if vdot else None,
        race_name=goal.name,
    )


def _weeks_to_dict(weeks: list[WeekPlan]) -> list[dict[str, Any]]:
    return [
        {
            "start": w.start.isoformat(),
            "phase": w.phase,
            "minutes": w.minutes,
            "recovery": w.recovery,
            "sessions": [{**asdict(s), "date": s.date.isoformat()} for s in w.sessions],
        }
        for w in weeks
    ]


def _goal_or_raise(goal_id: int) -> Goal:
    goal = get_goal(goal_id)
    if goal is None:
        raise LookupError(f"goal {goal_id}")
    return goal


def preview(goal_id: int, today: date | None = None) -> dict[str, Any]:
    """The plan as it would be written, without writing it."""
    goal = _goal_or_raise(goal_id)
    inputs = plan_inputs(goal, today)
    weeks = generate_plan(inputs)
    return {
        "goal": goal.to_dict(today),
        "inputs": {
            "weekly_minutes_now": round(inputs.weekly_minutes_now),
            "sessions_per_week": inputs.sessions_per_week,
            "rest_days": sorted(inputs.rest_days),
            "vdot": round(inputs.paces.vdot, 1) if inputs.paces else None,
        },
        "weeks": _weeks_to_dict(weeks),
    }


def _delete_future(con, goal_id: int, start: date) -> int:
    rows = con.execute(
        "DELETE FROM app.planned_sessions WHERE goal_id = ? AND status = 'pending' "
        "AND date >= ? RETURNING id",
        [goal_id, start],
    ).fetchall()
    return len(rows)


def apply(goal_id: int, today: date | None = None) -> dict[str, Any]:
    """Write the goal's plan, replacing its own future sessions still to do."""
    goal = _goal_or_raise(goal_id)
    inputs = plan_inputs(goal, today)
    weeks = generate_plan(inputs)
    con = connect()
    try:
        replaced = _delete_future(con, goal.id, inputs.start)
        taken = {
            r[0]
            for r in con.execute(
                "SELECT DISTINCT date FROM app.planned_sessions "
                "WHERE date BETWEEN ? AND ? AND status <> 'skipped'",
                [inputs.start, goal.race_date],
            ).fetchall()
        }
    finally:
        con.close()
    repo = GarminRepository()
    created, skipped = 0, []
    for week in weeks:
        for draft in week.sessions:
            if draft.date in taken:
                skipped.append(draft.date.isoformat())
                continue
            repo.create_planned_session(
                PlannedSession(
                    date=draft.date,
                    sport="running",
                    session_type=SessionType(draft.session_type),
                    target_duration_min=draft.duration_min,
                    target_distance_km=draft.distance_km,
                    target_hr_zone=draft.hr_zone,
                    target_intensity=draft.intensity,
                    description=draft.description,
                    source="plan",
                    status=SessionStatus.PENDING,
                    goal_id=goal.id,
                )
            )
            created += 1
    return {
        "created": created,
        "replaced": replaced,
        "skipped_days": skipped,  # another planned session was already there
        "weeks": len(weeks),
    }


def remove(goal_id: int, today: date | None = None) -> int:
    """Delete the goal's generated sessions still to come; how many."""
    _goal_or_raise(goal_id)
    con = connect()
    try:
        return _delete_future(con, goal_id, (today or date.today()) + timedelta(days=1))
    finally:
        con.close()
