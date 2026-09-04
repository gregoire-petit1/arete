"""Garmin Connect sync endpoints: login (with MFA), status, activity sync."""

from __future__ import annotations

import contextlib
import logging
from datetime import date

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from arete.garmin.repository import GarminRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/garmin/sync", tags=["garmin-sync"])
_repo = GarminRepository()


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
    activities_merged: int = 0
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


@router.get("/status", response_model=SyncStatusResponse)
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


@router.post("/login", response_model=GarminLoginResponse)
def garmin_login(request: GarminLoginRequest | None = None):
    """Authenticate with Garmin Connect.

    MFA flow: first call with email/password may return needs_mfa=True;
    call again with mfa_code to complete. Credentials default to
    GARMIN_EMAIL / GARMIN_PASSWORD. Tokens are stored on disk for later requests.
    """
    from arete.config import config
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

    email = (request.email if request else None) or config.garmin_email
    password = (request.password if request else None) or config.garmin_password
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


@router.post("/logout")
def garmin_logout():
    """Clear Garmin Connect authentication tokens."""
    from arete.garmin.client import GarminClient

    GarminClient().logout()
    return {"success": True, "message": "Logged out from Garmin Connect"}


@router.post("/activities", response_model=SyncResponse)
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
        activities_merged=result.activities_merged,
        activities_skipped=result.activities_skipped,
        errors=result.errors,
        last_activity_date=str(result.last_activity_date)
        if result.last_activity_date
        else None,
    )


@router.post("/reprocess")
def reprocess_synced_activities():
    """Backfill analytics columns (pace, laps, HR zones, names) on synced sessions.

    Reads the FIT files already on disk and asks Garmin for the activity names.
    Safe to run repeatedly.
    """
    from arete.garmin.sync import GarminSyncClient

    client = GarminSyncClient(repository=_repo)
    if not client.is_authenticated():
        raise HTTPException(
            status_code=401, detail="Not authenticated with Garmin Connect"
        )
    return client.reprocess_existing()
