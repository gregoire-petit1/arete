"""Garmin Connect synchronization using garth library.

Provides automated sync of activities from Garmin Connect to Arete.
Respects rate limits and handles authentication securely.
"""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import garth
from garth.exc import GarthException, GarthHTTPError

from arete.garmin.fit_parser import FITParser
from arete.garmin.models import ActivitySource, ActualSession
from arete.garmin.repository import GarminRepository

logger = logging.getLogger(__name__)


# Rate limiting configuration (conservative to avoid bans)
RATE_LIMITS = {
    "delay_between_requests": 3.0,  # seconds
    "delay_after_error": 60.0,  # seconds
    "delay_after_429": 300.0,  # 5 minutes
    "max_activities_per_sync": 50,  # per session
    "max_retries": 3,
}


@dataclass
class SyncResult:
    """Result of a sync operation."""

    success: bool
    activities_synced: int = 0
    activities_skipped: int = 0
    errors: list[str] = field(default_factory=list)
    last_activity_date: date | None = None


@dataclass
class GarminActivity:
    """Parsed Garmin activity metadata."""

    activity_id: int
    activity_name: str
    activity_type: str
    start_time: datetime
    duration_sec: int
    distance_m: float | None
    avg_hr: int | None
    max_hr: int | None
    calories: int | None
    avg_speed_mps: float | None
    max_speed_mps: float | None
    ascent_m: float | None
    descent_m: float | None
    avg_cadence: int | None
    max_cadence: int | None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> GarminActivity:
        """Create from Garmin Connect API response."""
        # Warn if startTimeLocal is missing (fallback to now is a data quality issue)
        if "startTimeLocal" not in data:
            import logging

            logging.getLogger(__name__).warning(
                "Missing startTimeLocal for activity %s, using current time",
                data.get("activityId", "unknown"),
            )
        return cls(
            activity_id=data["activityId"],
            activity_name=data.get("activityName", ""),
            activity_type=data.get("activityType", {}).get("typeKey", "unknown"),
            start_time=datetime.fromisoformat(data["startTimeLocal"].replace("Z", "+00:00"))
            if "startTimeLocal" in data
            else datetime.now(UTC),
            duration_sec=int(data.get("duration", 0)),
            distance_m=data.get("distance"),
            avg_hr=data.get("averageHR"),
            max_hr=data.get("maxHR"),
            calories=data.get("calories"),
            avg_speed_mps=data.get("averageSpeed"),
            max_speed_mps=data.get("maxSpeed"),
            ascent_m=data.get("elevationGain"),
            descent_m=data.get("elevationLoss"),
            avg_cadence=data.get("averageRunningCadenceInStepsPerMinute")
            or data.get("averageBikingCadenceInRevPerMinute"),
            max_cadence=data.get("maxRunningCadenceInStepsPerMinute")
            or data.get("maxBikingCadenceInRevPerMinute"),
        )

    def to_actual_session(self) -> ActualSession:
        """Convert to ActualSession model."""
        return ActualSession(
            date=self.start_time.date(),
            sport=self._map_activity_type(),
            session_type=self.activity_type,
            duration_sec=self.duration_sec,
            distance_m=self.distance_m,
            calories=self.calories,
            avg_hr=self.avg_hr,
            max_hr=self.max_hr,
            avg_speed_mps=self.avg_speed_mps,
            max_speed_mps=self.max_speed_mps,
            ascent_m=self.ascent_m,
            descent_m=self.descent_m,
            avg_cadence=self.avg_cadence,
            max_cadence=self.max_cadence,
            source=ActivitySource.GARMIN_CONNECT,
            garmin_activity_id=str(self.activity_id),
            start_time=self.start_time,
        )

    def _map_activity_type(self) -> str:
        """Map Garmin activity type to Arete sport type."""
        type_mapping = {
            "running": "running",
            "trail_running": "running",
            "treadmill_running": "running",
            "cycling": "cycling",
            "indoor_cycling": "cycling",
            "mountain_biking": "cycling",
            "swimming": "swimming",
            "open_water_swimming": "swimming",
            "lap_swimming": "swimming",
            "strength_training": "strength",
            "walking": "walking",
            "hiking": "hiking",
        }
        return type_mapping.get(self.activity_type, "other")


