"""Garmin pipeline API endpoints.

Endpoints for:
- Managing planned sessions
- Uploading FIT files
- Viewing session matching results
"""

from __future__ import annotations

import contextlib
import logging
from datetime import date
from typing import Literal

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from arete.garmin.fit_parser import FITParser
from arete.garmin.matcher import SessionMatcher
from arete.garmin.models import (
    ActivitySource,
    ActualSession,
    PlannedSession,
    SessionStatus,
    SessionType,
)
from arete.garmin.repository import GarminRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/garmin", tags=["garmin"])

# Shared repository instance
_repo = GarminRepository()


# ─────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────


class PlannedSessionCreate(BaseModel):
    """Create a planned session."""

    date: date
    sport: str = "running"
    session_type: SessionType = SessionType.ENDURANCE
    target_duration_min: int | None = None
    target_distance_km: float | None = None
    target_hr_zone: str | None = Field(None, pattern=r"^Z[1-5]$")
    target_intensity: Literal["easy", "moderate", "hard"] | None = None
    description: str | None = None
    source: Literal["manual", "llm", "coach"] = "manual"


class PlannedSessionResponse(BaseModel):
    """Planned session response."""

    id: int
    date: date
    sport: str
    session_type: str
    target_duration_min: int | None
    target_distance_km: float | None
    target_hr_zone: str | None
    target_intensity: str | None
    description: str | None
    source: str
    status: str


class ActualSessionResponse(BaseModel):
    """Actual session response."""

    id: int
    planned_session_id: int | None
    date: date
    sport: str
    session_type: str | None
    duration_min: str  # Format: "MM:SS"
    distance_km: float | None  # Rounded to 2 decimals
    avg_hr: int | None
    max_hr: int | None
    avg_pace: str | None
    ascent_m: float | None
    source: str
    adherence_score: float | None


class FITUploadResponse(BaseModel):
    """Response after uploading a FIT file."""

    activity_id: int
    activity: dict
    match: dict | None
    message: str


class MatchSummaryResponse(BaseModel):
    """Summary of matching statistics."""

    total_planned: int
    total_actual: int
    total_matched: int
    total_unmatched: int
    adherence_rate: float


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────


def _planned_to_response(session: PlannedSession) -> PlannedSessionResponse:
    """Convert PlannedSession model to response."""
    return PlannedSessionResponse(
        id=session.id or 0,
        date=session.date,
        sport=session.sport,
        session_type=session.session_type.value
        if isinstance(session.session_type, SessionType)
        else session.session_type,
        target_duration_min=session.target_duration_min,
        target_distance_km=session.target_distance_km,
        target_hr_zone=session.target_hr_zone,
        target_intensity=session.target_intensity,
        description=session.description,
        source=session.source,
        status=session.status.value
        if isinstance(session.status, SessionStatus)
        else session.status,
    )


def _actual_to_response(session: ActualSession) -> ActualSessionResponse:
    """Convert ActualSession model to response."""
    return ActualSessionResponse(
        id=session.id or 0,
        planned_session_id=session.planned_session_id,
        date=session.date,
        sport=session.sport,
        session_type=session.session_type,
        duration_min=session.duration_min,
        distance_km=session.distance_km,
        avg_hr=session.avg_hr,
        max_hr=session.max_hr,
        avg_pace=session.avg_pace_min_km,
        ascent_m=session.ascent_m,
        source=session.source.value
        if isinstance(session.source, ActivitySource)
        else session.source,
        adherence_score=session.adherence_score,
    )


# ─────────────────────────────────────────────────────────────────────────
# Planned Sessions Endpoints
# ─────────────────────────────────────────────────────────────────────────


@router.post("/planned", response_model=PlannedSessionResponse, status_code=201)
def create_planned_session(session: PlannedSessionCreate):
    """Create a new planned training session.

    This represents a recommended/scheduled workout from the coach or LLM.
    """
    planned = PlannedSession(
        date=session.date,
        sport=session.sport,
        session_type=session.session_type,
        target_duration_min=session.target_duration_min,
        target_distance_km=session.target_distance_km,
        target_hr_zone=session.target_hr_zone,
        target_intensity=session.target_intensity,
        description=session.description,
        source=session.source,
    )

    session_id = _repo.create_planned_session(planned)
    created = _repo.get_planned_session(session_id)
    if created is None:
        raise HTTPException(status_code=500, detail="Failed to create session")

    logger.info(f"Created planned session {session_id} for {session.date}")
    return _planned_to_response(created)


@router.get("/planned", response_model=list[PlannedSessionResponse])
def list_planned_sessions(
    start_date: date | None = Query(None, description="Filter by start date"),
    end_date: date | None = Query(None, description="Filter by end date"),
    status: SessionStatus | None = Query(None, description="Filter by status"),
    limit: int = Query(50, ge=1, le=200),
):
    """List planned training sessions.

    Returns planned sessions ordered by date descending.
    """
    sessions = _repo.list_planned_sessions(
        start_date=start_date,
        end_date=end_date,
        status=status,
        limit=limit,
    )
    return [_planned_to_response(s) for s in sessions]


