from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from arete.dataio.db import connect


# ---------- User Settings ----------
def _settings_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    import json as _json

    abbrev_raw = row[10] if len(row) > 10 else "{}"
    try:
        abbreviations = _json.loads(abbrev_raw) if abbrev_raw else {}
    except (ValueError, TypeError):
        abbreviations = {}

    return {
        "user_id": row[0],
        "display_name": row[1],
        "email": row[2],
        "timezone": row[3],
        "weekly_training_goal": row[4],
        "rest_day_preference": row[5].split(",") if row[5] else [],
        "fatigue_threshold": row[6],
        "fitness_goal": row[7],
        "notifications_enabled": row[8],
        "theme": row[9],
        "exercise_abbreviations": abbreviations,
    }


def get_user_settings(user_id: int = 1) -> dict[str, Any] | None:
    """Get user settings by user_id."""
    con = connect(True)
    try:
        row = con.execute(
            """
            SELECT user_id, display_name, email, timezone, weekly_training_goal,
                   rest_day_preference, fatigue_threshold, fitness_goal,
                   notifications_enabled, theme, exercise_abbreviations
            FROM app.user_settings
            WHERE user_id = ?
            """,
            [user_id],
        ).fetchone()
        return _settings_from_row(row) if row else None
    finally:
        con.close()


def upsert_user_settings(
    user_id: int = 1,
    *,
    display_name: str,
    email: str | None,
    timezone: str,
    weekly_training_goal: int,
    rest_day_preference: list[str],
    fatigue_threshold: int,
    fitness_goal: str,
    notifications_enabled: bool,
    theme: str,
    exercise_abbreviations: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Create or update user settings."""
    import json as _json

    con = connect(False)
    rest_days_str = ",".join(rest_day_preference) if rest_day_preference else ""
    abbrev_json = _json.dumps(exercise_abbreviations or {}, ensure_ascii=False)
    try:
        # Try update first
        row = con.execute(
            """
            UPDATE app.user_settings
            SET display_name = ?, email = ?, timezone = ?, weekly_training_goal = ?,
                rest_day_preference = ?, fatigue_threshold = ?, fitness_goal = ?,
                notifications_enabled = ?, theme = ?, exercise_abbreviations = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
            RETURNING user_id, display_name, email, timezone, weekly_training_goal,
                      rest_day_preference, fatigue_threshold, fitness_goal,
                      notifications_enabled, theme, exercise_abbreviations
            """,
            [
                display_name,
                email,
                timezone,
                weekly_training_goal,
                rest_days_str,
                fatigue_threshold,
                fitness_goal,
                notifications_enabled,
                theme,
                abbrev_json,
                user_id,
            ],
        ).fetchone()

        if row:
            return _settings_from_row(row)

        # Insert if not exists
        row = con.execute(
            """
            INSERT INTO app.user_settings (
                user_id, display_name, email, timezone, weekly_training_goal,
                rest_day_preference, fatigue_threshold, fitness_goal,
                notifications_enabled, theme, exercise_abbreviations
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING user_id, display_name, email, timezone, weekly_training_goal,
                      rest_day_preference, fatigue_threshold, fitness_goal,
                      notifications_enabled, theme, exercise_abbreviations
            """,
            [
                user_id,
                display_name,
                email,
                timezone,
                weekly_training_goal,
                rest_days_str,
                fatigue_threshold,
                fitness_goal,
                notifications_enabled,
                theme,
                abbrev_json,
            ],
        ).fetchone()
        if row is None:
            raise RuntimeError("Failed to insert user settings")
        return _settings_from_row(row)
    finally:
        con.close()


# ---------- Actual Sessions (Garmin Activities) ----------
@dataclass
class ActualSessionRow:
    """Simple representation of an actual session from Garmin."""

    id: int
    date: date
    sport: str
    activity_type: str | None
    duration_seconds: int
    source: str
    garmin_activity_id: str | None


def get_actual_sessions(start_date: str, end_date: str) -> list[ActualSessionRow]:
    """Get actual sessions (Garmin activities) within a date range."""
    con = connect(True)
    try:
        rows = con.execute(
            """
            SELECT id, date, sport, session_type, duration_sec, source, garmin_activity_id
            FROM app.actual_sessions
            WHERE date >= ? AND date <= ?
            ORDER BY date DESC
            """,
            [start_date, end_date],
        ).fetchall()
        return [
            ActualSessionRow(
                id=row[0],
                date=row[1],
                sport=row[2],
                activity_type=row[3],
                duration_seconds=row[4],
                source=row[5],
                garmin_activity_id=row[6],
            )
            for row in rows
        ]
    finally:
        con.close()
