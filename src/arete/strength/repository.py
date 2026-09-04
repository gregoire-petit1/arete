"""Repository for strength training data.

CRUD operations for exercises, sets, and strength sessions.
"""

from __future__ import annotations

import json
import logging
from datetime import date, datetime

import duckdb

from arete.data.exercises_catalog import EXERCISES_CATALOG
from arete.dataio.db import get_db_path
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

    def __init__(self, db_path: str | None = None):
        self.db_path = db_path or str(get_db_path())

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

    def remove_duplicate_exercises(self) -> int:
        """Remove duplicate exercises, keeping the one with lowest ID.

        Returns the number of removed duplicates.
        """
        conn = self._get_connection()

        # Count duplicates first
        dup_row = conn.execute(
            """
            SELECT COUNT(*) FROM app.exercises
            WHERE id NOT IN (
                SELECT MIN(id) FROM app.exercises GROUP BY LOWER(name)
            )
            """
        ).fetchone()
        dup_count = int(dup_row[0]) if dup_row else 0

        # Delete duplicates
        conn.execute(
            """
            DELETE FROM app.exercises
            WHERE id NOT IN (
                SELECT MIN(id) FROM app.exercises GROUP BY LOWER(name)
            )
            """
        )

        conn.close()

        return dup_count

    def get_exercise_by_catalog_id(self, catalog_id: str) -> Exercise | None:
        """Get an exercise by its catalog ID (from exercises_catalog.py).

        First checks notes field for 'Auto-created from catalog: <catalog_id>',
        then tries name matching.
        """
        conn = self._get_connection()

        # First: check notes for exact catalog_id match (most reliable)
        result = conn.execute(
            """
            SELECT id, name, category, primary_muscle, secondary_muscles_json,
                   equipment, is_unilateral, notes
            FROM app.exercises
            WHERE notes LIKE ?
            LIMIT 1
            """,
            [f"%Auto-created from catalog: {catalog_id}%"],
        ).fetchone()

        if not result:
            # Convert catalog_id to expected name format
            name_from_id = catalog_id.replace("_", " ").title()
            # Try exact name match
            result = conn.execute(
                """
                SELECT id, name, category, primary_muscle, secondary_muscles_json,
                       equipment, is_unilateral, notes
                FROM app.exercises
                WHERE LOWER(name) = LOWER(?) OR LOWER(name) = LOWER(?)
                LIMIT 1
                """,
                [name_from_id, catalog_id],
            ).fetchone()

        conn.close()

        if not result:
            return None

        return self._row_to_exercise(result)

    def get_or_create_exercise_from_catalog(self, catalog_id: str) -> Exercise | None:
        """Get or create an exercise from the catalog by its ID.

        If the exercise doesn't exist in DB but is in the catalog,
        create it automatically.
        """
        logger = logging.getLogger(__name__)

        # First try to find in DB
        exercise = self.get_exercise_by_catalog_id(catalog_id)
        if exercise:
            return exercise

        # Not in DB - look up in catalog and create
        catalog_entry = None
        for ex in EXERCISES_CATALOG:
            if ex["id"] == catalog_id:
                catalog_entry = ex
                break

        if not catalog_entry:
            logger.warning(f"Exercise {catalog_id} not found in catalog")
            return None

        # Map catalog category to ExerciseCategory based on movement pattern
        movement = catalog_entry.get("movement_pattern", "")
        category_map = {
            "horizontal_push": ExerciseCategory.PUSH_HORIZONTAL,
            "vertical_push": ExerciseCategory.PUSH_VERTICAL,
            "horizontal_pull": ExerciseCategory.PULL_HORIZONTAL,
            "vertical_pull": ExerciseCategory.PULL_VERTICAL,
            "hip_hinge": ExerciseCategory.HINGE,
            "squat": ExerciseCategory.SQUAT,
            "isolation": ExerciseCategory.ISOLATION,
            "core": ExerciseCategory.CORE,
            "carry": ExerciseCategory.CARRY,
        }
        category = category_map.get(movement, ExerciseCategory.OTHER)

        # Map primary muscle (take first one)
        muscle_map = {
            "chest": MuscleGroup.CHEST,
            "front_delts": MuscleGroup.SHOULDERS,
            "side_delts": MuscleGroup.SHOULDERS,
            "rear_delts": MuscleGroup.SHOULDERS,
            "triceps": MuscleGroup.TRICEPS,
            "biceps": MuscleGroup.BICEPS,
            "lats": MuscleGroup.BACK,
            "traps": MuscleGroup.BACK,
            "rhomboids": MuscleGroup.BACK,
            "lower_back": MuscleGroup.LOWER_BACK,
            "quads": MuscleGroup.QUADS,
            "hamstrings": MuscleGroup.HAMSTRINGS,
            "glutes": MuscleGroup.GLUTES,
            "calves": MuscleGroup.CALVES,
            "abs": MuscleGroup.ABS,
            "obliques": MuscleGroup.OBLIQUES,
            "forearms": MuscleGroup.FOREARMS,
            "adductors": MuscleGroup.ADDUCTORS,
        }

        primary_muscles = catalog_entry.get("primary_muscles", [])
        primary_muscle = (
            muscle_map.get(primary_muscles[0], MuscleGroup.FULL_BODY)
            if primary_muscles
            else MuscleGroup.FULL_BODY
        )

        secondary_muscles = [
            muscle_map.get(m, MuscleGroup.FULL_BODY)
            for m in catalog_entry.get("secondary_muscles", [])
            if m in muscle_map
        ]

        equipment = catalog_entry.get("equipment", [])
        equipment_str = equipment[0] if equipment else None

        # Create the exercise
        new_exercise = Exercise(
            name=catalog_entry["name"],
            category=category,
            primary_muscle=primary_muscle,
            secondary_muscles=secondary_muscles,
            equipment=equipment_str,
            is_unilateral=False,
            notes=f"Auto-created from catalog: {catalog_id}",
        )

        try:
            exercise_id = self.create_exercise(new_exercise)
            new_exercise.id = exercise_id
            logger.info(
                f"Created exercise {catalog_entry['name']} (id={exercise_id}) from catalog"
            )
            return new_exercise
        except Exception as e:
            logger.error(f"Failed to create exercise from catalog: {e}")
            return None

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
                   overall_rpe, fatigue_level, sleep_quality, notes, created_at,
                   actual_session_id
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
            actual_session_id=session_row[11],
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
        include_secondary: bool = True,
        secondary_weight: float = 0.5,
    ) -> dict[str, float]:
        """Get total volume grouped by muscle, including secondary muscles.

        Args:
            start_date: Filter sessions from this date
            end_date: Filter sessions until this date
            include_secondary: Whether to include secondary muscles (weighted)
            secondary_weight: Weight for secondary muscle volume (default 0.5)

        Returns:
            Dict mapping muscle name to volume in kg
        """
        conn = self._get_connection()

        # Get all sets with exercise info
        query = """
            SELECT e.id, e.name, e.primary_muscle, e.secondary_muscles_json,
                   es.reps, COALESCE(es.weight_kg, 0) as weight
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

        results = conn.execute(query, params).fetchall()
        conn.close()

        # Calculate volume per muscle
        muscle_volume: dict[str, float] = {}

        for row in results:
            primary_muscle = row[2]
            secondary_muscles_json = row[3]  # JSON string or None
            reps = row[4]
            weight = row[5]

            set_volume = reps * weight

            # Primary muscle gets full volume
            if primary_muscle:
                muscle_volume[primary_muscle] = (
                    muscle_volume.get(primary_muscle, 0) + set_volume
                )

            # Secondary muscles get weighted volume
            if include_secondary and secondary_muscles_json:
                import json

                try:
                    secondary_muscles = (
                        json.loads(secondary_muscles_json)
                        if isinstance(secondary_muscles_json, str)
                        else secondary_muscles_json
                    )
                    if isinstance(secondary_muscles, list):
                        for muscle in secondary_muscles:
                            muscle_volume[muscle] = (
                                muscle_volume.get(muscle, 0)
                                + set_volume * secondary_weight
                            )
                except (json.JSONDecodeError, TypeError):
                    pass

        return {
            k: round(v, 1)
            for k, v in sorted(muscle_volume.items(), key=lambda x: -x[1])
        }

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

    # ─────────────────────────────────────────────────────────────────────────
    # Garmin linking methods
    # ─────────────────────────────────────────────────────────────────────────

    def link_to_actual_session(self, session_id: int, garmin_id: int | None) -> bool:
        """Link a strength session to a Garmin activity."""
        conn = self._get_connection()

        # Check if session exists
        result = conn.execute(
            "SELECT id FROM app.strength_sessions WHERE id = ?", (session_id,)
        ).fetchone()

        if not result:
            conn.close()
            return False

        conn.execute(
            "UPDATE app.strength_sessions SET actual_session_id = ? WHERE id = ?",
            (garmin_id, session_id),
        )
        conn.close()
        return True
