"""Planning toolkit — create/list/update/delete planned sessions.

Write access to the planning repository, exposed to the agent as a toolkit
(loaded on demand, see ``toolkits.py``). Sessions created by the agent are
stamped ``source="coach"`` so the Planning page can tell them apart.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from arete.garmin.models import (
    PlannedSession,
    SessionStatus,
    SessionType,
    canonical_sport,
)
from arete.garmin.repository import GarminRepository
from arete.services.prescriptions import (
    Prescription,
    conversation_prescription,
    describe,
)

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
        "revision": s.revision,
        "structured": s.prescription is not None,
        "summary": describe(Prescription.model_validate(s.prescription))
        if s.prescription
        else s.description,
    }


def _parse_iso(value: str, field: str) -> date | str:
    """The date, or a tool error the model can read and correct."""
    try:
        return date.fromisoformat(value.strip())
    except ValueError:
        return json.dumps(
            {"error": f"{field} doit être une date ISO (YYYY-MM-DD), reçu « {value} »"},
            ensure_ascii=False,
        )


def list_planned(
    start_date: str = "",
    end_date: str = "",
) -> str:
    """List upcoming planned training sessions, earliest first.

    Args:
        start_date: Optional ISO date (YYYY-MM-DD) filter start, empty = today - 7.
        end_date: Optional ISO date (YYYY-MM-DD) filter end, empty = today + 120.
    """
    start = (
        _parse_iso(start_date, "start_date")
        if start_date
        else date.today() - timedelta(days=7)
    )
    if isinstance(start, str):
        return start
    end = (
        _parse_iso(end_date, "end_date")
        if end_date
        else date.today() + timedelta(days=_HORIZON_DAYS)
    )
    if isinstance(end, str):
        return end
    # Earliest first, one past the cap: a dense plan keeps this week, and the
    # model learns where to resume instead of silently missing sessions.
    sessions = _repo().list_planned_sessions(
        start_date=start, end_date=end, status=None, limit=_MAX_LIST + 1, ascending=True
    )
    truncated = len(sessions) > _MAX_LIST
    shown = sessions[:_MAX_LIST]
    return json.dumps(
        {
            "count": len(shown),
            "truncated": truncated,
            "next_start_date": sessions[_MAX_LIST].date.isoformat()
            if truncated
            else None,
            "sessions": [_session_to_dict(s) for s in shown],
        },
        ensure_ascii=False,
    )


def create_planned_session(
    date_str: str,
    session_type: str,
    description: str = "",
    sport: str = "running",
    target_duration_min: int = 0,
    target_distance_km: float = 0.0,
    target_intensity: str = "",
    prescription_json: str = "",
    strength_text: str = "",
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

    day = _parse_iso(date_str, "date_str")
    if isinstance(day, str):
        return day
    try:
        prescription = (
            conversation_prescription(
                prescription_json, canonical_sport(sport), day, strength_text
            )
            if prescription_json
            else None
        )
    except ValueError as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    planned = PlannedSession(
        date=day,
        sport=canonical_sport(sport),
        session_type=st,
        target_duration_min=target_duration_min or None,
        target_distance_km=target_distance_km or None,
        target_intensity=intensity,
        description=description or None,
        source="coach",
        prescription=prescription.model_dump(mode="json") if prescription else None,
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
    try:
        changed = _repo().update_planned_session_status(session_id, st)
    except ValueError as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    if not changed:
        return json.dumps({"error": f"Planned session {session_id} not found"})
    updated = _repo().get_planned_session(session_id)
    return json.dumps(
        {"updated": True, "session": _session_to_dict(updated) if updated else None},
        ensure_ascii=False,
    )


_ZONES = ("Z1", "Z2", "Z3", "Z4", "Z5")


def update_planned_session(
    session_id: int,
    date_str: str = "",
    session_type: str = "",
    description: str = "",
    target_duration_min: int = 0,
    target_distance_km: float = 0.0,
    target_hr_zone: str = "",
    target_intensity: str = "",
) -> str:
    """Move or adjust a planned session; empty or 0 leaves a field unchanged.

    Args:
        session_id: Id of the planned session.
        date_str: New ISO date (YYYY-MM-DD), empty = same day.
        session_type: New type (recovery, endurance, tempo, intervals, long_run,
            strength, hypertrophy, power, deload, cross_training, race, other).
        description: New description.
        target_duration_min: New duration in minutes.
        target_distance_km: New distance in km.
        target_hr_zone: New heart-rate zone, Z1 to Z5.
        target_intensity: easy, moderate or hard.
    """
    fields: dict[str, Any] = {}
    if date_str:
        day = _parse_iso(date_str, "date_str")
        if isinstance(day, str):
            return day
        fields["date"] = day
    if session_type:
        try:
            fields["session_type"] = SessionType(session_type)
        except ValueError:
            return json.dumps(
                {
                    "error": f"Unknown session_type '{session_type}'. "
                    f"Valid: {[t.value for t in SessionType]}"
                }
            )
    zone = target_hr_zone.strip().upper()
    if zone:
        if zone not in _ZONES:
            return json.dumps({"error": "target_hr_zone must be Z1|Z2|Z3|Z4|Z5"})
        fields["target_hr_zone"] = zone
    intensity = target_intensity.strip().lower()
    if intensity:
        if intensity not in ("easy", "moderate", "hard"):
            return json.dumps({"error": "target_intensity must be easy|moderate|hard"})
        fields["target_intensity"] = intensity
    if description:
        fields["description"] = description
    if target_duration_min:
        fields["target_duration_min"] = target_duration_min
    if target_distance_km:
        fields["target_distance_km"] = target_distance_km
    if not fields:
        return json.dumps({"error": "Nothing to change: give at least one field"})
    # A copy already on Garmin's calendar no longer matches: mark it unsent.
    try:
        changed = _repo().update_planned_session_fields(
            session_id, **fields, garmin_pushed_at=None
        )
    except ValueError as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)
    if not changed:
        return json.dumps({"error": f"Planned session {session_id} not found"})
    updated = _repo().get_planned_session(session_id)
    return json.dumps(
        {"updated": True, "session": _session_to_dict(updated) if updated else None},
        ensure_ascii=False,
    )


def delete_planned_session(session_id: int) -> str:
    """Delete a planned session by id. Prefer update_planned_status to mark it
    skipped — deletion loses the record.

    Args:
        session_id: Id of the planned session.
    """
    if not _repo().delete_planned_session(session_id):
        return json.dumps({"error": f"Planned session {session_id} not found"})
    return json.dumps({"deleted": True, "id": session_id})
