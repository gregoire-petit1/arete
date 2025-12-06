from __future__ import annotations

from datetime import date
from typing import Any

from arete.dataio.db import connect


# ---------- Helpers ----------
def _next_id(con, table_qualified: str) -> int:
    result = con.execute(f"SELECT COALESCE(MAX(id), 0) + 1 FROM {table_qualified}").fetchone()
    if result is None:
        return 1
    return int(result[0])


def _session_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "date": row[1],
        "objective": row[2],
        "duration": row[3],
        "fatigue": row[4],
        "rpe_avg7d": row[5],
    }


def _user_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "sex": row[1],
        "age": row[2],
        "height": row[3],
        "weight": row[4],
        "desired_training_load": row[5],
    }


def _objective_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "sport": row[1],
        "name": row[2],
        "priority": row[3],
    }


def _record_from_row(row: tuple[Any, ...]) -> dict[str, Any]:
    return {
        "id": row[0],
        "sport": row[1],
        "event": row[2],
        "performance": row[3],
        "unit": row[4],
    }


# ---------- Sessions ----------
def create_session(
    *,
    session_date: date,
    objective: str,
    duration: int,
    fatigue: int,
    rpe_avg7d: float | None,
) -> dict[str, Any]:
    con = connect(False)
    try:
        new_id = _next_id(con, "app.sessions")
        row = con.execute(
            """
            INSERT INTO app.sessions (id, date, objective, duration, fatigue, rpe_avg7d)
            VALUES (?, ?, ?, ?, ?, ?)
            RETURNING id, date, objective, duration, fatigue, rpe_avg7d
            """,
            [new_id, session_date, objective, duration, fatigue, rpe_avg7d],
        ).fetchone()
        if row is None:
            raise RuntimeError("Failed to insert session")
        return _session_from_row(row)
    finally:
        con.close()


def list_sessions(skip: int, limit: int) -> tuple[int, list[dict[str, Any]]]:
    con = connect(True)
    try:
        count_row = con.execute("SELECT COUNT(*) FROM app.sessions").fetchone()
        total = int(count_row[0]) if count_row else 0
        rows = con.execute(
            """
            SELECT id, date, objective, duration, fatigue, rpe_avg7d
            FROM app.sessions
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            [limit, skip],
        ).fetchall()
        return total, [_session_from_row(r) for r in rows]
    finally:
        con.close()


def get_session(session_id: int) -> dict[str, Any] | None:
    con = connect(True)
    try:
        row = con.execute(
            """
            SELECT id, date, objective, duration, fatigue, rpe_avg7d
            FROM app.sessions
            WHERE id = ?
            """,
            [session_id],
        ).fetchone()
        return _session_from_row(row) if row else None
    finally:
        con.close()


def update_session(
    session_id: int,
    *,
    session_date: date,
    objective: str,
    duration: int,
    fatigue: int,
    rpe_avg7d: float | None,
) -> dict[str, Any] | None:
    con = connect(False)
    try:
        row = con.execute(
            """
            UPDATE app.sessions
            SET date = ?, objective = ?, duration = ?, fatigue = ?, rpe_avg7d = ?
            WHERE id = ?
            RETURNING id, date, objective, duration, fatigue, rpe_avg7d
            """,
            [session_date, objective, duration, fatigue, rpe_avg7d, session_id],
        ).fetchone()
        return _session_from_row(row) if row else None
    finally:
        con.close()


def delete_session(session_id: int) -> bool:
    """Delete a session by ID. Returns True if deleted, False if not found."""
    con = connect(False)
    try:
        # Use single atomic operation to avoid TOCTOU race condition
        result = con.execute(
            """
            DELETE FROM app.sessions WHERE id = ?
            RETURNING id
            """,
            [session_id],
        ).fetchone()
        return result is not None
    finally:
        con.close()


# ---------- User (single) ----------
def get_user() -> dict[str, Any] | None:
    con = connect(True)
    try:
        row = con.execute(
            """
            SELECT id, sex, age, height, weight, desired_training_load
            FROM app.users
            ORDER BY id ASC
            LIMIT 1
            """
        ).fetchone()
        return _user_from_row(row) if row else None
    finally:
        con.close()


def create_user(
    *,
    sex: str,
    age: int,
    height: float,
    weight: float,
    desired_training_load: float | None,
) -> dict[str, Any]:
    """Create a new user. Raises ValueError if user already exists."""
    con = connect(False)
    try:
        # Use INSERT with check in single statement to avoid race condition
        # First, attempt to get next ID (will be 1 if no users exist)
        new_id = _next_id(con, "app.users")

        # Try to insert - if another user was created concurrently,
        # we detect it by checking count before insert in a transaction
        con.execute("BEGIN TRANSACTION")
        try:
            existing_row = con.execute("SELECT COUNT(*) FROM app.users").fetchone()
            existing = int(existing_row[0]) if existing_row else 0
            if existing:
                con.execute("ROLLBACK")
                raise ValueError("User already exists")

            row = con.execute(
                """
                INSERT INTO app.users
                    (id, sex, age, height, weight, desired_training_load)
                VALUES (?, ?, ?, ?, ?, ?)
                RETURNING id, sex, age, height, weight, desired_training_load
                """,
                [new_id, sex, age, height, weight, desired_training_load],
            ).fetchone()
            con.execute("COMMIT")
            if row is None:
                raise RuntimeError("Failed to insert user")
            return _user_from_row(row)
        except Exception:
            con.execute("ROLLBACK")
            raise
    finally:
        con.close()


def update_user(
    *,
    sex: str,
    age: int,
    height: float,
    weight: float,
    desired_training_load: float | None,
) -> dict[str, Any] | None:
    con = connect(False)
    try:
        row = con.execute(
            """
            UPDATE app.users
            SET sex = ?, age = ?, height = ?, weight = ?, desired_training_load = ?
            WHERE id = (SELECT id FROM app.users ORDER BY id ASC LIMIT 1)
            RETURNING id, sex, age, height, weight, desired_training_load
            """,
            [sex, age, height, weight, desired_training_load],
        ).fetchone()
        return _user_from_row(row) if row else None
    finally:
        con.close()


# ---------- Objectives ----------
def create_objective(*, sport: str, name: str, priority: int) -> dict[str, Any]:
    con = connect(False)
    try:
        new_id = _next_id(con, "app.objectives")
        row = con.execute(
            """
            INSERT INTO app.objectives (id, sport, name, priority)
            VALUES (?, ?, ?, ?)
            RETURNING id, sport, name, priority
            """,
            [new_id, sport, name, priority],
        ).fetchone()
        if row is None:
            raise RuntimeError("Failed to insert objective")
        return _objective_from_row(row)
    finally:
        con.close()


def list_objectives(skip: int, limit: int) -> tuple[int, list[dict[str, Any]]]:
    con = connect(True)
    try:
        count_row = con.execute("SELECT COUNT(*) FROM app.objectives").fetchone()
        total = int(count_row[0]) if count_row else 0
        rows = con.execute(
            """
            SELECT id, sport, name, priority
            FROM app.objectives
            ORDER BY priority DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            [limit, skip],
        ).fetchall()
        return total, [_objective_from_row(r) for r in rows]
    finally:
        con.close()