@router.delete("/planned/{session_id}")
def delete_planned_session(session_id: int):
    """Delete a planned session."""
    success = _repo.delete_planned_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Session deleted"}


# ─────────────────────────────────────────────────────────────────────────
# FIT Upload & Actual Sessions
# ─────────────────────────────────────────────────────────────────────────


@router.post("/upload-fit", response_model=FITUploadResponse)
async def upload_fit_file(
    file: UploadFile = File(..., description="FIT file from Garmin device"),
    auto_match: bool = Query(
        True, description="Automatically match to planned session"
    ),
):
    """Upload a FIT file and parse the activity.

    The activity is saved to the database and optionally matched
    to a planned session based on date and activity type.
    """
    import io
    from pathlib import Path

    if not file.filename or not file.filename.lower().endswith(".fit"):
        raise HTTPException(status_code=400, detail="File must be a .fit file")

    # Read with size limit (10MB for typical FIT files)
    MAX_FIT_SIZE = 10 * 1024 * 1024  # 10MB
    content = bytearray()
    total_size = 0

    while chunk := await file.read(8192):
        total_size += len(chunk)
        if total_size > MAX_FIT_SIZE:
            raise HTTPException(status_code=413, detail="FIT file too large (max 10MB)")
        content.extend(chunk)

    content_bytes = bytes(content)

    try:
        parser = FITParser()
        parsed = parser.parse_stream(io.BytesIO(content_bytes))
        # Sanitize filename to prevent path traversal
        parsed.source_file = Path(file.filename).name
    except Exception as e:
        logger.error(f"Failed to parse FIT file: {e}")
        raise HTTPException(
            status_code=400, detail=f"Failed to parse FIT file: {e}"
        ) from e

    # Convert parsed activity to ActualSession
    actual = ActualSession(
        date=parsed.start_time.date() if parsed.start_time else date.today(),
        sport=parsed.sport or "running",
        session_type=parsed.sub_sport or parsed.infer_session_type(),
        duration_sec=parsed.duration_sec or parsed.elapsed_time_sec or 0,
        distance_m=parsed.distance_m,
        calories=parsed.calories,
        avg_hr=parsed.avg_hr,
        max_hr=parsed.max_hr,
        hr_zones_json=parsed.hr_zones.to_json() if parsed.hr_zones else None,
        avg_speed_mps=parsed.avg_speed_mps,
        max_speed_mps=parsed.max_speed_mps,
        ascent_m=parsed.ascent_m,
        descent_m=parsed.descent_m,
        start_lat=parsed.start_lat,
        start_lon=parsed.start_lon,
        source=ActivitySource.FIT_FILE,
        source_file=file.filename,
        start_time=parsed.start_time,
    )

    # Calculate avg pace if running
    if actual.distance_m and actual.duration_sec and actual.distance_m > 0:
        pace_sec_per_km = actual.duration_sec / (actual.distance_m / 1000)
        actual.avg_pace_sec_km = int(pace_sec_per_km)

    # Auto-match to planned session
    match_result = None
    if auto_match:
        planned_sessions = _repo.get_potential_matches(actual)
        if planned_sessions:
            matcher = SessionMatcher()
            match = matcher.find_match(actual, planned_sessions)
            if match.is_matched and match.planned_session is not None:
                planned_id = match.planned_session.id
                actual.planned_session_id = planned_id
                actual.adherence_score = match.adherence_score
                match_result = {
                    "planned_session_id": planned_id,
                    "confidence": match.confidence.value,
                    "adherence_score": match.adherence_score,
                    "summary": match.summary(),
                }
                # Update planned session status
                if planned_id is not None:
                    _repo.update_planned_session_status(
                        planned_id, SessionStatus.COMPLETED
                    )

    # Save actual session
    activity_id = _repo.create_actual_session(actual)

    activity_dict = {
        "id": activity_id,
        "date": str(actual.date),
        "sport": actual.sport,
        "duration_min": actual.duration_min,
        "distance_km": actual.distance_km,
        "avg_hr": actual.avg_hr,
        "avg_pace": actual.avg_pace_min_km,
    }

    return FITUploadResponse(
        activity_id=activity_id,
        activity=activity_dict,
        match=match_result,
        message="Activity saved" + (" and matched" if match_result else ""),
    )


@router.get("/actual", response_model=list[ActualSessionResponse])
def list_actual_sessions(
    start_date: date | None = Query(None),
    end_date: date | None = Query(None),
    unmatched_only: bool = Query(False, description="Only show unmatched sessions"),
    limit: int = Query(50, ge=1, le=200),
):
    """List actual training sessions (from FIT files/Garmin Connect)."""
    sessions = _repo.list_actual_sessions(
        start_date=start_date,
        end_date=end_date,
        unmatched_only=unmatched_only,
        limit=limit,
    )
    return [_actual_to_response(s) for s in sessions]


# ─────────────────────────────────────────────────────────────────────────
# Summary & Analytics
# ─────────────────────────────────────────────────────────────────────────


