"""Planning tool schemas; domain validation and persistence live in services."""

from langchain_core.tools import BaseTool, tool

from arete.agent.tools.imports import inspect_import, prepare_import
from arete.services import planning as service


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
    return service.list_planned(start_date=start_date, end_date=end_date)


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
    return service.create_planned_session(
        date_str=date_str,
        session_type=session_type,
        description=description,
        sport=sport,
        target_duration_min=target_duration_min,
        target_distance_km=target_distance_km,
        target_intensity=target_intensity,
    )


@tool
def update_planned_status(session_id: int, status: str) -> str:
    """Change a planned session's status.

    Args:
        session_id: Id of the planned session.
        status: pending | completed | skipped | modified.
    """
    return service.update_planned_status(session_id=session_id, status=status)


@tool
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
    return service.update_planned_session(
        session_id=session_id,
        date_str=date_str,
        session_type=session_type,
        description=description,
        target_duration_min=target_duration_min,
        target_distance_km=target_distance_km,
        target_hr_zone=target_hr_zone,
        target_intensity=target_intensity,
    )


@tool
def delete_planned_session(session_id: int) -> str:
    """Delete a planned session by id. Prefer update_planned_status to mark it
    skipped — deletion loses the record.

    Args:
        session_id: Id of the planned session.
    """
    return service.delete_planned_session(session_id=session_id)


PLANNING_TOOLS: list[BaseTool] = [
    list_planned,
    create_planned_session,
    update_planned_status,
    update_planned_session,
    delete_planned_session,
    prepare_import,
    inspect_import,
]
