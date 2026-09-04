"""Runalyze backup integration.

Provides backup/validation of Garmin data via Runalyze export.
Runalyze offers official API access and serves as a fallback data source.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

import httpx

from arete.garmin.models import ActivitySource, ActualSession

logger = logging.getLogger(__name__)


RUNALYZE_API_BASE = "https://runalyze.com/api/v1"


@dataclass
class RunalyzeActivity:
    """Runalyze activity data."""

    id: int
    sport: str
    name: str
    datetime_start: datetime
    duration_sec: int
    distance_m: float | None
    avg_hr: int | None
    max_hr: int | None
    trimp: float | None
    vo2max_estimate: float | None
    elevation_gain: float | None
    elevation_loss: float | None
    avg_pace_sec_km: float | None
    cadence: int | None

    @classmethod
    def from_api_response(cls, data: dict[str, Any]) -> RunalyzeActivity:
        """Parse from Runalyze API response."""
        return cls(
            id=data["id"],
            sport=data.get("sport", {}).get("name", "unknown"),
            name=data.get("title", ""),
            datetime_start=datetime.fromisoformat(data["datetime"])
            if "datetime" in data
            else datetime.now(),  # Fallback for missing datetime - consider raising error
            duration_sec=int(data.get("s", 0)),  # Runalyze uses 's' for seconds
            distance_m=float(data["distance"]) * 1000 if data.get("distance") else None,
            avg_hr=data.get("hrAvg"),
            max_hr=data.get("hrMax"),
            trimp=data.get("trimp"),
            vo2max_estimate=data.get("vo2maxEstimate"),
            elevation_gain=data.get("elevationUp"),
            elevation_loss=data.get("elevationDown"),
            avg_pace_sec_km=data.get("pace"),  # sec/km
            cadence=data.get("cadence"),
        )

    def to_actual_session(self) -> ActualSession:
        """Convert to ActualSession model."""
        return ActualSession(
            date=self.datetime_start.date(),
            sport=self._map_sport(),
            session_type=self.sport,
            duration_sec=self.duration_sec,
            distance_m=self.distance_m,
            avg_hr=self.avg_hr,
            max_hr=self.max_hr,
            ascent_m=self.elevation_gain,
            descent_m=self.elevation_loss,
            avg_pace_sec_km=int(self.avg_pace_sec_km) if self.avg_pace_sec_km else None,
            avg_cadence=self.cadence,
            source=ActivitySource.RUNALYZE,
            start_time=self.datetime_start,
        )

    def _map_sport(self) -> str:
        """Map Runalyze sport to Arete sport."""
        sport_lower = self.sport.lower()
        if "run" in sport_lower or "laufen" in sport_lower:
            return "running"
        if "rad" in sport_lower or "cycl" in sport_lower or "bike" in sport_lower:
            return "cycling"
        if "swim" in sport_lower or "schwimm" in sport_lower:
            return "swimming"
        if "kraft" in sport_lower or "strength" in sport_lower:
            return "strength"
        return "other"


@dataclass
class BackupResult:
    """Result of backup operation."""

    success: bool
    activities_backed_up: int = 0
    export_path: Path | None = None
    errors: list[str] = field(default_factory=list)


class RunalyzeClient:
    """Client for Runalyze API.

    Runalyze provides a legitimate API for accessing training data.
    Can be used as:
    - Primary backup of Garmin data
    - Validation source to compare with Garmin sync
    - Fallback when Garmin sync fails
    """

    def __init__(self, api_token: str | None = None):
        """Initialize Runalyze client.

        Args:
            api_token: Runalyze API token.
                      Get from: https://runalyze.com/settings/account/api
                      If None, uses RUNALYZE_TOKEN env var.
        """
        self.api_token = api_token or os.getenv("RUNALYZE_TOKEN")
        self._client: httpx.Client | None = None

    @property
    def client(self) -> httpx.Client:
        """Get or create HTTP client."""
        if self._client is None:
            if not self.api_token:
                raise ValueError(
                    "Runalyze API token required. Set RUNALYZE_TOKEN env var or pass api_token."
                )
            self._client = httpx.Client(
                base_url=RUNALYZE_API_BASE,
                headers={"token": self.api_token},
                timeout=30.0,
            )
        return self._client

    def is_configured(self) -> bool:
        """Check if API token is configured."""
        return bool(self.api_token)

    def get_activities(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        limit: int = 100,
    ) -> list[RunalyzeActivity]:
        """Fetch activities from Runalyze.

        Args:
            start_date: Filter by start date.
            end_date: Filter by end date.
            limit: Maximum activities to fetch.

        Returns:
            List of RunalyzeActivity objects.
        """
        params: dict[str, Any] = {"limit": limit}

        if start_date:
            params["from"] = start_date.isoformat()
        if end_date:
            params["to"] = end_date.isoformat()

        try:
            response = self.client.get("/activities", params=params)
            response.raise_for_status()
            data = response.json()

            activities = []
            for item in data.get("data", []):
                try:
                    activities.append(RunalyzeActivity.from_api_response(item))
                except (KeyError, ValueError) as e:
                    logger.warning(f"Failed to parse Runalyze activity: {e}")

            logger.info(f"Fetched {len(activities)} activities from Runalyze")
            return activities

        except httpx.HTTPError as e:
            logger.error(f"Runalyze API error: {e}")
            raise

    def export_activities(
        self,
        output_dir: Path | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
        format: str = "json",
    ) -> BackupResult:
        """Export activities to local files.

        Args:
            output_dir: Directory to save exports.
            start_date: Filter by start date.
            end_date: Filter by end date.
            format: Export format ('json' or 'csv').

        Returns:
            BackupResult with export statistics.
        """
        result = BackupResult(success=False)
        output_dir = output_dir or Path("data/backups/runalyze")
        output_dir.mkdir(parents=True, exist_ok=True)

        try:
            activities = self.get_activities(
                start_date=start_date, end_date=end_date, limit=1000
            )

            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            export_file = output_dir / f"runalyze_export_{timestamp}.{format}"

            if format == "json":
                export_data = [
                    {
                        "id": a.id,
                        "sport": a.sport,
                        "name": a.name,
                        "datetime": a.datetime_start.isoformat(),
                        "duration_sec": a.duration_sec,
                        "distance_m": a.distance_m,
                        "avg_hr": a.avg_hr,
                        "max_hr": a.max_hr,
                        "trimp": a.trimp,
                        "vo2max_estimate": a.vo2max_estimate,
                        "elevation_gain": a.elevation_gain,
                        "avg_pace_sec_km": a.avg_pace_sec_km,
                    }
                    for a in activities
                ]
                export_file.write_text(json.dumps(export_data, indent=2))
            else:
                # CSV format
                import csv

                with export_file.open("w", newline="") as f:
                    writer = csv.DictWriter(
                        f,
                        fieldnames=[
                            "id",
                            "sport",
                            "name",
                            "datetime",
                            "duration_sec",
                            "distance_m",
                            "avg_hr",
                            "trimp",
                        ],
                    )
                    writer.writeheader()
                    for a in activities:
                        writer.writerow(
                            {
                                "id": a.id,
                                "sport": a.sport,
                                "name": a.name,
                                "datetime": a.datetime_start.isoformat(),
                                "duration_sec": a.duration_sec,
                                "distance_m": a.distance_m,
                                "avg_hr": a.avg_hr,
                                "trimp": a.trimp,
                            }
                        )

            result.success = True
            result.activities_backed_up = len(activities)
            result.export_path = export_file
            logger.info(f"Exported {len(activities)} activities to {export_file}")

        except Exception as e:
            result.errors.append(str(e))
            logger.error(f"Export failed: {e}")

        return result

    def compare_with_garmin(
        self,
        garmin_activities: list[ActualSession],
        tolerance_minutes: int = 30,
    ) -> dict[str, Any]:
        """Compare Runalyze data with Garmin sync for validation.

        Args:
            garmin_activities: Activities synced from Garmin.
            tolerance_minutes: Time tolerance for matching activities.

        Returns:
            Comparison report with matches, mismatches, and missing.
        """
        runalyze_activities = self.get_activities(limit=500)

        matches = []
        garmin_only = []

        matched_runalyze_indices: set[int] = set()

        for garmin in garmin_activities:
            matched = False
            for i, runalyze in enumerate(runalyze_activities):
                if i in matched_runalyze_indices:
                    continue
                # Match by date and approximate time
                if garmin.date == runalyze.datetime_start.date() and garmin.start_time:
                    time_diff = abs(
                        (garmin.start_time - runalyze.datetime_start).total_seconds()
                    )
                    if time_diff < tolerance_minutes * 60:
                        matches.append(
                            {
                                "garmin_date": str(garmin.date),
                                "runalyze_id": runalyze.id,
                                "garmin_duration": garmin.duration_sec,
                                "runalyze_duration": runalyze.duration_sec,
                                "duration_diff": abs(
                                    (garmin.duration_sec or 0)
                                    - (runalyze.duration_sec or 0)
                                ),
                            }
                        )
                        matched_runalyze_indices.add(i)
                        matched = True
                        break

            if not matched:
                garmin_only.append(
                    {
                        "date": str(garmin.date),
                        "sport": garmin.sport,
                        "duration_sec": garmin.duration_sec,
                    }
                )

        # Compute runalyze_only from unmatched indices
        runalyze_only_filtered = [
            r
            for i, r in enumerate(runalyze_activities)
            if i not in matched_runalyze_indices
        ]

        return {
            "total_garmin": len(garmin_activities),
            "total_runalyze": len(runalyze_activities),
            "matched": len(matches),
            "garmin_only": len(garmin_only),
            "runalyze_only": len(runalyze_only_filtered),
            "match_details": matches[:10],  # First 10 for preview
            "garmin_only_details": garmin_only[:10],
            "runalyze_only_details": [
                {"id": r.id, "date": str(r.datetime_start.date()), "sport": r.sport}
                for r in runalyze_only_filtered[:10]
            ],
        }

    def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            self._client.close()
            self._client = None


def backup_to_runalyze(output_dir: Path | None = None) -> BackupResult:
    """Convenience function to backup activities from Runalyze.

    Uses RUNALYZE_TOKEN environment variable.

    Args:
        output_dir: Directory for backup files.

    Returns:
        BackupResult with statistics.
    """
    client = RunalyzeClient()
    if not client.is_configured():
        return BackupResult(success=False, errors=["RUNALYZE_TOKEN not configured"])

    try:
        return client.export_activities(output_dir=output_dir)
    finally:
        client.close()