@router.get("/summary", response_model=MatchSummaryResponse)
def get_summary():
    """Get summary statistics of planned vs actual sessions.

    Returns adherence rate and counts.
    """
    summary = _repo.get_matches_summary()
    return MatchSummaryResponse(**summary)


# ─────────────────────────────────────────────────────────────────────────
# Sync Endpoints (Garmin Connect)
# ─────────────────────────────────────────────────────────────────────────


class SyncStatusResponse(BaseModel):
    """Sync status response."""

    garmin_authenticated: bool
    user_email: str | None = None
    last_sync: str | None = None
    activities_synced: int = 0


class SyncRequest(BaseModel):
    """Sync request parameters."""

    start_date: date | None = None
    end_date: date | None = None
    download_fit: bool = True
    max_activities: int = 50


class SyncResponse(BaseModel):
    """Sync result response."""

    success: bool
    activities_synced: int
    activities_skipped: int
    errors: list[str]
    last_activity_date: str | None = None


class GarminLoginRequest(BaseModel):
    """Garmin login credentials (secure, not logged)."""

    email: str | None = Field(None, repr=False)
    password: str | None = Field(None, repr=False)
    mfa_code: str | None = Field(None, repr=False, description="MFA code if required")


class GarminLoginResponse(BaseModel):
    """Garmin login response."""

    success: bool
    needs_mfa: bool = False
    message: str


@router.get("/sync/status", response_model=SyncStatusResponse)
def get_sync_status():
    """Get current sync status and authentication state."""
    from arete.garmin.client import GarminClient

    client = GarminClient()
    authenticated = client.is_authenticated()
    user_email = None
    if authenticated:
        with contextlib.suppress(Exception):
            user_email = client.profile().get("user_email")

    return SyncStatusResponse(
        garmin_authenticated=authenticated,
        user_email=user_email,
        activities_synced=_repo.count_actual_sessions(),
    )


@router.post("/sync/login", response_model=GarminLoginResponse)
def garmin_login(request: GarminLoginRequest | None = None):
    """Authenticate with Garmin Connect.

    MFA flow: first call with email/password may return needs_mfa=True;
    call again with mfa_code to complete. Credentials default to
    GARMIN_EMAIL / GARMIN_PASSWORD. Tokens are stored on disk for later requests.
    """
    import os

    from arete.garmin.client import GarminAuthError, GarminClient

    client = GarminClient()

    if request and request.mfa_code:
        try:
            client.complete_mfa(request.mfa_code)
        except GarminAuthError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except Exception as e:
            logger.error(f"MFA verification failed: {e}")
            raise HTTPException(
                status_code=401, detail=f"MFA verification failed: {e}"
            ) from e
        return GarminLoginResponse(
            success=True, message="Successfully authenticated with Garmin Connect"
        )

    email = (request.email if request else None) or os.getenv("GARMIN_EMAIL")
    password = (request.password if request else None) or os.getenv("GARMIN_PASSWORD")
    if not email or not password:
        raise HTTPException(
            status_code=400,
            detail="Garmin credentials required. Set GARMIN_EMAIL and GARMIN_PASSWORD "
            "environment variables or pass them directly.",
        )

    try:
        status = client.login(email, password)
    except Exception as e:
        logger.error(f"Garmin login failed: {e}")
        raise HTTPException(
            status_code=401, detail=f"Authentication failed: {e}"
        ) from e

    if status == "needs_mfa":
        return GarminLoginResponse(
            success=False,
            needs_mfa=True,
            message="MFA code required. Please provide the code sent to your device.",
        )
    return GarminLoginResponse(
        success=True, message="Successfully authenticated with Garmin Connect"
    )


@router.post("/sync/logout")
def garmin_logout():
    """Clear Garmin Connect authentication tokens."""
    from arete.garmin.client import GarminClient

    GarminClient().logout()
    return {"success": True, "message": "Logged out from Garmin Connect"}


@router.post("/sync/activities", response_model=SyncResponse)
def sync_activities(request: SyncRequest):
    """Sync activities from Garmin Connect.

    Requires prior authentication via /sync/login or GARMIN_EMAIL/GARMIN_PASSWORD env vars.
    """
    from arete.garmin.sync import GarminSyncClient

    client = GarminSyncClient(repository=_repo)

    if not client.is_authenticated():
        try:
            if client.login() == "needs_mfa":
                raise HTTPException(
                    status_code=401,
                    detail="Garmin requires an MFA code: log in from Settings first.",
                )
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(
                status_code=401,
                detail=f"Not authenticated. Login first or set GARMIN_EMAIL/GARMIN_PASSWORD: {e}",
            ) from e

    result = client.sync_activities(
        start_date=request.start_date,
        end_date=request.end_date,
        download_fit=request.download_fit,
        max_activities=request.max_activities,
    )

    return SyncResponse(
        success=result.success,
        activities_synced=result.activities_synced,
        activities_skipped=result.activities_skipped,
        errors=result.errors,
        last_activity_date=str(result.last_activity_date)
        if result.last_activity_date
        else None,
    )
