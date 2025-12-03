"""Data models for Garmin pipeline.

Pydantic models for planned/actual sessions and matching results.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any


class SessionType(str, Enum):
    """Types of training sessions."""

    RECOVERY = "recovery"
    ENDURANCE = "endurance"
    TEMPO = "tempo"
    INTERVALS = "intervals"
    LONG_RUN = "long_run"
    STRENGTH = "strength"
    CROSS_TRAINING = "cross_training"
    RACE = "race"
    OTHER = "other"


class SessionStatus(str, Enum):
    """Status of a planned session."""

    PENDING = "pending"
    COMPLETED = "completed"
    SKIPPED = "skipped"
    MODIFIED = "modified"


class MatchConfidence(str, Enum):
    """Confidence level of session matching."""

    HIGH = "high"  # Same date, same type, duration within 20%
    MEDIUM = "medium"  # Same date, similar duration
    LOW = "low"  # Same date only
    NONE = "none"  # No match found


class ActivitySource(str, Enum):
    """Source of activity data."""

    FIT_FILE = "fit_file"
    GARMIN_CONNECT = "garmin_connect"
    STRAVA = "strava"
    MANUAL = "manual"


@dataclass
class PlannedSession:
    """A planned training session."""

    id: int | None = None
    user_id: int | None = None
    date: date = field(default_factory=date.today)
    sport: str = "running"
    session_type: SessionType = SessionType.ENDURANCE
    target_duration_min: int | None = None
    target_distance_km: float | None = None
    target_hr_zone: str | None = None
    target_intensity: str | None = None  # 'easy', 'moderate', 'hard'
    description: str | None = None
    source: str = "manual"  # 'manual', 'llm', 'coach'
    status: SessionStatus = SessionStatus.PENDING
    created_at: datetime | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for DB insertion."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "date": self.date,
            "sport": self.sport,
            "session_type": self.session_type.value,
            "target_duration_min": self.target_duration_min,
            "target_distance_km": self.target_distance_km,
            "target_hr_zone": self.target_hr_zone,
            "target_intensity": self.target_intensity,
            "description": self.description,
            "source": self.source,
            "status": self.status.value,
        }


@dataclass
class ActualSession:
    """An actual training session (from Garmin/FIT)."""

    id: int | None = None
    planned_session_id: int | None = None
    user_id: int | None = None
    date: date = field(default_factory=date.today)
    sport: str = "running"
    session_type: str | None = None

    # Core metrics
    duration_sec: int = 0
    distance_m: float | None = None
    calories: int | None = None

    # Heart rate
    avg_hr: int | None = None
    max_hr: int | None = None
    hr_zones_json: str | None = None  # JSON string

    # Pace/Speed
    avg_pace_sec_km: int | None = None
    avg_speed_mps: float | None = None
    max_speed_mps: float | None = None

    # Elevation
    ascent_m: float | None = None
    descent_m: float | None = None

    # GPS
    start_lat: float | None = None
    start_lon: float | None = None

    # Source
    source: ActivitySource = ActivitySource.FIT_FILE
    source_file: str | None = None
    garmin_activity_id: str | None = None

    # Adherence (computed)
    adherence_score: float | None = None
    intensity_deviation: float | None = None

    # Timestamps
    start_time: datetime | None = None
    created_at: datetime | None = None

    @property
    def duration_min(self) -> float:
        """Duration in minutes."""
        return self.duration_sec / 60.0

    @property
    def distance_km(self) -> float | None:
        """Distance in kilometers."""
        return self.distance_m / 1000.0 if self.distance_m else None

    @property
    def avg_pace_min_km(self) -> str | None:
        """Average pace as MM:SS string."""
        if self.avg_pace_sec_km is None:
            return None
        minutes = self.avg_pace_sec_km // 60
        seconds = self.avg_pace_sec_km % 60
        return f"{minutes}:{seconds:02d}"

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for DB insertion."""
        return {
            "id": self.id,
            "planned_session_id": self.planned_session_id,
            "user_id": self.user_id,
            "date": self.date,
            "sport": self.sport,
            "session_type": self.session_type,
            "duration_sec": self.duration_sec,
            "distance_m": self.distance_m,
            "calories": self.calories,
            "avg_hr": self.avg_hr,
            "max_hr": self.max_hr,
            "hr_zones_json": self.hr_zones_json,
            "avg_pace_sec_km": self.avg_pace_sec_km,
            "avg_speed_mps": self.avg_speed_mps,
            "max_speed_mps": self.max_speed_mps,
            "ascent_m": self.ascent_m,
            "descent_m": self.descent_m,
            "start_lat": self.start_lat,
            "start_lon": self.start_lon,
            "source": self.source.value,
            "source_file": self.source_file,
            "garmin_activity_id": self.garmin_activity_id,
            "adherence_score": self.adherence_score,
            "intensity_deviation": self.intensity_deviation,
            "start_time": self.start_time,
        }


@dataclass
class SessionMatch:
    """Result of matching an actual session to a planned session."""

    actual_session: ActualSession
    planned_session: PlannedSession | None
    confidence: MatchConfidence
    adherence_score: float  # 0-100
    duration_deviation_pct: float  # % deviation from planned
    intensity_deviation_pct: float | None  # % deviation from planned HR zone
    notes: list[str] = field(default_factory=list)

    @property
    def is_matched(self) -> bool:
        """Whether a match was found."""
        return self.planned_session is not None and self.confidence != MatchConfidence.NONE

    def summary(self) -> str:
        """Human-readable summary."""
        if not self.is_matched:
            return "Séance non planifiée (activité spontanée)"

        confidence_fr = {
            MatchConfidence.HIGH: "élevée",
            MatchConfidence.MEDIUM: "moyenne",
            MatchConfidence.LOW: "faible",
        }

        return (
            f"Match {confidence_fr.get(self.confidence, 'inconnue')} avec "
            f"'{self.planned_session.description or self.planned_session.session_type.value}' - "
            f"Adhérence: {self.adherence_score:.0f}%"
        )


@dataclass
class SessionAnalysis:
    """LLM-generated analysis for a session."""

    id: int | None = None
    actual_session_id: int = 0
    analysis_type: str = "adherence"  # 'adherence', 'performance', 'summary'
    insights_json: str | None = None  # JSON with structured insights
    recommendations: str | None = None
    generated_by: str = "llm"  # 'llm', 'rules', 'manual'
    created_at: datetime | None = None

    @property
    def insights(self) -> dict[str, Any]:
        """Parse insights JSON."""
        import json

        if self.insights_json:
            return json.loads(self.insights_json)
        return {}

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for DB insertion."""
        return {
            "id": self.id,
            "actual_session_id": self.actual_session_id,
            "analysis_type": self.analysis_type,
            "insights_json": self.insights_json,
            "recommendations": self.recommendations,
            "generated_by": self.generated_by,
        }
