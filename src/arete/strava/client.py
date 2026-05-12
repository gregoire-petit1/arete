"""Strava OAuth2 client and API wrapper."""

from __future__ import annotations

import logging
import time
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"

ACTIVITIES_PER_PAGE = 50


class StravaClient:
    """Handles Strava OAuth2 flow and activity fetching."""

    def __init__(self, client_id: str, client_secret: str, redirect_uri: str) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    def get_authorize_url(self, state: str | None = None) -> str:
        """Build the Strava OAuth authorization URL."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "activity:read_all",
            "approval_prompt": "auto",
        }
        if state:
            params["state"] = state
        return f"{STRAVA_AUTH_URL}?{urlencode(params)}"

    def exchange_code(self, code: str) -> dict:
        """Exchange authorization code for tokens."""
        resp = httpx.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "grant_type": "authorization_code",
            },
        )
        if resp.status_code != 200:
            logger.error("Strava token exchange failed: %s", resp.text)
            raise ValueError(f"Strava token exchange failed: {resp.text}")
        return resp.json()

    def refresh_token(self, refresh_tok: str) -> dict:
        """Refresh an expired access token."""
        resp = httpx.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_tok,
            },
        )
        if resp.status_code != 200:
            logger.error("Strava token refresh failed: %s", resp.text)
            raise ValueError(f"Strava token refresh failed: {resp.text}")
        return resp.json()

    @staticmethod
    def needs_refresh(expires_at: int, margin_sec: int = 300) -> bool:
        """Check if the access token needs refreshing (5-min margin)."""
        return time.time() > expires_at - margin_sec

    def fetch_activities(
        self,
        access_token: str,
        after: int | None = None,
        before: int | None = None,
    ) -> list[dict]:
        """Fetch all activities with pagination."""
        headers = {"Authorization": f"Bearer {access_token}"}
        all_activities: list[dict] = []
        page = 1

        while True:
            params: dict = {"per_page": ACTIVITIES_PER_PAGE, "page": page}
            if after is not None:
                params["after"] = after
            if before is not None:
                params["before"] = before

            resp = httpx.get(
                f"{STRAVA_API_BASE}/athlete/activities",
                headers=headers,
                params=params,
            )
            if resp.status_code != 200:
                logger.error("Strava API error: %s %s", resp.status_code, resp.text)
                break

            batch = resp.json()
            if not batch:
                break

            all_activities.extend(batch)
            if len(batch) < ACTIVITIES_PER_PAGE:
                break
            page += 1

        logger.info("Fetched %d activities from Strava", len(all_activities))
        return all_activities

    def fetch_activity_detail(self, access_token: str, activity_id: int) -> dict | None:
        """Fetch detailed data for a single activity (laps, splits, best_efforts)."""
        resp = httpx.get(
            f"{STRAVA_API_BASE}/activities/{activity_id}",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json()
