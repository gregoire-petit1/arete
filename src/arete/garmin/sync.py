"""Garmin Connect activity synchronization (via arete.garmin.client).

Provides automated sync of activities from Garmin Connect to Arete.
Respects rate limits and handles authentication securely.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from garminconnect import GarminConnectTooManyRequestsError

from arete.config import config
from arete.garmin.client import GarminAuthError, GarminClient
from arete.garmin.fit_parser import FITParser
from arete.garmin.models import ActivitySource, ActualSession
from arete.garmin.repository import GarminRepository
from arete.strava.merge import garmin_takeover

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
    activities_merged: int = 0
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
    moving_duration_sec: int | None = None

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
            start_time=datetime.fromisoformat(
                data["startTimeLocal"].replace("Z", "+00:00")
            )
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
            moving_duration_sec=int(data["movingDuration"])
            if data.get("movingDuration")
            else None,
        )

    def to_actual_session(self) -> ActualSession:
        """Convert to ActualSession model."""
        sport = self._map_activity_type()
        return ActualSession(
            date=self.start_time.date(),
            sport=sport,
            session_type=self.activity_type,
            name=self.activity_name or None,
            duration_sec=self.duration_sec,
            moving_time_sec=self.moving_duration_sec or self.duration_sec,
            avg_pace_sec_km=pace_from_speed(self.avg_speed_mps, sport),
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


FOOT_SPORTS_FOR_PACE = {"running", "walking", "hiking"}


def pace_from_speed(avg_speed_mps: float | None, sport: str) -> int | None:
    """sec/km from m/s, only for sports where pace is meaningful."""
    if not avg_speed_mps or avg_speed_mps <= 0 or sport not in FOOT_SPORTS_FOR_PACE:
        return None
    return int(round(1000 / avg_speed_mps))


def laps_to_json(parsed: Any) -> str | None:
    """Serialize FIT laps in the shape the analytics expect (Strava lap fields)."""
    structure = getattr(parsed, "workout_structure", None)
    if not structure or not structure.laps:
        return None
    laps = [
        {
            "lap_index": lap.lap_number,
            "distance": round(lap.distance_m, 1),
            "elapsed_time": int(lap.duration_sec),
            "moving_time": int(lap.duration_sec),
            "average_speed": lap.avg_speed_mps,
            "average_heartrate": lap.avg_hr,
            "max_heartrate": lap.max_hr,
            "average_cadence": lap.avg_cadence,
            "total_elevation_gain": None,  # not exposed per lap by the FIT parser
        }
        for lap in structure.laps
    ]
    return json.dumps(laps)


class GarminSyncClient:
    """Syncs activities from Garmin Connect into the local database."""

    def __init__(
        self,
        client: GarminClient | None = None,
        repository: GarminRepository | None = None,
    ):
        self.client = client or GarminClient()
        self._repository = repository
        self._last_request_time = 0.0

    @property
    def repository(self) -> GarminRepository:
        """Get or create repository."""
        if self._repository is None:
            self._repository = GarminRepository()
        return self._repository

    def is_authenticated(self) -> bool:
        """True when a saved Garmin session can be restored."""
        return self.client.is_authenticated()

    def login(self, email: str | None = None, password: str | None = None) -> str:
        """Authenticate with Garmin Connect. Returns "ok" or "needs_mfa".

        Credentials default to GARMIN_EMAIL / GARMIN_PASSWORD.
        """
        email = email or config.garmin_email
        password = password or config.garmin_password
        if not email or not password:
            raise ValueError(
                "Garmin credentials required. Set GARMIN_EMAIL and GARMIN_PASSWORD "
                "environment variables or pass them directly."
            )
        status = self.client.login(email, password)
        logger.info("Garmin login: %s", status)
        return status

    def logout(self) -> None:
        """Clear saved authentication tokens."""
        self.client.logout()

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
        """Fetch activities between two dates (inclusive), newest first."""
        end_date = end_date or date.today()
        start_date = start_date or end_date - timedelta(days=30)
        self._rate_limit()
        try:
            raw = self.client.activities(start_date, end_date)
        except GarminConnectTooManyRequestsError:
            logger.warning("Rate limited by Garmin. Waiting...")
            time.sleep(RATE_LIMITS["delay_after_429"])
            raise

        activities = []
        for data in raw[: min(limit, 100)]:
            if not isinstance(data, dict):
                continue
            try:
                activities.append(GarminActivity.from_api_response(data))
            except (KeyError, ValueError) as e:
                logger.warning(f"Failed to parse activity: {e}")
        logger.info(f"Fetched {len(activities)} activities from Garmin Connect")
        return activities

    def download_fit_file(
        self, activity_id: int, output_dir: Path | None = None
    ) -> Path | None:
        """Download the original FIT file for an activity (cached on disk)."""
        output_dir = output_dir or Path("data/fit_files")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{activity_id}.fit"
        if output_path.exists():
            logger.debug(f"FIT file already exists: {output_path}")
            return output_path

        self._rate_limit()
        try:
            fit_data = self.client.download_fit(activity_id)
        except GarminConnectTooManyRequestsError:
            time.sleep(RATE_LIMITS["delay_after_429"])
            return None
        except Exception as e:
            logger.error(f"Failed to download FIT file {activity_id}: {e}")
            return None
        if not fit_data:
            return None
        output_path.write_bytes(fit_data)
        logger.info(f"Downloaded FIT file: {output_path}")
        return output_path

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
            max_activities
            if max_activities
            else int(RATE_LIMITS["max_activities_per_sync"])
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

                    # Same workout already imported from Strava? Garmin takes it over.
                    twin = self.repository.find_overlapping_session(
                        session.start_time, session.duration_sec
                    )
                    if (
                        twin is not None
                        and twin.id is not None
                        and twin.source == ActivitySource.STRAVA
                    ):
                        self.repository.update_actual_session_fields(
                            twin.id, **garmin_takeover(session)
                        )
                        result.activities_merged += 1
                    else:
                        self.repository.create_actual_session(session)
                        result.activities_synced += 1
                    result.last_activity_date = activity.start_time.date()

                    logger.info(
                        f"Synced: {activity.activity_name} ({activity.start_time.date()})"
                    )

                except Exception as e:
                    error_msg = f"Failed to sync activity {activity.activity_id}: {e}"
                    logger.error(error_msg)
                    result.errors.append(error_msg)

            result.success = True
            logger.info(
                f"Sync complete: {result.activities_synced} synced, "
                f"{result.activities_merged} merged into Strava rows, "
                f"{result.activities_skipped} skipped, "
                f"{len(result.errors)} errors"
            )

        except (GarminAuthError, Exception) as e:
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
            parsed = parser.parse_file(fit_path, detailed=True)

            # Update with more detailed data from FIT
            if parsed.hr_zones:
                session.hr_zones_json = parsed.hr_zones.to_json()
            session.laps_json = laps_to_json(parsed) or session.laps_json
            if session.avg_pace_sec_km is None:
                session.avg_pace_sec_km = pace_from_speed(
                    parsed.avg_speed_mps, session.sport
                )

            # Update cadence from FIT (may be more accurate)
            if parsed.avg_cadence:
                session.avg_cadence = parsed.avg_cadence
            if parsed.max_cadence:
                session.max_cadence = parsed.max_cadence

            session.source_file = str(fit_path.name)

        except Exception as e:
            logger.warning(f"Could not parse FIT file {fit_path}: {e}")

        return session

    def reprocess_existing(self, fit_dir: Path | None = None) -> dict[str, int]:
        """Fill analytics columns on already-synced Garmin sessions.

        Recomputes pace from speed, re-reads laps / HR zones from the FIT files on
        disk and fetches the activity names from Garmin. Idempotent.
        """
        fit_dir = fit_dir or Path("data/fit_files")
        sessions = [
            s
            for s in self.repository.list_actual_sessions(limit=10000)
            if s.source == ActivitySource.GARMIN_CONNECT and s.id is not None
        ]
        if not sessions:
            return {"sessions": 0, "updated": 0, "named": 0}

        names: dict[str, str] = {}
        try:
            dates = [s.date for s in sessions]
            for data in self.client.activities(min(dates), max(dates)):
                if isinstance(data, dict) and data.get("activityId"):
                    names[str(data["activityId"])] = data.get("activityName") or ""
        except Exception as e:
            logger.warning("Could not fetch activity names: %s", e)

        updated = named = 0
        for session in sessions:
            fields: dict[str, Any] = {}
            if session.avg_pace_sec_km is None:
                pace = pace_from_speed(session.avg_speed_mps, session.sport)
                if pace:
                    fields["avg_pace_sec_km"] = pace
            if session.moving_time_sec is None and session.duration_sec:
                fields["moving_time_sec"] = session.duration_sec
            if not session.name and names.get(session.garmin_activity_id or ""):
                fields["name"] = names[session.garmin_activity_id or ""]
                named += 1
            fit_path = fit_dir / f"{session.garmin_activity_id}.fit"
            if fit_path.exists() and (
                session.laps_json is None or session.hr_zones_json
            ):
                try:
                    parsed = FITParser().parse_file(fit_path, detailed=True)
                    laps = laps_to_json(parsed)
                    if laps:
                        fields["laps_json"] = laps
                    if parsed.hr_zones:
                        fields["hr_zones_json"] = parsed.hr_zones.to_json()
                except Exception as e:
                    logger.warning("FIT reparse failed for %s: %s", fit_path, e)
            if fields:
                assert session.id is not None
                self.repository.update_actual_session_fields(session.id, **fields)
                updated += 1
        logger.info(
            "Reprocessed %d Garmin sessions (%d updated, %d named)",
            len(sessions),
            updated,
            named,
        )
        return {"sessions": len(sessions), "updated": updated, "named": named}

    def get_user_summary(self) -> dict[str, Any]:
        """Garmin profile of the authenticated user."""
        return self.client.profile()
