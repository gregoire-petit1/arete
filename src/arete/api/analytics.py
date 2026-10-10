"""HTTP contracts for analytics; services own queries and calculations."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from arete.services import activity_detail
from arete.services import analytics as service

router = APIRouter(prefix="/analytics", tags=["analytics"])


class SessionUpdate(BaseModel):
    rpe: int | None = None
    notes: str | None = None


@router.get("/overview")
def get_overview(period: str = Query("30d")):
    return service.get_overview(period)


@router.get("/records")
def get_records(sport: str = Query("running")):
    return service.get_records(sport)


@router.patch("/sessions/{session_id}")
def update_session(session_id: int, body: SessionUpdate):
    # Only the keys the client sent: an explicit null clears the value.
    return service.update_session(session_id, body.model_dump(exclude_unset=True))


@router.get("/sessions")
def list_sessions(limit: int = 20, offset: int = 0, for_model: bool = False):
    """Recent sessions; ``for_model`` leaves out Strava's, for an AI client."""
    return service.list_sessions(limit=limit, offset=offset, for_model=for_model)


@router.get("/sessions/{session_id}/detail")
def get_session_detail(session_id: int):
    """One activity for its page: laps, zones, analysis, chart-sized streams."""
    result = activity_detail.get_activity_detail(session_id)
    if result is None:
        raise HTTPException(404, "Séance introuvable.")
    return result


@router.get("/sessions/{session_id}")
def get_session(session_id: int):
    result = service.get_session(session_id)
    if result is None:
        raise HTTPException(404, "Séance introuvable.")
    return result
