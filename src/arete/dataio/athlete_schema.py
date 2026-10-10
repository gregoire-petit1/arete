"""Account identities and athlete lifecycle, independent of training data.

Clerk's subject is the stable account identity. Email is contact information,
never a foreign key or proof that an account owns an existing athlete.
"""

from __future__ import annotations

import duckdb

DDL = """
CREATE TABLE IF NOT EXISTS app.athletes (
    id INTEGER PRIMARY KEY,
    created_at TIMESTAMP NOT NULL DEFAULT current_timestamp,
    deleted_at TIMESTAMP,
    last_sync_at TIMESTAMP,
    sync_lease_until TIMESTAMP
);
ALTER TABLE app.users ADD COLUMN IF NOT EXISTS email_verified_at TIMESTAMP;
ALTER TABLE app.users ADD COLUMN IF NOT EXISTS profile_synced_at TIMESTAMP;
ALTER TABLE app.users ADD COLUMN IF NOT EXISTS deleted_at TIMESTAMP;
"""


def migrate(con: duckdb.DuckDBPyConnection) -> None:
    """Preserve existing account mappings and the original athlete's data."""
    con.execute(DDL)
    con.execute(
        "INSERT INTO app.athletes (id) "
        "SELECT 1 UNION SELECT athlete_id FROM app.users WHERE athlete_id IS NOT NULL "
        "ON CONFLICT DO NOTHING"
    )
    from arete.dataio.tenant_schema import LEGACY_OWNERS

    for table in sorted(LEGACY_OWNERS):
        columns = {r[0] for r in con.execute(f"DESCRIBE app.{table}").fetchall()}
        if "user_id" in columns:
            con.execute(
                f"INSERT INTO app.athletes(id) SELECT DISTINCT user_id FROM app.{table} "
                "WHERE user_id IS NOT NULL ON CONFLICT DO NOTHING"
            )
    # A restored database may already contain additional athlete identities.
    # Starting beyond their maximum avoids sequence collisions at first signup.
    row = con.execute("SELECT coalesce(max(id), 1) + 1 FROM app.athletes").fetchone()
    assert row is not None
    start = int(row[0])
    assert start >= 2
    con.execute(f"CREATE SEQUENCE IF NOT EXISTS app.athletes_seq START {start}")
