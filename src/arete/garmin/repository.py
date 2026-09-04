"""Repository for Garmin sessions database operations."""

from datetime import date, datetime, timedelta
from typing import Any

import duckdb

from arete.dataio.db import connect
from arete.garmin.models import (
    ActivitySource,
    ActualSession,
    PlannedSession,
    SessionStatus,
    SessionType,
)


class GarminRepository:
    """Repository for planned and actual sessions CRUD operations."""

    def _get_connection(self) -> duckdb.DuckDBPyConnection:
        """Get database connection."""
        conn = connect()
        conn.execute("SET search_path = 'app'")
        return conn

    # ─────────────────────────────────────────────────────────────────────
    # Planned Sessions
    # ─────────────────────────────────────────────────────────────────────

    def create_planned_session(self, session: PlannedSession) -> int:
        """Create a new planned session.

        Args:
            session: PlannedSession to create

        Returns:
            ID of created session
        """
        conn = self._get_connection()

        result = conn.execute(
            """
            INSERT INTO planned_sessions (
                user_id, date, sport, session_type, target_duration_min,
                target_distance_km, target_hr_zone, target_intensity,
                description, source, status, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            [
                session.user_id or 1,
                session.date,
                session.sport,
                session.session_type.value
                if isinstance(session.session_type, SessionType)
                else session.session_type,
                session.target_duration_min,
                session.target_distance_km,
                session.target_hr_zone,
                session.target_intensity,
                session.description,
                session.source,
                session.status.value
                if isinstance(session.status, SessionStatus)
                else session.status,
                datetime.now(),
            ],
        ).fetchone()
        conn.close()
        if result is None:
            raise RuntimeError("Failed to insert planned session")
        return int(result[0])

    def get_planned_session(self, session_id: int) -> PlannedSession | None:
        """Get a planned session by ID."""
        conn = self._get_connection()
        result = conn.execute(
            """
            SELECT id, user_id, date, sport, session_type, target_duration_min,
                   target_distance_km, target_hr_zone, target_intensity,
                   description, source, status, created_at
            FROM planned_sessions WHERE id = ?
            """,
            [session_id],
        ).fetchone()
        conn.close()

        if not result:
            return None

        return PlannedSession(
            id=result[0],
            user_id=result[1],
            date=result[2],
            sport=result[3],
            session_type=SessionType(result[4]) if result[4] else SessionType.ENDURANCE,
            target_duration_min=result[5],
            target_distance_km=result[6],
            target_hr_zone=result[7],
            target_intensity=result[8],
            description=result[9],
            source=result[10],
            status=SessionStatus(result[11]) if result[11] else SessionStatus.PENDING,
            created_at=result[12],
        )

    def list_planned_sessions(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        status: SessionStatus | None = None,
        limit: int = 50,
    ) -> list[PlannedSession]:
        """List planned sessions with optional date filter."""
        conn = self._get_connection()

        query = """
            SELECT id, user_id, date, sport, session_type, target_duration_min,
                   target_distance_km, target_hr_zone, target_intensity,
                   description, source, status, created_at
            FROM planned_sessions WHERE 1=1
        """
        params: list = []

        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        if status:
            query += " AND status = ?"
            params.append(status.value)

        query += " ORDER BY date DESC LIMIT ?"
        params.append(limit)

        results = conn.execute(query, params).fetchall()
        conn.close()

        return [
            PlannedSession(
                id=row[0],
                user_id=row[1],
                date=row[2],
                sport=row[3],
                session_type=SessionType(row[4]) if row[4] else SessionType.ENDURANCE,
                target_duration_min=row[5],
                target_distance_km=row[6],
                target_hr_zone=row[7],
                target_intensity=row[8],
                description=row[9],
                source=row[10],
                status=SessionStatus(row[11]) if row[11] else SessionStatus.PENDING,
                created_at=row[12],
            )
            for row in results
        ]

    def update_planned_session_status(
        self, session_id: int, status: SessionStatus
    ) -> bool:
        """Update the status of a planned session."""
        conn = self._get_connection()
        result = conn.execute(
            "UPDATE planned_sessions SET status = ? WHERE id = ? RETURNING id",
            [status.value, session_id],
        ).fetchone()
        conn.close()
        return result is not None

    def delete_planned_session(self, session_id: int) -> bool:
        """Delete a planned session by ID."""
        conn = self._get_connection()
        result = conn.execute(
            "DELETE FROM planned_sessions WHERE id = ? RETURNING id", [session_id]
        ).fetchone()
        conn.close()
        return result is not None

    # ─────────────────────────────────────────────────────────────────────
    # Actual Sessions
    # ─────────────────────────────────────────────────────────────────────

    def create_actual_session(self, session: ActualSession) -> int:
        """Create a new actual session from parsed FIT file.

        Args:
            session: ActualSession to create

        Returns:
            ID of created session
        """
        conn = self._get_connection()

        result = conn.execute(
            """
            INSERT INTO actual_sessions (
                planned_session_id, user_id, date, sport, session_type,
                duration_sec, distance_m, calories, avg_hr, max_hr,
                hr_zones_json, avg_pace_sec_km, avg_speed_mps, max_speed_mps,
                ascent_m, descent_m, start_lat, start_lon,
                avg_cadence, max_cadence, avg_vertical_oscillation,
                avg_ground_contact_time, avg_stride_length,
                source, source_file, garmin_activity_id,
                adherence_score, intensity_deviation, start_time, created_at,
                name, notes, rpe, workout_type, moving_time_sec,
                suffer_score, laps_json, splits_json, best_efforts_json,
                avg_watts, weighted_avg_watts, device_name
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            [
                session.planned_session_id,
                session.user_id or 1,
                session.date,
                session.sport,
                session.session_type,
                session.duration_sec,
                session.distance_m,
                session.calories,
                session.avg_hr,
                session.max_hr,
                session.hr_zones_json,
                session.avg_pace_sec_km,
                session.avg_speed_mps,
                session.max_speed_mps,
                session.ascent_m,
                session.descent_m,
                session.start_lat,
                session.start_lon,
                session.avg_cadence,
                session.max_cadence,
                session.avg_vertical_oscillation,
                session.avg_ground_contact_time,
                session.avg_stride_length,
                session.source.value
                if isinstance(session.source, ActivitySource)
                else session.source,
                session.source_file,
                session.garmin_activity_id,
                session.adherence_score,
                session.intensity_deviation,
                session.start_time,
                datetime.now(),
                session.name,
                session.notes,
                session.rpe,
                session.workout_type,
                session.moving_time_sec,
                session.suffer_score,
                session.laps_json,
                session.splits_json,
                session.best_efforts_json,
                session.avg_watts,
                session.weighted_avg_watts,
                session.device_name,
            ],
        ).fetchone()
        conn.close()
        if result is None:
            raise RuntimeError("Failed to insert actual session")
        return int(result[0])

    def get_actual_session(self, session_id: int) -> ActualSession | None:
        """Get an actual session by ID."""
        conn = self._get_connection()
        result = conn.execute(
            """
            SELECT id, planned_session_id, user_id, date, sport, session_type,
                   duration_sec, distance_m, calories, avg_hr, max_hr,
                   hr_zones_json, avg_pace_sec_km, avg_speed_mps, max_speed_mps,
                   ascent_m, descent_m, start_lat, start_lon,
                   avg_cadence, max_cadence, avg_vertical_oscillation,
                   avg_ground_contact_time, avg_stride_length,
                   source, source_file, garmin_activity_id,
                   adherence_score, intensity_deviation, start_time, created_at,
                   name, notes, rpe, workout_type, moving_time_sec,
                   suffer_score, laps_json, splits_json, best_efforts_json,
                   avg_watts, weighted_avg_watts, device_name
            FROM actual_sessions WHERE id = ?
            """,
            [session_id],
        ).fetchone()
        conn.close()

        if not result:
            return None

        return self._row_to_actual_session(result)

    def _row_to_actual_session(self, row: tuple) -> ActualSession:
        """Convert a database row to ActualSession."""
        return ActualSession(
            id=row[0],
            planned_session_id=row[1],
            user_id=row[2],
            date=row[3],
            sport=row[4],
            session_type=row[5],
            duration_sec=row[6] or 0,
            distance_m=row[7],
            calories=row[8],
            avg_hr=row[9],
            max_hr=row[10],
            hr_zones_json=row[11],
            avg_pace_sec_km=row[12],
            avg_speed_mps=row[13],
            max_speed_mps=row[14],
            ascent_m=row[15],
            descent_m=row[16],
            start_lat=row[17],
            start_lon=row[18],
            avg_cadence=row[19],
            max_cadence=row[20],
            avg_vertical_oscillation=row[21],
            avg_ground_contact_time=row[22],
            avg_stride_length=row[23],
            source=ActivitySource(row[24]) if row[24] else ActivitySource.FIT_FILE,
            source_file=row[25],
            garmin_activity_id=row[26],
            adherence_score=row[27],
            intensity_deviation=row[28],
            start_time=row[29],
            created_at=row[30],
            name=row[31] if len(row) > 31 else None,
            notes=row[32] if len(row) > 32 else None,
            rpe=row[33] if len(row) > 33 else None,
            workout_type=row[34] if len(row) > 34 else None,
            moving_time_sec=row[35] if len(row) > 35 else None,
            suffer_score=row[36] if len(row) > 36 else None,
            laps_json=row[37] if len(row) > 37 else None,
            splits_json=row[38] if len(row) > 38 else None,
            best_efforts_json=row[39] if len(row) > 39 else None,
            avg_watts=row[40] if len(row) > 40 else None,
            weighted_avg_watts=row[41] if len(row) > 41 else None,
            device_name=row[42] if len(row) > 42 else None,
        )

    def list_actual_sessions(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        unmatched_only: bool = False,
        limit: int = 50,
    ) -> list[ActualSession]:
        """List actual sessions with optional filters."""
        conn = self._get_connection()

        query = """
            SELECT id, planned_session_id, user_id, date, sport, session_type,
                   duration_sec, distance_m, calories, avg_hr, max_hr,
                   hr_zones_json, avg_pace_sec_km, avg_speed_mps, max_speed_mps,
                   ascent_m, descent_m, start_lat, start_lon,
                   avg_cadence, max_cadence, avg_vertical_oscillation,
                   avg_ground_contact_time, avg_stride_length,
                   source, source_file, garmin_activity_id,
                   adherence_score, intensity_deviation, start_time, created_at,
                   name, notes, rpe, workout_type, moving_time_sec,
                   suffer_score, laps_json, splits_json, best_efforts_json,
                   avg_watts, weighted_avg_watts, device_name
            FROM actual_sessions WHERE 1=1
        """
        params: list = []

        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        if unmatched_only:
            query += " AND planned_session_id IS NULL"

        query += " ORDER BY date DESC LIMIT ?"
        params.append(limit)

        results = conn.execute(query, params).fetchall()
        conn.close()

        return [self._row_to_actual_session(row) for row in results]

    ENRICHMENT_COLUMNS = frozenset(
        {
            # analytics
            "name",
            "notes",
            "avg_pace_sec_km",
            "moving_time_sec",
            "laps_json",
            "splits_json",
            "best_efforts_json",
            "hr_zones_json",
            "avg_cadence",
            "max_cadence",
            "descent_m",
            "calories",
            # Strava extras
            "suffer_score",
            "workout_type",
            "device_name",
            "avg_watts",
            "weighted_avg_watts",
            "strava_activity_id",
            # provenance (when a Strava row is taken over by Garmin)
            "source",
            "source_file",
            "session_type",
            "garmin_activity_id",
        }
    )

    def find_overlapping_session(
        self,
        start_time: datetime | None,
        duration_sec: int,
        tolerance_sec: int = 120,
    ) -> ActualSession | None:
        """Session that is the same workout: starts within ``tolerance_sec``.

        Without a start time, falls back to same day and duration within
        max(tolerance, 5 %). Used to merge Garmin and Strava copies.
        """
        if start_time is None:
            return None
        conn = self._get_connection()
        try:
            row = conn.execute(
                """
                SELECT id FROM actual_sessions
                WHERE date = ?
                  AND start_time IS NOT NULL
                  AND abs(epoch(start_time) - epoch(CAST(? AS TIMESTAMP))) <= ?
                ORDER BY abs(epoch(start_time) - epoch(CAST(? AS TIMESTAMP)))
                LIMIT 1
                """,
                [start_time.date(), start_time, tolerance_sec, start_time],
            ).fetchone()
            if row is None:
                tol = max(tolerance_sec, int(duration_sec * 0.05))
                row = conn.execute(
                    """
                    SELECT id FROM actual_sessions
                    WHERE date = ? AND start_time IS NULL
                      AND abs(duration_sec - ?) <= ?
                    LIMIT 1
                    """,
                    [start_time.date(), duration_sec, tol],
                ).fetchone()
        finally:
            conn.close()
        return self.get_actual_session(int(row[0])) if row else None

    def known_strava_ids(self) -> set[str]:
        """Strava activity IDs already imported (own rows or merged into Garmin rows)."""
        conn = self._get_connection()
        try:
            rows = conn.execute(
                """
                SELECT garmin_activity_id FROM actual_sessions WHERE source = 'strava'
                UNION
                SELECT strava_activity_id FROM actual_sessions WHERE strava_activity_id IS NOT NULL
                """
            ).fetchall()
        finally:
            conn.close()
        return {str(r[0]) for r in rows if r[0] is not None}

    def update_actual_session_fields(self, session_id: int, **fields: Any) -> None:
        """Update enrichment columns of an actual session (whitelisted)."""
        unknown = set(fields) - self.ENRICHMENT_COLUMNS
        if unknown:
            raise ValueError(f"Not updatable: {sorted(unknown)}")
        if not fields:
            return
        assignments = ", ".join(f"{col} = ?" for col in fields)
        conn = self._get_connection()
        try:
            conn.execute(
                f"UPDATE actual_sessions SET {assignments} WHERE id = ?",
                [*fields.values(), session_id],
            )
        finally:
            conn.close()

    def update_actual_session_match(
        self,
        actual_id: int,
        planned_id: int | None,
        adherence_score: float | None = None,
    ) -> bool:
        """Update the planned_session_id for an actual session."""
        conn = self._get_connection()
        result = conn.execute(
            """
            UPDATE actual_sessions
            SET planned_session_id = ?, adherence_score = ?
            WHERE id = ?
            RETURNING id
            """,
            [planned_id, adherence_score, actual_id],
        ).fetchone()
        conn.close()
        return result is not None

    def delete_actual_session(self, session_id: int) -> bool:
        """Delete an actual session by ID."""
        conn = self._get_connection()
        result = conn.execute(
            "DELETE FROM actual_sessions WHERE id = ? RETURNING id", [session_id]
        ).fetchone()
        conn.close()
        return result is not None

    def count_actual_sessions(self) -> int:
        """Return total count of actual sessions (efficient query)."""
        conn = self._get_connection()
        result = conn.execute("SELECT COUNT(*) FROM actual_sessions").fetchone()
        conn.close()
        return int(result[0]) if result else 0

    # ─────────────────────────────────────────────────────────────────────
    # Matching Operations
    # ─────────────────────────────────────────────────────────────────────

    def get_potential_matches(
        self, actual_session: ActualSession, date_tolerance_days: int = 1
    ) -> list[PlannedSession]:
        """Get planned sessions that could match an actual session.

        Args:
            actual_session: The actual session to match
            date_tolerance_days: Number of days tolerance for matching

        Returns:
            List of potential matching planned sessions
        """
        start = actual_session.date - timedelta(days=date_tolerance_days)
        end = actual_session.date + timedelta(days=date_tolerance_days)
        return self.list_planned_sessions(start_date=start, end_date=end)

    def get_matches_summary(self) -> dict:
        """Get summary statistics of matches."""
        conn = self._get_connection()

        # Count totals
        planned_row = conn.execute("SELECT COUNT(*) FROM planned_sessions").fetchone()
        total_planned = int(planned_row[0]) if planned_row else 0
        actual_row = conn.execute("SELECT COUNT(*) FROM actual_sessions").fetchone()
        total_actual = int(actual_row[0]) if actual_row else 0
        matched_row = conn.execute(
            "SELECT COUNT(*) FROM actual_sessions WHERE planned_session_id IS NOT NULL"
        ).fetchone()
        total_matched = int(matched_row[0]) if matched_row else 0

        conn.close()

        return {
            "total_planned": total_planned,
            "total_actual": total_actual,
            "total_matched": total_matched,
            "total_unmatched": total_actual - total_matched,
            "adherence_rate": (
                round(total_matched / total_planned * 100, 1)
                if total_planned > 0
                else 0
            ),
        }

    # ==================== Session Analysis ====================

    # ─────────────────────────────────────────────────────────────────────
    # RAG Context - Cardio Benchmarks
    # ─────────────────────────────────────────────────────────────────────