def update_objective(obj_id: int, *, sport: str, name: str, priority: int) -> dict[str, Any] | None:
    con = connect(False)
    try:
        row = con.execute(
            """
            UPDATE app.objectives
            SET sport = ?, name = ?, priority = ?
            WHERE id = ?
            RETURNING id, sport, name, priority
            """,
            [sport, name, priority, obj_id],
        ).fetchone()
        return _objective_from_row(row) if row else None
    finally:
        con.close()


def delete_objective(obj_id: int) -> bool:
    """Delete an objective by ID. Returns True if deleted, False if not found."""
    con = connect(False)
    try:
        # Use single atomic operation to avoid TOCTOU race condition
        result = con.execute(
            """
            DELETE FROM app.objectives WHERE id = ?
            RETURNING id
            """,
            [obj_id],
        ).fetchone()
        return result is not None
    finally:
        con.close()


# ---------- Personal records ----------
def create_record(*, sport: str, event: str, performance: float, unit: str) -> dict[str, Any]:
    con = connect(False)
    try:
        new_id = _next_id(con, "app.personal_records")
        row = con.execute(
            """
            INSERT INTO app.personal_records (id, sport, event, performance, unit)
            VALUES (?, ?, ?, ?, ?)
            RETURNING id, sport, event, performance, unit
            """,
            [new_id, sport, event, performance, unit],
        ).fetchone()
        if row is None:
            raise RuntimeError("Failed to insert record")
        return _record_from_row(row)
    finally:
        con.close()


def list_records(skip: int, limit: int) -> tuple[int, list[dict[str, Any]]]:
    con = connect(True)
    try:
        count_row = con.execute("SELECT COUNT(*) FROM app.personal_records").fetchone()
        total = int(count_row[0]) if count_row else 0
        rows = con.execute(
            """
            SELECT id, sport, event, performance, unit
            FROM app.personal_records
            ORDER BY id DESC
            LIMIT ? OFFSET ?
            """,
            [limit, skip],
        ).fetchall()
        return total, [_record_from_row(r) for r in rows]
    finally:
        con.close()


def update_record(
    rec_id: int, *, sport: str, event: str, performance: float, unit: str
) -> dict[str, Any] | None:
    con = connect(False)
    try:
        row = con.execute(
            """
            UPDATE app.personal_records
            SET sport = ?, event = ?, performance = ?, unit = ?
            WHERE id = ?
            RETURNING id, sport, event, performance, unit
            """,
            [sport, event, performance, unit, rec_id],
        ).fetchone()
        return _record_from_row(row) if row else None
    finally:
        con.close()


def delete_record(rec_id: int) -> bool:
    """Delete a personal record by ID. Returns True if deleted, False if not found."""
    con = connect(False)
    try:
        # Use single atomic operation to avoid TOCTOU race condition
        result = con.execute(
            """
            DELETE FROM app.personal_records WHERE id = ?
            RETURNING id
            """,
            [rec_id],
        ).fetchone()
        return result is not None
    finally:
        con.close()
