"""Schema initialisation and versioned migrations on legacy databases."""

from __future__ import annotations

import duckdb
import pytest

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


def test_m18_creates_the_users_table_once(tmp_path, monkeypatch):
    path = tmp_path / "users.duckdb"
    monkeypatch.setenv("ARETE_DB", str(path))
    init_duckdb.main()
    con = duckdb.connect(str(path))
    con.execute("DROP TABLE app.users")
    con.execute("DELETE FROM app.schema_version WHERE version >= 18")
    con.close()
    init_duckdb.main()
    init_duckdb.main()
    con = duckdb.connect(str(path), read_only=True)
    cols = {r[0] for r in con.execute("DESCRIBE app.users").fetchall()}
    (latest,) = con.execute("SELECT MAX(version) FROM app.schema_version").fetchone()
    con.close()
    assert {"clerk_user_id", "email", "athlete_id"} <= cols
    assert latest == init_duckdb.MIGRATIONS[-1][0]


@pytest.mark.parametrize("version_19", ["gamification", "personal_memory"])
def test_memory_upgrade_accepts_both_version_19_histories(
    tmp_path, monkeypatch, version_19
):
    path = tmp_path / "version-nineteen.duckdb"
    monkeypatch.setenv("ARETE_DB", str(path))
    with monkeypatch.context() as old:
        old.setattr(
            init_duckdb,
            "MIGRATIONS",
            [(v, fn) for v, fn in init_duckdb.MIGRATIONS if v <= 18],
        )
        init_duckdb.main()
    with duckdb.connect(str(path)) as con:
        con.execute(
            "INSERT INTO app.athlete_facts(kind, text, since) VALUES ('constraint', 'Pas de mercredi', DATE '2026-10-01')"
        )
        if version_19 == "gamification":
            from arete.dataio.game_schema import migrate

            migrate(con)
            con.execute(
                "UPDATE app.game_profile SET enabled=true, version=3 WHERE id=1"
            )
            expected_evidence = "legacy"
        else:
            from arete.dataio.memory_schema import migrate

            migrate(con)
            con.execute(
                "UPDATE app.athlete_facts SET evidence='explicit', source_ref='Déclaration athlète'"
            )
            expected_evidence = "explicit"
        con.execute("INSERT INTO app.schema_version(version) VALUES (19)")
    init_duckdb.main()
    init_duckdb.main()
    with duckdb.connect(str(path), read_only=True) as con:
        assert con.execute(
            "SELECT text, evidence, revision FROM app.athlete_facts"
        ).fetchone() == ("Pas de mercredi", expected_evidence, 1)
        assert con.execute(
            "SELECT count(*) FROM app.athlete_fact_revisions"
        ).fetchone() == (0,)
        expected_game = (True, 3) if version_19 == "gamification" else (False, 0)
        assert (
            con.execute(
                "SELECT enabled, version FROM app.game_profile WHERE id=1"
            ).fetchone()
            == expected_game
        )
        assert con.execute(
            "SELECT max(version) FROM app.schema_version"
        ).fetchone() == (max(v for v, _ in init_duckdb.MIGRATIONS),)


def test_a_missing_version_below_the_latest_still_runs(tmp_path, monkeypatch):
    # A preview database shared by parallel branches can record a higher
    # version before a lower one is merged: the lower one must still run.
    path = tmp_path / "gap.duckdb"
    monkeypatch.setenv("ARETE_DB", str(path))
    init_duckdb.main()
    con = duckdb.connect(str(path))
    con.execute("DROP TABLE app.calendar_actions")
    con.execute("DROP TABLE app.calendar_connections")
    con.execute("DELETE FROM app.schema_version WHERE version = 17")
    con.execute("INSERT INTO app.schema_version (version) VALUES (9999)")
    con.close()
    init_duckdb.main()
    init_duckdb.main()
    con = duckdb.connect(str(path), read_only=True)
    tables = {
        r[0]
        for r in con.execute(
            "SELECT table_name FROM duckdb_tables() WHERE schema_name = 'app'"
        ).fetchall()
    }
    versions = [
        r[0]
        for r in con.execute(
            "SELECT version FROM app.schema_version WHERE version = 17"
        ).fetchall()
    ]
    con.close()
    assert {"calendar_actions", "calendar_connections"} <= tables
    assert versions == [17]  # recorded once, and the unknown 9999 is ignored


def test_m34_adds_the_plan_sync_columns_once(tmp_path, monkeypatch):
    from arete.services.calendar_repository import PLAN_SYNC_DDL

    path = tmp_path / "plan-sync.duckdb"
    monkeypatch.setenv("ARETE_DB", str(path))
    init_duckdb.main()
    # "ALTER TABLE <table> ADD COLUMN IF NOT EXISTS <column> <type>;"
    added = [
        (line.split()[2], line.split()[8])
        for line in PLAN_SYNC_DDL.strip().splitlines()
    ]
    with duckdb.connect(str(path)) as con:
        for table, column in added:
            con.execute(f"ALTER TABLE {table} DROP COLUMN {column}")
        con.execute(
            "INSERT INTO app.calendar_connections (connection_key, enabled) VALUES ('k', TRUE)"
        )
        con.execute(
            "INSERT INTO app.planned_sessions (date, sport, session_type) VALUES ('2026-10-12', 'running', 'endurance')"
        )
        con.execute("DELETE FROM app.schema_version WHERE version = 34")
    init_duckdb.main()
    init_duckdb.main()  # recorded once, then skipped
    with duckdb.connect(str(path), read_only=True) as con:
        for table, column in added:
            columns = {r[0] for r in con.execute(f"DESCRIBE {table}").fetchall()}
            assert column in columns
        assert con.execute(
            "SELECT enabled, plan_sync, plan_calendar FROM app.calendar_connections"
        ).fetchone() == (True, False, None)
        assert con.execute(
            "SELECT session_type, google_event_id FROM app.planned_sessions"
        ).fetchone() == ("endurance", None)
        assert con.execute(
            "SELECT count(*) FROM app.schema_version WHERE version = 34"
        ).fetchone() == (1,)
