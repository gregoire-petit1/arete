"""Schema initialisation and versioned migrations on legacy databases."""

from __future__ import annotations

import duckdb

from arete.dataio import init_duckdb


def test_fresh_db_records_all_versions(tmp_path, monkeypatch):
    monkeypatch.setenv("ARETE_DB", str(tmp_path / "fresh.duckdb"))
    init_duckdb.main()
    con = duckdb.connect(str(tmp_path / "fresh.duckdb"), read_only=True)
    versions = [
        r[0]
        for r in con.execute(
            "SELECT version FROM app.schema_version ORDER BY 1"
        ).fetchall()
    ]
    con.close()
    assert versions == [v for v, _ in init_duckdb.MIGRATIONS]


def test_legacy_column_is_renamed_once(tmp_path, monkeypatch):
    path = tmp_path / "legacy.duckdb"
    monkeypatch.setenv("ARETE_DB", str(path))
    # Legacy shape: strength_sessions still has garmin_activity_id, no schema_version yet
    con = duckdb.connect(str(path))
    con.execute("CREATE SCHEMA app")
    con.execute(
        "CREATE TABLE app.strength_sessions (id INTEGER, garmin_activity_id INTEGER)"
    )
    con.execute("CREATE TABLE app.user_settings (user_id INTEGER)")
    con.execute("CREATE TABLE app.actual_sessions (id INTEGER)")
    con.close()

    init_duckdb.main()
    init_duckdb.main()  # second run must be a no-op

    con = duckdb.connect(str(path), read_only=True)
    cols = {r[0] for r in con.execute("DESCRIBE app.strength_sessions").fetchall()}
    versions = [
        r[0]
        for r in con.execute(
            "SELECT version FROM app.schema_version ORDER BY 1"
        ).fetchall()
    ]
    con.close()
    assert "actual_session_id" in cols and "garmin_activity_id" not in cols
    assert versions == [version for version, _ in init_duckdb.MIGRATIONS]


def test_a_current_database_skips_the_ddl(tmp_path, monkeypatch):
    # Boot runs one statement against a current schema, not the whole DDL.
    monkeypatch.setenv("ARETE_DB", str(tmp_path / "current.duckdb"))
    init_duckdb.main()
    monkeypatch.setattr(init_duckdb, "DDL", "SELECT * FROM no_such_table")
    init_duckdb.main()  # would raise if the DDL ran


def test_a_database_behind_runs_its_migrations(tmp_path, monkeypatch):
    path = tmp_path / "behind.duckdb"
    monkeypatch.setenv("ARETE_DB", str(path))
    init_duckdb.main()
    con = duckdb.connect(str(path))
    con.execute(
        "DELETE FROM app.schema_version WHERE version = ?",
        [init_duckdb.MIGRATIONS[-1][0]],
    )
    con.close()
    init_duckdb.main()
    con = duckdb.connect(str(path), read_only=True)
    (latest,) = con.execute("SELECT MAX(version) FROM app.schema_version").fetchone()
    con.close()
    assert latest == init_duckdb.MIGRATIONS[-1][0]


def test_document_migration_preserves_version_twelve_planning(tmp_path, monkeypatch):
    path = tmp_path / "version-twelve.duckdb"
    monkeypatch.setenv("ARETE_DB", str(path))
    init_duckdb.main()
    with duckdb.connect(str(path)) as con:
        con.execute(
            "INSERT INTO app.planned_sessions (date,sport,session_type,description) VALUES ('2027-01-12','running','endurance','Existing session')"
        )
        for column in ("prescription", "provenance", "revision"):
            con.execute(f"ALTER TABLE app.planned_sessions DROP COLUMN {column}")
        for table in (
            "document_quota",
            "coach_documents",
            "coach_document_chunks",
            "coach_imports",
            "garmin_exports",
        ):
            con.execute(f"DROP TABLE app.{table}")
        con.execute("DELETE FROM app.schema_version WHERE version >= 13")
    init_duckdb.main()
    with duckdb.connect(str(path)) as con:
        row = con.execute(
            "SELECT description,prescription,provenance,revision FROM app.planned_sessions"
        ).fetchone()
        assert row == ("Existing session", None, None, 1)
        assert con.execute("SELECT used_bytes FROM app.document_quota").fetchone() == (
            0,
        )


def test_sport_names_are_canonicalised_once(tmp_path, monkeypatch):
    path = tmp_path / "sports.duckdb"
    monkeypatch.setenv("ARETE_DB", str(path))
    init_duckdb.main()
    con = duckdb.connect(str(path))
    con.execute("DELETE FROM app.schema_version WHERE version >= 9")
    for i, sport in enumerate(("run", "Ride", "walk", "running", "TrailRun"), 1):
        con.execute(
            "INSERT INTO app.actual_sessions (id, user_id, date, sport, duration_sec, source)"
            " VALUES (?, 1, DATE '2026-10-01', ?, 3600, 'manual')",
            [i, sport],
        )
    con.execute(
        "INSERT INTO app.planned_sessions (id, user_id, date, sport, session_type)"
        " VALUES (1, 1, DATE '2026-10-01', 'run', 'endurance')"
    )
    con.close()

    init_duckdb.main()
    init_duckdb.main()  # second run must be a no-op

    con = duckdb.connect(str(path), read_only=True)
    actual = [
        r[0]
        for r in con.execute(
            "SELECT sport FROM app.actual_sessions ORDER BY id"
        ).fetchall()
    ]
    (planned,) = con.execute("SELECT sport FROM app.planned_sessions").fetchone()
    (latest,) = con.execute("SELECT MAX(version) FROM app.schema_version").fetchone()
    con.close()
    assert actual == ["running", "cycling", "walking", "running", "running"]
    assert planned == "running"
    assert latest == init_duckdb.MIGRATIONS[-1][0]


def test_m10_adds_performance_columns_to_a_legacy_table(tmp_path, monkeypatch):
    path = tmp_path / "perf.duckdb"
    monkeypatch.setenv("ARETE_DB", str(path))
    init_duckdb.main()
    con = duckdb.connect(str(path))
    for name in init_duckdb.GARMIN_PERFORMANCE_COLUMNS:
        con.execute(f"ALTER TABLE app.daily_metrics DROP COLUMN {name}")
    con.execute("DELETE FROM app.schema_version WHERE version >= 10")
    con.close()

    init_duckdb.main()
    init_duckdb.main()

    con = duckdb.connect(str(path), read_only=True)
    cols = {r[0] for r in con.execute("DESCRIBE app.daily_metrics").fetchall()}
    con.close()
    assert set(init_duckdb.GARMIN_PERFORMANCE_COLUMNS) <= cols


def test_m17_creates_the_users_table_once(tmp_path, monkeypatch):
    path = tmp_path / "users.duckdb"
    monkeypatch.setenv("ARETE_DB", str(path))
    init_duckdb.main()
    con = duckdb.connect(str(path))
    con.execute("DROP TABLE app.users")
    con.execute("DELETE FROM app.schema_version WHERE version >= 17")
    con.close()
    init_duckdb.main()
    init_duckdb.main()
    con = duckdb.connect(str(path), read_only=True)
    cols = {r[0] for r in con.execute("DESCRIBE app.users").fetchall()}
    (latest,) = con.execute("SELECT MAX(version) FROM app.schema_version").fetchone()
    con.close()
    assert {"clerk_user_id", "email", "athlete_id"} <= cols
    assert latest == init_duckdb.MIGRATIONS[-1][0]
