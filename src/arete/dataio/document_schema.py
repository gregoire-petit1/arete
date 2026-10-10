"""Durable document imports and outbound Garmin operations."""

DDL = """
CREATE TABLE IF NOT EXISTS app.document_quota (
    id INTEGER PRIMARY KEY, used_bytes BIGINT NOT NULL
);
INSERT INTO app.document_quota (id, used_bytes) SELECT 1, 0 WHERE NOT EXISTS
    (SELECT 1 FROM app.document_quota WHERE id = 1);
CREATE TABLE IF NOT EXISTS app.coach_documents (
    id VARCHAR PRIMARY KEY, thread_id VARCHAR NOT NULL, name VARCHAR NOT NULL,
    size BIGINT NOT NULL, sha256 VARCHAR NOT NULL, status VARCHAR NOT NULL,
    extraction JSON, created_at TIMESTAMP DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS app.coach_document_chunks (
    document_id VARCHAR NOT NULL, position INTEGER NOT NULL, content BLOB NOT NULL,
    PRIMARY KEY (document_id, position)
);
CREATE TABLE IF NOT EXISTS app.coach_imports (
    id VARCHAR PRIMARY KEY, thread_id VARCHAR NOT NULL, version INTEGER NOT NULL,
    status VARCHAR NOT NULL, sessions JSON NOT NULL, confirmation_key VARCHAR,
    selected JSON, session_ids JSON, created_at TIMESTAMP DEFAULT current_timestamp
);
CREATE TABLE IF NOT EXISTS app.garmin_exports (
    session_id INTEGER PRIMARY KEY, operation_id VARCHAR NOT NULL,
    state VARCHAR NOT NULL, workout_id BIGINT, schedule_id BIGINT,
    fingerprint VARCHAR, remote_snapshot JSON, device_id BIGINT,
    intended_payload JSON, intended_date DATE, remote_date DATE, phase VARCHAR,
    error VARCHAR, deleted BOOLEAN DEFAULT false,
    updated_at TIMESTAMP DEFAULT current_timestamp
);
"""


def migrate(con) -> None:
    con.execute(DDL)
    con.execute(
        "ALTER TABLE app.planned_sessions ADD COLUMN IF NOT EXISTS prescription JSON"
    )
    con.execute(
        "ALTER TABLE app.planned_sessions ADD COLUMN IF NOT EXISTS provenance JSON"
    )
    con.execute(
        "ALTER TABLE app.planned_sessions ADD COLUMN IF NOT EXISTS revision INTEGER DEFAULT 1"
    )
