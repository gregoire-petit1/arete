"""Repository for strength training data.

CRUD operations for exercises, sets, and strength sessions.
"""

from __future__ import annotations

import json
from datetime import date, datetime

import duckdb

from arete.strength.models import (
    Exercise,
    ExerciseCategory,
    ExerciseSet,
    MuscleGroup,
    SessionExercise,
    StrengthSession,
)


class StrengthRepository:
    """Repository for strength training data in DuckDB."""

    def __init__(self, db_path: str = "data/arete.duckdb"):
        self.db_path = db_path

    def _get_connection(self) -> duckdb.DuckDBPyConnection:
        """Get a database connection."""
        return duckdb.connect(self.db_path)

    # ─────────────────────────────────────────────────────────────────────
    # Exercises (Library)
    # ─────────────────────────────────────────────────────────────────────

    def create_exercise(self, exercise: Exercise) -> int:
        """Create a new exercise in the library."""
        conn = self._get_connection()
        result = conn.execute(
            """
            INSERT INTO app.exercises (
                name, category, primary_muscle, secondary_muscles_json,
                equipment, is_unilateral, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            [
                exercise.name,
                exercise.category.value,
                exercise.primary_muscle.value,
                json.dumps([m.value for m in exercise.secondary_muscles]),
                exercise.equipment,
                exercise.is_unilateral,
                exercise.notes,
                datetime.now(),
            ],
        ).fetchone()
        conn.close()
        if result is None:
            raise RuntimeError("Failed to insert exercise")
        return int(result[0])

    def get_exercise(self, exercise_id: int) -> Exercise | None:
        """Get an exercise by ID."""
        conn = self._get_connection()
        result = conn.execute(
            """
            SELECT id, name, category, primary_muscle, secondary_muscles_json,
                   equipment, is_unilateral, notes
            FROM app.exercises WHERE id = ?
            """,
            [exercise_id],
        ).fetchone()
        conn.close()

        if not result:
            return None

        return self._row_to_exercise(result)

    def get_exercise_by_name(self, name: str) -> Exercise | None:
        """Get an exercise by name (case-insensitive)."""
        conn = self._get_connection()
        result = conn.execute(
            """
            SELECT id, name, category, primary_muscle, secondary_muscles_json,
                   equipment, is_unilateral, notes
            FROM app.exercises WHERE LOWER(name) = LOWER(?)
            """,
            [name],
        ).fetchone()
        conn.close()

        if not result:
            return None

        return self._row_to_exercise(result)

    def list_exercises(
        self,
        category: ExerciseCategory | None = None,
        muscle: MuscleGroup | None = None,
        search: str | None = None,
    ) -> list[Exercise]:
        """List exercises with optional filters."""
        conn = self._get_connection()

        query = """
            SELECT id, name, category, primary_muscle, secondary_muscles_json,
                   equipment, is_unilateral, notes
            FROM app.exercises WHERE 1=1
        """
        params: list = []

        if category:
            query += " AND category = ?"
            params.append(category.value)

        if muscle:
            query += " AND (primary_muscle = ? OR secondary_muscles_json LIKE ?)"
            params.extend([muscle.value, f'%"{muscle.value}"%'])

        if search:
            query += " AND LOWER(name) LIKE LOWER(?)"
            params.append(f"%{search}%")

        query += " ORDER BY name"

        results = conn.execute(query, params).fetchall()
        conn.close()

        return [self._row_to_exercise(row) for row in results]

    def _row_to_exercise(self, row: tuple) -> Exercise:
        """Convert a database row to an Exercise."""
        secondary = json.loads(row[4]) if row[4] else []
        return Exercise(
            id=row[0],
            name=row[1],
            category=ExerciseCategory(row[2]) if row[2] else ExerciseCategory.OTHER,
            primary_muscle=MuscleGroup(row[3]) if row[3] else MuscleGroup.FULL_BODY,
            secondary_muscles=[MuscleGroup(m) for m in secondary],
            equipment=row[5],
            is_unilateral=row[6],
            notes=row[7],
        )

    # ─────────────────────────────────────────────────────────────────────
    # Strength Sessions
    # ─────────────────────────────────────────────────────────────────────

    def create_session(self, session: StrengthSession) -> int:
        """Create a new strength session."""
        conn = self._get_connection()
        result = conn.execute(
            """
            INSERT INTO app.strength_sessions (
                user_id, date, name, program, duration_min,
                overall_rpe, fatigue_level, sleep_quality, notes, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            [
                session.user_id,
                session.date,
                session.name,
                session.program,
                session.duration_min,
                session.overall_rpe,
                session.fatigue_level,
                session.sleep_quality,
                session.notes,
                datetime.now(),
            ],
        ).fetchone()
        if result is None:
            raise RuntimeError("Failed to insert session")
        session_id: int = result[0]

        # Create exercises and sets
        for ex in session.exercises:
            ex.session_id = session_id
            self._create_session_exercise(conn, ex)

        conn.close()
        return session_id

    def _create_session_exercise(
        self, conn: duckdb.DuckDBPyConnection, exercise: SessionExercise
    ) -> int:
        """Create a session exercise with its sets."""
        result = conn.execute(
            """
            INSERT INTO app.session_exercises (
                session_id, exercise_id, exercise_order,
                target_sets, target_reps, target_rpe, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            [
                exercise.session_id,
                exercise.exercise_id,
                exercise.order,
                exercise.target_sets,
                exercise.target_reps,
                exercise.target_rpe,
                exercise.notes,
            ],
        ).fetchone()
        if result is None:
            raise RuntimeError("Failed to insert session exercise")
        session_exercise_id: int = result[0]

        # Create sets
        for s in exercise.sets:
            s.session_exercise_id = session_exercise_id
            self._create_set(conn, s)

        return session_exercise_id

    def _create_set(
        self, conn: duckdb.DuckDBPyConnection, exercise_set: ExerciseSet
    ) -> int:
        """Create an exercise set."""
        result = conn.execute(
            """
            INSERT INTO app.exercise_sets (
                session_exercise_id, set_number, reps, weight_kg,
                rpe, rir, rest_sec, tempo, is_warmup, is_failure, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            [
                exercise_set.session_exercise_id,
                exercise_set.set_number,
                exercise_set.reps,
                exercise_set.weight_kg,
                exercise_set.rpe,
                exercise_set.rir,
                exercise_set.rest_sec,
                exercise_set.tempo,
                exercise_set.is_warmup,
                exercise_set.is_failure,
                exercise_set.notes,
            ],
        ).fetchone()
        if result is None:
            raise RuntimeError("Failed to insert set")
        return int(result[0])

    def get_session(self, session_id: int) -> StrengthSession | None:
        """Get a strength session with all exercises and sets."""
        conn = self._get_connection()

        # Get session
        session_row = conn.execute(
            """
            SELECT id, user_id, date, name, program, duration_min,
                   overall_rpe, fatigue_level, sleep_quality, notes, created_at
            FROM app.strength_sessions WHERE id = ?
            """,
            [session_id],
        ).fetchone()

        if not session_row:
            conn.close()
            return None

        session = StrengthSession(
            id=session_row[0],
            user_id=session_row[1],
            date=session_row[2],
            name=session_row[3],
            program=session_row[4],
            duration_min=session_row[5],
            overall_rpe=session_row[6],
            fatigue_level=session_row[7],
            sleep_quality=session_row[8],
            notes=session_row[9],
            created_at=session_row[10],
        )

        # Get exercises
        exercise_rows = conn.execute(
            """
            SELECT se.id, se.exercise_id, se.exercise_order,
                   se.target_sets, se.target_reps, se.target_rpe, se.notes,
                   e.id, e.name, e.category, e.primary_muscle, e.secondary_muscles_json,
                   e.equipment, e.is_unilateral, e.notes
            FROM app.session_exercises se
            LEFT JOIN app.exercises e ON se.exercise_id = e.id
            WHERE se.session_id = ?
            ORDER BY se.exercise_order
            """,
            [session_id],
        ).fetchall()

        for ex_row in exercise_rows:
            exercise = None
            if ex_row[7]:  # Has exercise data
                secondary = json.loads(ex_row[11]) if ex_row[11] else []
                exercise = Exercise(
                    id=ex_row[7],
                    name=ex_row[8],
                    category=ExerciseCategory(ex_row[9])
                    if ex_row[9]
                    else ExerciseCategory.OTHER,
                    primary_muscle=MuscleGroup(ex_row[10])
                    if ex_row[10]
                    else MuscleGroup.FULL_BODY,
                    secondary_muscles=[MuscleGroup(m) for m in secondary],
                    equipment=ex_row[12],
                    is_unilateral=ex_row[13],
                    notes=ex_row[14],
                )

            session_exercise = SessionExercise(
                id=ex_row[0],
                session_id=session_id,
                exercise_id=ex_row[1],
                exercise=exercise,
                order=ex_row[2],
                target_sets=ex_row[3],
                target_reps=ex_row[4],
                target_rpe=ex_row[5],
                notes=ex_row[6],
            )

            # Get sets for this exercise
            set_rows = conn.execute(
                """
                SELECT id, set_number, reps, weight_kg, rpe, rir,
                       rest_sec, tempo, is_warmup, is_failure, notes
                FROM app.exercise_sets
                WHERE session_exercise_id = ?
                ORDER BY set_number
                """,
                [ex_row[0]],
            ).fetchall()

            for set_row in set_rows:
                exercise_set = ExerciseSet(
                    id=set_row[0],
                    session_exercise_id=ex_row[0],
                    set_number=set_row[1],
                    reps=set_row[2],
                    weight_kg=set_row[3],
                    rpe=set_row[4],
                    rir=set_row[5],
                    rest_sec=set_row[6],
                    tempo=set_row[7],
                    is_warmup=set_row[8],
                    is_failure=set_row[9],
                    notes=set_row[10],
                )
                session_exercise.sets.append(exercise_set)

            session.exercises.append(session_exercise)

        conn.close()
        return session

    def list_sessions(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
        program: str | None = None,
        limit: int = 50,
    ) -> list[StrengthSession]:
        """List strength sessions (without full exercise details)."""
        conn = self._get_connection()

        query = """
            SELECT id, user_id, date, name, program, duration_min,
                   overall_rpe, fatigue_level, sleep_quality, notes, created_at
            FROM app.strength_sessions WHERE 1=1
        """
        params: list = []

        if start_date:
            query += " AND date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND date <= ?"
            params.append(end_date)
        if program:
            query += " AND LOWER(program) = LOWER(?)"
            params.append(program)

        query += " ORDER BY date DESC LIMIT ?"
        params.append(limit)

        results = conn.execute(query, params).fetchall()
        conn.close()

        sessions = []
        for row in results:
            sessions.append(
                StrengthSession(
                    id=row[0],
                    user_id=row[1],
                    date=row[2],
                    name=row[3],
                    program=row[4],
                    duration_min=row[5],
                    overall_rpe=row[6],
                    fatigue_level=row[7],
                    sleep_quality=row[8],
                    notes=row[9],
                    created_at=row[10],
                )
            )
        return sessions

    def delete_session(self, session_id: int) -> bool:
        """Delete a strength session and all related data."""
        conn = self._get_connection()

        # Delete sets first (cascade)
        conn.execute(
            """
            DELETE FROM app.exercise_sets
            WHERE session_exercise_id IN (
                SELECT id FROM app.session_exercises WHERE session_id = ?
            )
            """,
            [session_id],
        )

        # Delete session exercises
        conn.execute(
            "DELETE FROM app.session_exercises WHERE session_id = ?", [session_id]
        )

        # Delete session
        result = conn.execute(
            "DELETE FROM app.strength_sessions WHERE id = ? RETURNING id", [session_id]
        ).fetchone()

        conn.close()
        return result is not None

    # ─────────────────────────────────────────────────────────────────────
    # Statistics
    # ─────────────────────────────────────────────────────────────────────

    def get_exercise_history(
        self,
        exercise_id: int,
        limit: int = 20,
    ) -> list[dict]:
        """Get performance history for an exercise."""
        conn = self._get_connection()

        results = conn.execute(
            """
            SELECT ss.date, se.id,
                   COUNT(es.id) as total_sets,
                   SUM(CASE WHEN NOT es.is_warmup THEN 1 ELSE 0 END) as working_sets,
                   MAX(es.weight_kg) as max_weight,
                   SUM(es.reps * COALESCE(es.weight_kg, 0)) as volume,
                   AVG(CASE WHEN NOT es.is_warmup THEN es.rpe END) as avg_rpe
            FROM app.session_exercises se
            JOIN app.strength_sessions ss ON se.session_id = ss.id
            LEFT JOIN app.exercise_sets es ON es.session_exercise_id = se.id
            WHERE se.exercise_id = ?
            GROUP BY ss.date, se.id
            ORDER BY ss.date DESC
            LIMIT ?
            """,
            [exercise_id, limit],
        ).fetchall()
        conn.close()

        return [
            {
                "date": str(row[0]),
                "session_exercise_id": row[1],
                "total_sets": row[2],
                "working_sets": row[3],
                "max_weight": row[4],
                "volume": round(row[5], 1) if row[5] else 0,
                "avg_rpe": round(row[6], 1) if row[6] else None,
            }
            for row in results
        ]

    def get_volume_by_muscle(
        self,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> dict[str, float]:
        """Get total volume grouped by primary muscle."""
        conn = self._get_connection()

        query = """
            SELECT e.primary_muscle,
                   SUM(es.reps * COALESCE(es.weight_kg, 0)) as volume
            FROM app.exercise_sets es
            JOIN app.session_exercises se ON es.session_exercise_id = se.id
            JOIN app.exercises e ON se.exercise_id = e.id
            JOIN app.strength_sessions ss ON se.session_id = ss.id
            WHERE NOT es.is_warmup
        """
        params: list = []

        if start_date:
            query += " AND ss.date >= ?"
            params.append(start_date)
        if end_date:
            query += " AND ss.date <= ?"
            params.append(end_date)

        query += " GROUP BY e.primary_muscle ORDER BY volume DESC"

        results = conn.execute(query, params).fetchall()
        conn.close()

        return {row[0]: round(row[1], 1) for row in results}

    def get_personal_records(self, exercise_id: int) -> dict:
        """Get personal records for an exercise."""
        conn = self._get_connection()

        # Max weight (1RM or estimated)
        max_weight = conn.execute(
            """
            SELECT MAX(es.weight_kg), es.reps, ss.date
            FROM app.exercise_sets es
            JOIN app.session_exercises se ON es.session_exercise_id = se.id
            JOIN app.strength_sessions ss ON se.session_id = ss.id
            WHERE se.exercise_id = ? AND NOT es.is_warmup
            GROUP BY es.weight_kg, es.reps, ss.date
            ORDER BY es.weight_kg DESC
            LIMIT 1
            """,
            [exercise_id],
        ).fetchone()

        # Max volume in single session
        max_volume = conn.execute(
            """
            SELECT SUM(es.reps * COALESCE(es.weight_kg, 0)) as vol, ss.date
            FROM app.exercise_sets es
            JOIN app.session_exercises se ON es.session_exercise_id = se.id
            JOIN app.strength_sessions ss ON se.session_id = ss.id
            WHERE se.exercise_id = ? AND NOT es.is_warmup
            GROUP BY ss.id, ss.date
            ORDER BY vol DESC
            LIMIT 1
            """,
            [exercise_id],
        ).fetchall()

        conn.close()

        result: dict[str, str | float | int | None] = {
            "max_weight": None,
            "max_weight_reps": None,
            "max_weight_date": None,
            "estimated_1rm": None,
            "max_session_volume": None,
            "max_volume_date": None,
        }

        if max_weight:
            weight, reps, wdate = max_weight
            result["max_weight"] = weight
            result["max_weight_reps"] = reps
            result["max_weight_date"] = str(wdate)
            if weight and reps:
                # Epley formula
                result["estimated_1rm"] = round(weight * (1 + reps / 30), 1)

        if max_volume:
            vol, vdate = max_volume[0]
            result["max_session_volume"] = round(vol, 1) if vol else None
            result["max_volume_date"] = str(vdate) if vdate else None

        return result

    def get_all_prs_summary(self) -> list[dict]:
        """Get summary of personal records for all exercises with data.

        Returns list of dicts with exercise name, category, and estimated 1RM.
        Useful for RAG context enrichment.
        """
        conn = self._get_connection()

        results = conn.execute(
            """
            WITH best_sets AS (
                SELECT
                    se.exercise_id,
                    es.weight_kg,
                    es.reps,
                    ROW_NUMBER() OVER (
                        PARTITION BY se.exercise_id
                        ORDER BY es.weight_kg * (1 + es.reps / 30.0) DESC
                    ) as rn
                FROM app.exercise_sets es
                JOIN app.session_exercises se ON es.session_exercise_id = se.id
                WHERE NOT es.is_warmup AND es.weight_kg > 0
            )
            SELECT
                e.name,
                e.category,
                e.primary_muscle,
                bs.weight_kg,
                bs.reps,
                ROUND(bs.weight_kg * (1 + bs.reps / 30.0), 1) as estimated_1rm
            FROM best_sets bs
            JOIN app.exercises e ON bs.exercise_id = e.id
            WHERE bs.rn = 1
            ORDER BY e.category, estimated_1rm DESC
            """,
        ).fetchall()
        conn.close()

        return [
            {
                "exercise": row[0],
                "category": row[1],
                "muscle": row[2],
                "weight_kg": row[3],
                "reps": row[4],
                "estimated_1rm": row[5],
            }
            for row in results
        ]

    def get_strength_trends(self, days: int = 30) -> dict:
        """Get strength training trends for context.

        Returns volume trends, session count, and muscle distribution.
        """
        conn = self._get_connection()
        cutoff_date = date.today().isoformat()

        # Total volume and sessions
        stats = conn.execute(
            f"""
            SELECT
                COUNT(DISTINCT ss.id) as session_count,
                SUM(es.reps * COALESCE(es.weight_kg, 0)) as total_volume
            FROM app.strength_sessions ss
            JOIN app.session_exercises se ON ss.id = se.session_id
            JOIN app.exercise_sets es ON se.id = es.session_exercise_id
            WHERE ss.date >= date '{cutoff_date}' - INTERVAL '{days} days'
                AND NOT es.is_warmup
            """,
        ).fetchone()

        # Volume per muscle group
        muscle_volume = conn.execute(
            f"""
            SELECT
                e.primary_muscle,
                SUM(es.reps * COALESCE(es.weight_kg, 0)) as volume
            FROM app.strength_sessions ss
            JOIN app.session_exercises se ON ss.id = se.session_id
            JOIN app.exercise_sets es ON se.id = es.session_exercise_id
            JOIN app.exercises e ON se.exercise_id = e.id
            WHERE ss.date >= date '{cutoff_date}' - INTERVAL '{days} days'
                AND NOT es.is_warmup
            GROUP BY e.primary_muscle
            ORDER BY volume DESC
            """,
        ).fetchall()

        conn.close()

        return {
            "period_days": days,
            "session_count": stats[0] if stats else 0,
            "total_volume_kg": round(stats[1], 0) if stats and stats[1] else 0,
            "volume_by_muscle": {row[0]: round(row[1], 0) for row in muscle_volume},
        }
