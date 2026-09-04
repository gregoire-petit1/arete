"""Strava integration API router — OAuth, sync, status, disconnect."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from arete.config import config

if TYPE_CHECKING:
    from arete.strava.client import StravaClient

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/strava", tags=["strava"])


# ---------------------------------------------------------------------------
# DB helper functions
# ---------------------------------------------------------------------------


def _get_strava_tokens(user_id: int = 1) -> dict | None:
    """Get Strava tokens from DB."""
    from arete.dataio.db import connect

    con = connect(True)
    try:
        row = con.execute(
            "SELECT athlete_id, access_token, refresh_token, expires_at, athlete_name "
            "FROM app.strava_tokens WHERE user_id = ?",
            [user_id],
        ).fetchone()
        if not row:
            return None
        return {
            "athlete_id": row[0],
            "access_token": row[1],
            "refresh_token": row[2],
            "expires_at": row[3],
            "athlete_name": row[4],
        }
    finally:
        con.close()


def _save_strava_tokens(tokens: dict, user_id: int = 1) -> None:
    """Upsert Strava tokens in DB."""
    from arete.dataio.db import connect

    con = connect(False)
    try:
        con.execute("DELETE FROM app.strava_tokens WHERE user_id = ?", [user_id])
        con.execute(
            "INSERT INTO app.strava_tokens "
            "(user_id, athlete_id, access_token, refresh_token, expires_at, athlete_name) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                user_id,
                tokens.get("athlete_id"),
                tokens["access_token"],
                tokens["refresh_token"],
                tokens["expires_at"],
                tokens.get("athlete_name"),
            ],
        )
    finally:
        con.close()


def _delete_strava_tokens(user_id: int = 1) -> None:
    """Delete Strava tokens from DB."""
    from arete.dataio.db import connect

    con = connect(False)
    try:
        con.execute("DELETE FROM app.strava_tokens WHERE user_id = ?", [user_id])
    finally:
        con.close()


def _get_strava_client() -> StravaClient:
    """Create StravaClient from configuration."""
    from arete.strava.client import StravaClient

    if not config.strava_client_id or not config.strava_client_secret:
        raise ValueError("STRAVA_CLIENT_ID and STRAVA_CLIENT_SECRET env vars required")
    return StravaClient(
        config.strava_client_id, config.strava_client_secret, config.strava_redirect_uri
    )


def _ensure_fresh_token(tokens: dict) -> str:
    """Refresh token if needed, persist new tokens, return valid access_token."""
    from arete.strava.client import StravaClient

    if not StravaClient.needs_refresh(tokens["expires_at"]):
        return str(tokens["access_token"])
    client = _get_strava_client()
    new_tokens = client.refresh_token(tokens["refresh_token"])
    new_tokens["athlete_id"] = tokens.get("athlete_id")
    new_tokens["athlete_name"] = tokens.get("athlete_name")
    _save_strava_tokens(new_tokens)
    return str(new_tokens["access_token"])


# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class SyncRequest(BaseModel):
    """Request body for /strava/sync."""

    days: int = Field(default=30, ge=1, le=3650)
    full: bool = Field(
        default=False, description="Ignore days: import the whole history"
    )


RATE_LIMIT_BACKOFF_SEC = 300  # Strava: 100 requests / 15 min


def _with_backoff(fn, *args, retries: int = 2):
    """Call fn, sleeping through Strava 429s up to ``retries`` times."""
    for attempt in range(retries + 1):
        try:
            return fn(*args)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code != 429 or attempt == retries:
                raise
            logger.warning(
                "Strava rate limit hit, sleeping %ds", RATE_LIMIT_BACKOFF_SEC
            )
            time.sleep(RATE_LIMIT_BACKOFF_SEC)
    return None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/authorize")
def authorize():
    """Return the Strava OAuth authorization URL."""
    try:
        client = _get_strava_client()
    except ValueError:
        raise HTTPException(
            status_code=500, detail="Strava env vars not configured"
        ) from None
    return {"url": client.get_authorize_url()}


@router.get("/callback")
def callback(code: str, scope: str = ""):
    """Exchange authorization code for tokens and store them."""
    client = _get_strava_client()
    token_data = client.exchange_code(code)

    athlete = token_data.get("athlete", {})
    tokens = {
        "access_token": token_data["access_token"],
        "refresh_token": token_data["refresh_token"],
        "expires_at": token_data["expires_at"],
        "athlete_id": athlete.get("id"),
        "athlete_name": f"{athlete.get('firstname', '')} {athlete.get('lastname', '')}".strip()
        or None,
    }
    _save_strava_tokens(tokens)

    # Redirect back to the frontend Settings page after successful OAuth
    frontend_url = config.frontend_url
    return RedirectResponse(url=f"{frontend_url}/settings?strava=connected")


@router.post("/sync")
def sync(body: SyncRequest | None = None):
    """Sync activities from Strava into local DB."""
    if body is None:
        body = SyncRequest()

    tokens = _get_strava_tokens()
    if not tokens:
        raise HTTPException(status_code=400, detail="Not connected to Strava")

    access_token = _ensure_fresh_token(tokens)

    client = _get_strava_client()
    after = None if body.full else int(time.time()) - body.days * 86400
    activities = client.fetch_activities(access_token, after=after)
    activities.sort(key=lambda a: a.get("start_date", ""))

    from arete.garmin.repository import GarminRepository
    from arete.strava.merge import strava_extras
    from arete.strava.models import strava_activity_to_actual_session

    repo = GarminRepository()
    existing_ids = repo.known_strava_ids()
    imported = 0
    merged = 0
    skipped = 0
    errors: list[str] = []

    for activity in activities:
        act_id = str(activity.get("id", ""))
        if act_id in existing_ids:
            skipped += 1
            continue
        try:
            # Fetch detail for richer data (laps, splits, best_efforts)
            detail = _with_backoff(
                client.fetch_activity_detail, access_token, int(act_id)
            )
            activity_data = detail if detail else activity

            # Fetch HR zone distribution
            hr_zones = _with_backoff(
                client.fetch_activity_zones, access_token, int(act_id)
            )

            session = strava_activity_to_actual_session(
                activity_data, hr_zones=hr_zones
            )
            twin = repo.find_overlapping_session(
                session.start_time, session.duration_sec
            )
            if twin is not None and twin.id is not None:
                # Same workout already synced from Garmin: keep Garmin, add Strava extras
                repo.update_actual_session_fields(
                    twin.id, **strava_extras(twin, session)
                )
                merged += 1
            else:
                repo.create_actual_session(session)
                imported += 1

            # Rate limiting: pause briefly between detail calls
            # Each activity = 2 API calls (detail + zones), so pause at 45 activities
            if (imported + merged) % 45 == 0:
                logger.info("Approaching rate limit, pausing 60s...")
                time.sleep(60)
        except Exception as exc:
            errors.append(f"Activity {act_id}: {exc}")

    return {
        "success": True,
        "imported": imported,
        "merged": merged,
        "skipped": skipped,
        "errors": errors,
    }


@router.get("/status")
def status():
    """Return Strava connection status."""
    tokens = _get_strava_tokens()
    if not tokens:
        return {"connected": False, "athlete_name": None, "athlete_id": None}
    return {
        "connected": True,
        "athlete_name": tokens.get("athlete_name"),
        "athlete_id": tokens.get("athlete_id"),
    }


@router.delete("/disconnect")
def disconnect():
    """Remove Strava tokens from DB."""
    _delete_strava_tokens()
    return {"success": True}
