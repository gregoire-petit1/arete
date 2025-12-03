"""Repository for Garmin sessions database operations."""

import json
from datetime import date, datetime, timedelta

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
        return result[0]

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
                adherence_score, intensity_deviation, start_time, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ],
        ).fetchone()
        conn.close()
        return result[0]

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
                   adherence_score, intensity_deviation, start_time, created_at
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
                   adherence_score, intensity_deviation, start_time, created_at
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

    # ─────────────────────────────────────────────────────────────────────
    # Matching Operations
    # ─────────────────────────────────────────────────────────────────────

    def get_unmatched_actual_sessions(self) -> list[ActualSession]:
        """Get all actual sessions without a match."""
        return self.list_actual_sessions(unmatched_only=True, limit=100)

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
        total_planned = conn.execute(
            "SELECT COUNT(*) FROM planned_sessions"
        ).fetchone()[0]
        total_actual = conn.execute("SELECT COUNT(*) FROM actual_sessions").fetchone()[
            0
        ]
        total_matched = conn.execute(
            "SELECT COUNT(*) FROM actual_sessions WHERE planned_session_id IS NOT NULL"
        ).fetchone()[0]

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

    def save_analysis(
        self,
        actual_session_id: int,
        analysis_type: str,
        insights_json: str,
        recommendations: str,
        generated_by: str = "llm",
    ) -> int:
        """Save session analysis to database.

        Args:
            actual_session_id: ID of the analyzed session
            analysis_type: Type of analysis ('adherence', 'summary', etc.)
            insights_json: JSON string with structured insights
            recommendations: Text recommendations
            generated_by: Source of analysis ('llm', 'rules')

        Returns:
            ID of created analysis
        """
        conn = self._get_connection()
        result = conn.execute(
            """
            INSERT INTO session_analysis (
                actual_session_id, analysis_type, insights_json,
                recommendations, generated_by, created_at
            ) VALUES (?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            [
                actual_session_id,
                analysis_type,
                insights_json,
                recommendations,
                generated_by,
                datetime.now(),
            ],
        ).fetchone()
        conn.close()
        return result[0]

    def get_analysis(self, actual_session_id: int) -> dict | None:
        """Get the latest analysis for a session.

        Args:
            actual_session_id: ID of the session

        Returns:
            Analysis dict or None if not found
        """
        conn = self._get_connection()
        result = conn.execute(
            """
            SELECT id, actual_session_id, analysis_type, insights_json,
                   recommendations, generated_by, created_at
            FROM session_analysis
            WHERE actual_session_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            [actual_session_id],
        ).fetchone()
        conn.close()

        if result:
            return {
                "id": result[0],
                "actual_session_id": result[1],
                "analysis_type": result[2],
                "insights": json.loads(result[3]) if result[3] else {},
                "recommendations": result[4],
                "generated_by": result[5],
                "created_at": result[6].isoformat() if result[6] else None,
            }
        return None

    # ─────────────────────────────────────────────────────────────────────
    # RAG Context - Cardio Benchmarks
    # ─────────────────────────────────────────────────────────────────────

    def get_cardio_benchmarks(self, days: int = 90) -> dict:
        """Get cardio benchmarks for RAG context enrichment.

        Computes averages for endurance sessions (Z2/easy) over the period.

        Returns:
            Dict with avg cadence, vertical oscillation, pace benchmarks, etc.
        """
        conn = self._get_connection()
        cutoff = date.today() - timedelta(days=days)

        # Average metrics for endurance/easy sessions
        result = conn.execute(
            """
            SELECT
                AVG(avg_cadence) as avg_cadence,
                AVG(avg_vertical_oscillation) as avg_vo,
                AVG(avg_ground_contact_time) as avg_gct,
                AVG(avg_stride_length) as avg_stride,
                AVG(avg_hr) as avg_hr,
                AVG(avg_pace_sec_km) as avg_pace,
                COUNT(*) as session_count
            FROM actual_sessions
            WHERE date >= ?
                AND sport = 'running'
                AND (session_type IN ('endurance', 'recovery', 'long_run')
                     OR session_type IS NULL)
            """,
            [cutoff],
        ).fetchone()

        # Best pace (fastest avg pace in any session)
        best_pace = conn.execute(
            """
            SELECT avg_pace_sec_km, date
            FROM actual_sessions
            WHERE date >= ? AND sport = 'running'
                AND avg_pace_sec_km > 0
            ORDER BY avg_pace_sec_km ASC
            LIMIT 1
            """,
            [cutoff],
        ).fetchone()

        # Weekly volume trend
        volume = conn.execute(
            """
            SELECT
                SUM(distance_m) / 1000.0 as total_km,
                SUM(duration_sec) / 3600.0 as total_hours
            FROM actual_sessions
            WHERE date >= ? AND sport = 'running'
            """,
            [cutoff],
        ).fetchone()

        conn.close()

        def _pace_str(sec: float | None) -> str | None:
            if not sec:
                return None
            m, s = divmod(int(sec), 60)
            return f"{m}:{s:02d}"

        return {
            "period_days": days,
            "session_count": result[6] if result else 0,
            "avg_cadence_spm": round(result[0]) if result and result[0] else None,
            "avg_vertical_oscillation_mm": round(result[1], 1)
            if result and result[1]
            else None,
            "avg_ground_contact_time_ms": round(result[2])
            if result and result[2]
            else None,
            "avg_stride_length_m": round(result[3], 2)
            if result and result[3]
            else None,
            "avg_easy_hr": round(result[4]) if result and result[4] else None,
            "avg_easy_pace": _pace_str(result[5]) if result else None,
            "best_pace": _pace_str(best_pace[0]) if best_pace else None,
            "best_pace_date": str(best_pace[1]) if best_pace else None,
            "total_distance_km": round(volume[0], 1) if volume and volume[0] else 0,
            "total_hours": round(volume[1], 1) if volume and volume[1] else 0,
        }

    def get_hr_drift_analysis(self, days: int = 30) -> list[dict]:
        """Analyze HR drift patterns for fatigue detection.

        HR drift > 10% during steady efforts can indicate glycogen depletion
        or cardiovascular fatigue.

        Returns:
            List of sessions with significant HR drift
        """
        conn = self._get_connection()
        cutoff = date.today() - timedelta(days=days)

        # Get sessions with HR data for analysis
        # Note: This is a simplified query - real HR drift analysis
        # would require time-series data from hr_zones_json
        sessions = conn.execute(
            """
            SELECT id, date, session_type, duration_sec, avg_hr, max_hr
            FROM actual_sessions
            WHERE date >= ?
                AND sport = 'running'
                AND avg_hr IS NOT NULL
                AND max_hr IS NOT NULL
                AND duration_sec >= 1800  -- At least 30 min
            ORDER BY date DESC
            """,
            [cutoff],
        ).fetchall()

        conn.close()

        drift_data = []
        for row in sessions:
            session_id, sess_date, sess_type, duration, avg_hr, max_hr = row
            # Approximate drift based on avg vs max HR spread
            # Real implementation would analyze time-series data
            hr_spread_pct = ((max_hr - avg_hr) / avg_hr * 100) if avg_hr else 0
            if hr_spread_pct > 15:  # Significant spread suggests drift
                drift_data.append(
                    {
                        "session_id": session_id,
                        "date": str(sess_date),
                        "type": sess_type,
                        "duration_min": duration // 60,
                        "avg_hr": avg_hr,
                        "max_hr": max_hr,
                        "hr_spread_pct": round(hr_spread_pct, 1),
                        "flag": "potential_fatigue"
                        if hr_spread_pct > 20
                        else "monitor",
                    }
                )

        return drift_data
