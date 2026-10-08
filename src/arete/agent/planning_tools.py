"""Planning toolkit — create/list/update/delete planned sessions.

Write access to the planning repository, exposed to the agent as a toolkit
(loaded on demand, see ``toolkits.py``). Sessions created by the agent are
stamped ``source="coach"`` so the Planning page can tell them apart.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from langchain_core.tools import BaseTool, tool

from arete.garmin.models import PlannedSession, SessionStatus, SessionType
from arete.garmin.repository import GarminRepository

_MAX_LIST = 50
_HORIZON_DAYS = 120


def _repo() -> GarminRepository:
    return GarminRepository()


def _session_to_dict(s: PlannedSession) -> dict[str, Any]:
    return {
        "id": s.id,
        "date": s.date.isoformat(),
        "sport": s.sport,
        "session_type": s.session_type.value,
        "target_duration_min": s.target_duration_min,
        "target_distance_km": s.target_distance_km,
        "target_hr_zone": s.target_hr_zone,
        "target_intensity": s.target_intensity,
        "description": s.description,
        "source": s.source,
        "status": s.status.value,
    }


@tool
def list_planned(
    start_date: str = "",
    end_date: str = "",
) -> str:
    """List upcoming planned training sessions.

    Args:
        start_date: Optional ISO date (YYYY-MM-DD) filter start, empty = today - 7.
        end_date: Optional ISO date (YYYY-MM-DD) filter end, empty = today + 120.
    """
    start = (
        date.fromisoformat(start_date)
        if start_date
        else date.today() - timedelta(days=7)
    )
    end = (
        date.fromisoformat(end_date)
        if end_date
        else date.today() + timedelta(days=_HORIZON_DAYS)
    )
    sessions = _repo().list_planned_sessions(
        start_date=start, end_date=end, status=None, limit=_MAX_LIST
    )
    return json.dumps(
        {"count": len(sessions), "sessions": [_session_to_dict(s) for s in sessions]},
        ensure_ascii=False,
    )


@tool
def create_planned_session(
    date_str: str,
    session_type: str,
    description: str = "",
    sport: str = "running",
    target_duration_min: int = 0,
    target_distance_km: float = 0.0,
    target_intensity: str = "",
) -> str:
    """Create a planned training session (source stamped 'coach').

    Args:
        date_str: ISO date (YYYY-MM-DD) of the session.
        session_type: One of recovery, endurance, tempo, intervals, long_run,
            strength, hypertrophy, power, deload, cross_training, race, other.
        description: What the session should be (shown on the Planning page).
        sport: running, cycling, swimming, strength… (default running).
        target_duration_min: Target duration in minutes (0 = unset).
        target_distance_km: Target distance in km (0 = unset).
        target_intensity: easy, moderate or hard (empty = unset).
    """
    try:
        st = SessionType(session_type)
    except ValueError:
        return json.dumps(
            {
                "error": f"Unknown session_type '{session_type}'. Valid: {[t.value for t in SessionType]}"
            }
        )
    intensity = target_intensity.strip().lower() or None
    if intensity is not None and intensity not in ("easy", "moderate", "hard"):
        return json.dumps({"error": "target_intensity must be easy|moderate|hard"})

    planned = PlannedSession(
        date=date.fromisoformat(date_str),
        sport=sport,
        session_type=st,
        target_duration_min=target_duration_min or None,
        target_distance_km=target_distance_km or None,
        target_intensity=intensity,
        description=description or None,
        source="coach",
    )
    session_id = _repo().create_planned_session(planned)
    created = _repo().get_planned_session(session_id)
    return json.dumps(
        {
            "created": True,
            "session": _session_to_dict(created) if created else {"id": session_id},
        },
        ensure_ascii=False,
    )


@tool
def update_planned_status(session_id: int, status: str) -> str:
    """Change a planned session's status.

    Args:
        session_id: Id of the planned session.
        status: pending | completed | skipped | modified.
    """
    try:
        st = SessionStatus(status)
    except ValueError:
        return json.dumps(
            {"error": "status must be pending|completed|skipped|modified"}
        )
    if not _repo().update_planned_session_status(session_id, st):
        return json.dumps({"error": f"Planned session {session_id} not found"})
    updated = _repo().get_planned_session(session_id)
    return json.dumps(
        {"updated": True, "session": _session_to_dict(updated) if updated else None},
        ensure_ascii=False,
    )


@tool
def delete_planned_session(session_id: int) -> str:
    """Delete a planned session by id. Prefer update_planned_status to mark it
    skipped — deletion loses the record.

    Args:
        session_id: Id of the planned session.
    """
    if not _repo().delete_planned_session(session_id):
        return json.dumps({"error": f"Planned session {session_id} not found"})
    return json.dumps({"deleted": True, "id": session_id})


PLANNING_TOOLS: list[BaseTool] = [
    list_planned,
    create_planned_session,
    update_planned_status,
    delete_planned_session,
]

#: Rules only. The tools' own schemas and descriptions already reach the model
#: once the toolkit is loaded; listing them again here cost tokens on every
#: later call of the turn and said nothing new.
PLANNING_INSTRUCTIONS = """Toolkit `planning` chargé. Règles:
- Avant de planifier, regarde la charge récente et ce qui est déjà prévu, pour ne pas doubler une séance.
- Une séance qui ne se fera pas passe en `skipped`; ne la supprime que si l'athlète le demande."""
