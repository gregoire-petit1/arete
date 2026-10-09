"""Additive personal-memory migration; old provenance stays unknown."""


def migrate(con) -> None:
    for definition in (
        "evidence VARCHAR DEFAULT 'legacy'",
        "source_ref VARCHAR DEFAULT ''",
        "valid_until DATE",
        "revision INTEGER DEFAULT 1",
    ):
        con.execute(
            f"ALTER TABLE app.athlete_facts ADD COLUMN IF NOT EXISTS {definition}"
        )
    con.execute("""
        CREATE TABLE IF NOT EXISTS app.athlete_fact_revisions (
            fact_id INTEGER NOT NULL,
            revision INTEGER NOT NULL,
            snapshot JSON NOT NULL,
            recorded_at TIMESTAMP DEFAULT current_timestamp,
            PRIMARY KEY (fact_id, revision)
        )
    """)