class GarminSyncClient:
    """Client for syncing activities from Garmin Connect.

    Uses garth library for authentication and API access.
    Stores OAuth tokens securely for persistent sessions.
    """

    def __init__(
        self,
        token_dir: str | Path | None = None,
        repository: GarminRepository | None = None,
    ):
        """Initialize sync client.

        Args:
            token_dir: Directory to store OAuth tokens.
                       Defaults to ~/.garth/
            repository: GarminRepository for storing synced activities.
        """
        self.token_dir = Path(token_dir) if token_dir else Path.home() / ".garth"
        self.token_dir.mkdir(parents=True, exist_ok=True)
        self._repository = repository
        self._authenticated = False
        self._last_request_time = 0.0

    @property
    def repository(self) -> GarminRepository:
        """Get or create repository."""
        if self._repository is None:
            self._repository = GarminRepository()
        return self._repository

    def is_authenticated(self) -> bool:
        """Check if we have valid authentication."""
        try:
            # Try to resume session from saved tokens
            garth.resume(str(self.token_dir))
            self._authenticated = True
            return True
        except Exception:
            self._authenticated = False
            return False

    def login(self, email: str | None = None, password: str | None = None) -> bool:
        """Authenticate with Garmin Connect.

        Args:
            email: Garmin Connect email. If None, uses GARMIN_EMAIL env var.
            password: Garmin Connect password. If None, uses GARMIN_PASSWORD env var.

        Returns:
            True if login successful.

        Raises:
            GarthException: If authentication fails.
        """
        email = email or os.getenv("GARMIN_EMAIL")
        password = password or os.getenv("GARMIN_PASSWORD")

        if not email or not password:
            raise ValueError(
                "Garmin credentials required. Set GARMIN_EMAIL and GARMIN_PASSWORD "
                "environment variables or pass them directly."
            )

        try:
            garth.login(email, password)
            garth.save(str(self.token_dir))
            self._authenticated = True
            logger.info("Successfully authenticated with Garmin Connect")
            return True
        except GarthHTTPError as e:
            logger.error(f"Garmin authentication failed: {e}")
            raise
        except GarthException as e:
            logger.error(f"Garmin authentication error: {e}")
            raise

    def logout(self) -> None:
        """Clear saved authentication tokens."""
        token_file = self.token_dir / "oauth1_token.json"
        if token_file.exists():
            token_file.unlink()
        token_file = self.token_dir / "oauth2_token.json"
        if token_file.exists():
            token_file.unlink()
        self._authenticated = False
        logger.info("Logged out from Garmin Connect")

    def _rate_limit(self) -> None:
        """Apply rate limiting between requests."""
        elapsed = time.time() - self._last_request_time
        if elapsed < RATE_LIMITS["delay_between_requests"]:
            time.sleep(RATE_LIMITS["delay_between_requests"] - elapsed)
        self._last_request_time = time.time()

    def get_activities(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 50,
    ) -> list[GarminActivity]:
        """Fetch activity list from Garmin Connect.

        Args:
            start_date: Start date for filtering (inclusive).
            end_date: End date for filtering (inclusive).
            limit: Maximum number of activities to fetch.

        Returns:
            List of GarminActivity objects.
        """
        if not self._authenticated and not self.is_authenticated():
            raise RuntimeError("Not authenticated. Call login() first.")

        self._rate_limit()

        try:
            # Garmin API uses start index and limit
            activities_data = garth.connectapi(
                "/activitylist-service/activities/search/activities",
                params={"start": 0, "limit": min(limit, 100)},
            )

            activities = []
            if not isinstance(activities_data, list):
                logger.warning("Unexpected response format from Garmin API")
                return []

            for data in activities_data:
                if not isinstance(data, dict):
                    continue
                try:
                    activity = GarminActivity.from_api_response(data)

                    # Filter by date if specified
                    if start_date and activity.start_time.date() < start_date:
                        continue
                    if end_date and activity.start_time.date() > end_date:
                        continue

                    activities.append(activity)
                except (KeyError, ValueError) as e:
                    logger.warning(f"Failed to parse activity: {e}")
                    continue

            logger.info(f"Fetched {len(activities)} activities from Garmin Connect")
            return activities

        except GarthHTTPError as e:
            if hasattr(e, "response") and e.response.status_code == 429:
                logger.warning("Rate limited by Garmin. Waiting...")
                time.sleep(RATE_LIMITS["delay_after_429"])
            raise

    def download_fit_file(self, activity_id: int, output_dir: Path | None = None) -> Path | None:
        """Download original FIT file for an activity.

        Args:
            activity_id: Garmin activity ID.
            output_dir: Directory to save FIT file. Defaults to data/fit_files/

        Returns:
            Path to downloaded file, or None if download failed.
        """
        if not self._authenticated and not self.is_authenticated():
            raise RuntimeError("Not authenticated. Call login() first.")

        output_dir = output_dir or Path("data/fit_files")
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / f"{activity_id}.fit"

        # Skip if already downloaded
        if output_path.exists():
            logger.debug(f"FIT file already exists: {output_path}")
            return output_path

        self._rate_limit()

        try:
            # Download original FIT file
            fit_data = garth.download(f"/download-service/files/activity/{activity_id}")

            output_path.write_bytes(fit_data)
            logger.info(f"Downloaded FIT file: {output_path}")
            return output_path

        except GarthHTTPError as e:
            logger.error(f"Failed to download FIT file {activity_id}: {e}")
            if hasattr(e, "response") and e.response.status_code == 429:
                time.sleep(RATE_LIMITS["delay_after_429"])
            return None

    def sync_activities(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        download_fit: bool = True,
        max_activities: int | None = None,
    ) -> SyncResult:
        """Sync activities from Garmin Connect to local database.

        Args:
            start_date: Start date for sync. Defaults to last synced date.
            end_date: End date for sync. Defaults to today.
            download_fit: Whether to download FIT files.
            max_activities: Maximum activities to sync. Defaults to rate limit.

        Returns:
            SyncResult with sync statistics.
        """
        result = SyncResult(success=False)
        effective_max: int = (
            max_activities if max_activities else int(RATE_LIMITS["max_activities_per_sync"])
        )

        # Default to syncing from last activity
        if start_date is None:
            last_activity = self._get_last_synced_activity()
            if last_activity:
                start_date = last_activity.date
            else:
                # First sync: get last 30 days
                start_date = date.today() - timedelta(days=30)

        end_date = end_date or date.today()

        logger.info(f"Syncing activities from {start_date} to {end_date}")

        try:
            activities = self.get_activities(
                start_date=start_date, end_date=end_date, limit=effective_max
            )

            for activity in activities:
                try:
                    # Check if already synced
                    if self._is_already_synced(activity.activity_id):
                        result.activities_skipped += 1
                        continue

                    # Convert and save
                    session = activity.to_actual_session()

                    # Optionally download and parse FIT for detailed data
                    if download_fit:
                        fit_path = self.download_fit_file(activity.activity_id)
                        if fit_path:
                            session = self._enrich_from_fit(session, fit_path)

                    # Save to database
                    self.repository.create_actual_session(session)
                    result.activities_synced += 1
                    result.last_activity_date = activity.start_time.date()

                    logger.info(f"Synced: {activity.activity_name} ({activity.start_time.date()})")

                except Exception as e:
                    error_msg = f"Failed to sync activity {activity.activity_id}: {e}"
                    logger.error(error_msg)
                    result.errors.append(error_msg)

            result.success = True
            logger.info(
                f"Sync complete: {result.activities_synced} synced, "
                f"{result.activities_skipped} skipped, "
                f"{len(result.errors)} errors"
            )

        except GarthException as e:
            result.errors.append(f"Garmin API error: {e}")
            logger.error(f"Sync failed: {e}")

        return result

    def _get_last_synced_activity(self) -> ActualSession | None:
        """Get the most recent synced activity."""
        sessions = self.repository.list_actual_sessions(limit=1)
        return sessions[0] if sessions else None

    def _is_already_synced(self, activity_id: int) -> bool:
        """Check if activity is already in database."""
        # Use cached synced IDs for O(1) lookup instead of O(n)
        if not hasattr(self, "_synced_ids_cache"):
            sessions = self.repository.list_actual_sessions(limit=1000)
            self._synced_ids_cache: set[str] = {
                s.garmin_activity_id for s in sessions if s.garmin_activity_id
            }
        return str(activity_id) in self._synced_ids_cache


    def _enrich_from_fit(self, session: ActualSession, fit_path: Path) -> ActualSession:
        """Enrich session with detailed data from FIT file."""
        try:
            parser = FITParser()
            parsed = parser.parse_file(fit_path)

            # Update with more detailed data from FIT
            if parsed.hr_zones:
                session.hr_zones_json = parsed.hr_zones.to_json()

            # Update cadence from FIT (may be more accurate)
            if parsed.avg_cadence:
                session.avg_cadence = parsed.avg_cadence
            if parsed.max_cadence:
                session.max_cadence = parsed.max_cadence

            session.source_file = str(fit_path.name)

        except Exception as e:
            logger.warning(f"Could not parse FIT file {fit_path}: {e}")

        return session

    def get_user_summary(self) -> dict[str, Any]:
        """Get user profile and summary stats."""
        if not self._authenticated and not self.is_authenticated():
            raise RuntimeError("Not authenticated.")

        self._rate_limit()

        try:
            profile = garth.connectapi("/userprofile-service/socialProfile")
            if isinstance(profile, dict):
                return {
                    "display_name": profile.get("displayName"),
                    "profile_image_url": profile.get("profileImageUrlLarge"),
                    "user_id": profile.get("id"),
                }
            return {}
        except GarthHTTPError as e:
            logger.error(f"Failed to get user summary: {e}")
            return {}
