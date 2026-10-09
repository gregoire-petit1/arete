"""HTTP contracts for analytics; services own queries and calculations."""

from fastapi import APIRouter, Query
from pydantic import BaseModel

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
def list_sessions(limit: int = 20, offset: int = 0):
    return service.list_sessions(limit=limit, offset=offset)
