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
    assert versions == [1, 2, 3, 4, 5]
