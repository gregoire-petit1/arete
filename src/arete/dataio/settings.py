"""User settings persistence (app.user_settings)."""

from __future__ import annotations

from typing import Any

from arete.dataio.db import connect
from arete.features.hr_zones import ZoneModel


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
        "weekly_volume_target_kg": row[11] if len(row) > 11 else 20000,
        "lthr": row[12] if len(row) > 12 else None,
        "max_hr": row[13] if len(row) > 13 else None,
        "threshold_pace_sec_km": row[14] if len(row) > 14 else None,
    }


def get_user_settings(user_id: int = 1) -> dict[str, Any] | None:
    """Get user settings by user_id."""
    con = connect(True)
    try:
        row = con.execute(
            """
            SELECT user_id, display_name, email, timezone, weekly_training_goal,
                   rest_day_preference, fatigue_threshold, fitness_goal,
                   notifications_enabled, theme, exercise_abbreviations,
                   weekly_volume_target_kg, lthr, max_hr, threshold_pace_sec_km
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
    weekly_volume_target_kg: int = 20000,
    lthr: int | None = None,
    max_hr: int | None = None,
    threshold_pace_sec_km: int | None = None,
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
                weekly_volume_target_kg = ?, lthr = ?, max_hr = ?,
                threshold_pace_sec_km = ?, updated_at = CURRENT_TIMESTAMP
            WHERE user_id = ?
            RETURNING user_id, display_name, email, timezone, weekly_training_goal,
                      rest_day_preference, fatigue_threshold, fitness_goal,
                      notifications_enabled, theme, exercise_abbreviations,
                      weekly_volume_target_kg, lthr, max_hr, threshold_pace_sec_km
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
                weekly_volume_target_kg,
                lthr,
                max_hr,
                threshold_pace_sec_km,
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
                notifications_enabled, theme, exercise_abbreviations,
                weekly_volume_target_kg, lthr, max_hr, threshold_pace_sec_km
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING user_id, display_name, email, timezone, weekly_training_goal,
                      rest_day_preference, fatigue_threshold, fitness_goal,
                      notifications_enabled, theme, exercise_abbreviations,
                      weekly_volume_target_kg, lthr, max_hr, threshold_pace_sec_km
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
                weekly_volume_target_kg,
                lthr,
                max_hr,
                threshold_pace_sec_km,
            ],
        ).fetchone()
        if row is None:
            raise RuntimeError("Failed to insert user settings")
        return _settings_from_row(row)
    finally:
        con.close()


def athlete_zone_model(user_id: int = 1) -> ZoneModel:
    """Zone model from the stored threshold, or max HR, or the generic default."""
    settings = get_user_settings(user_id) or {}
    return ZoneModel.from_reference(
        lthr=settings.get("lthr"), max_hr=settings.get("max_hr")
    )
