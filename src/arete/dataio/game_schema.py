"""Additive athlete RPG storage; no existing activity is backfilled."""

DDL = """
CREATE TABLE IF NOT EXISTS app.game_profile (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    enabled BOOLEAN NOT NULL DEFAULT false,
    version INTEGER NOT NULL DEFAULT 0,
    activated_at TIMESTAMPTZ,
    athlete_class VARCHAR NOT NULL DEFAULT 'sentinel',
    silhouette VARCHAR NOT NULL DEFAULT 'balanced',
    equipped VARCHAR NOT NULL DEFAULT 'base'
);
INSERT INTO app.game_profile (id) VALUES (1) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS app.game_periods (
    started_at TIMESTAMPTZ PRIMARY KEY, ended_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS app.game_events (
    source_key VARCHAR PRIMARY KEY,
    canonical_key VARCHAR NOT NULL,
    activity_date DATE NOT NULL,
    week_start DATE NOT NULL,
    timezone VARCHAR NOT NULL,
    name VARCHAR NOT NULL,
    eligible BOOLEAN NOT NULL,
    reason VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    processed BOOLEAN NOT NULL DEFAULT false
);
CREATE TABLE IF NOT EXISTS app.game_weeks (
    week_start DATE PRIMARY KEY,
    goal INTEGER NOT NULL CHECK(goal BETWEEN 1 AND 14),
    timezone VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS app.game_ledger (
    id VARCHAR PRIMARY KEY,
    cause VARCHAR NOT NULL,
    week_start DATE,
    xp INTEGER NOT NULL,
    shards INTEGER NOT NULL,
    label VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS app.game_owned (
    skin VARCHAR PRIMARY KEY, created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
INSERT INTO app.game_owned (skin) VALUES ('base') ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS app.game_commands (
    key VARCHAR PRIMARY KEY, fingerprint VARCHAR NOT NULL,
    result VARCHAR NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def migrate(con) -> None:
    con.execute(DDL)
