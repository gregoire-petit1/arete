import logging

from arete.dataio.db import connect

logger = logging.getLogger(__name__)

DDL = """
CREATE SCHEMA IF NOT EXISTS app;

-- ============================================================
-- Garmin Pipeline Tables (Phase 1)
-- ============================================================

-- Sequences for auto-increment
CREATE SEQUENCE IF NOT EXISTS app.planned_sessions_seq START 1;
CREATE SEQUENCE IF NOT EXISTS app.actual_sessions_seq START 1;
CREATE SEQUENCE IF NOT EXISTS app.session_analysis_seq START 1;

-- Planned training sessions (recommendations from coach/LLM)
CREATE TABLE IF NOT EXISTS app.planned_sessions (
    id              INTEGER PRIMARY KEY DEFAULT nextval('app.planned_sessions_seq'),
    user_id         INTEGER,
    date            DATE NOT NULL,
    sport           VARCHAR NOT NULL DEFAULT 'running',
    session_type    VARCHAR NOT NULL,          -- 'recovery', 'endurance', 'tempo', 'intervals', 'long_run'
    target_duration_min INTEGER,               -- planned duration
    target_distance_km  DOUBLE,                -- planned distance
    target_hr_zone  VARCHAR,                   -- 'Z1', 'Z2', etc.
    target_intensity VARCHAR,                  -- 'easy', 'moderate', 'hard'
    description     VARCHAR,                   -- workout description
    source          VARCHAR DEFAULT 'manual',  -- 'manual', 'llm', 'coach'
    status          VARCHAR DEFAULT 'pending', -- 'pending', 'completed', 'skipped', 'modified'
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Actual training sessions (imported from Garmin/FIT files)
CREATE TABLE IF NOT EXISTS app.actual_sessions (
    id                  INTEGER PRIMARY KEY DEFAULT nextval('app.actual_sessions_seq'),
    planned_session_id  INTEGER,               -- FK to planned_sessions (NULL if unplanned)
    user_id             INTEGER,
    date                DATE NOT NULL,
    sport               VARCHAR NOT NULL DEFAULT 'running',
    session_type        VARCHAR,               -- auto-detected or manual

    -- Core metrics
    duration_sec        INTEGER NOT NULL,
    distance_m          DOUBLE,
    calories            INTEGER,

    -- Heart rate
    avg_hr              INTEGER,
    max_hr              INTEGER,
    hr_zones_json       VARCHAR,               -- JSON: {"Z1": 300, "Z2": 1200, ...} seconds per zone

    -- Pace/Speed
    avg_pace_sec_km     INTEGER,               -- seconds per km
    avg_speed_mps       DOUBLE,                -- meters per second
    max_speed_mps       DOUBLE,

    -- Elevation
    ascent_m            DOUBLE,
    descent_m           DOUBLE,

    -- GPS (optional, for route analysis)
    start_lat           DOUBLE,
    start_lon           DOUBLE,

    -- Source tracking
    source              VARCHAR NOT NULL,      -- 'fit_file', 'garmin_connect', 'manual', 'strava'
    source_file         VARCHAR,               -- original filename
    garmin_activity_id  VARCHAR,               -- Garmin Connect activity ID

    -- Running dynamics (from Garmin sensors)
    avg_cadence         INTEGER,               -- steps per minute (running) or RPM (cycling)
    max_cadence         INTEGER,
    avg_vertical_oscillation DOUBLE,           -- mm (running only)
    avg_ground_contact_time  INTEGER,          -- ms (running only)
    avg_stride_length   DOUBLE,                -- meters

    -- Computed adherence (filled by matching logic)
    adherence_score     DOUBLE,                -- 0-100: how well it matched the plan
    intensity_deviation DOUBLE,                -- % deviation from planned intensity

    -- Timestamps
    start_time          TIMESTAMP,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- Analytics / enrichment columns
    name                VARCHAR,
    notes               TEXT,
    rpe                 INTEGER,
    workout_type        VARCHAR,
    moving_time_sec     INTEGER,
    suffer_score        INTEGER,
    laps_json           TEXT,
    splits_json         TEXT,
    best_efforts_json   TEXT,
    avg_watts           INTEGER,
    weighted_avg_watts  INTEGER,
    device_name         VARCHAR
);

-- Session analysis/feedback (LLM-generated insights)
CREATE TABLE IF NOT EXISTS app.session_analysis (
    id                  INTEGER PRIMARY KEY DEFAULT nextval('app.session_analysis_seq'),
    actual_session_id   INTEGER NOT NULL,      -- FK to actual_sessions
    analysis_type       VARCHAR NOT NULL,      -- 'adherence', 'performance', 'recovery'
    insights_json       VARCHAR,               -- JSON with structured insights
    recommendations     VARCHAR,               -- text recommendations
    generated_by        VARCHAR DEFAULT 'llm', -- 'llm', 'rules', 'manual'
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- Strength Training Tables
-- ============================================================

-- Sequences for strength tables
CREATE SEQUENCE IF NOT EXISTS app.exercises_seq START 1;
CREATE SEQUENCE IF NOT EXISTS app.strength_sessions_seq START 1;
CREATE SEQUENCE IF NOT EXISTS app.session_exercises_seq START 1;
CREATE SEQUENCE IF NOT EXISTS app.exercise_sets_seq START 1;

-- Exercise library (reusable exercise definitions)
CREATE TABLE IF NOT EXISTS app.exercises (
    id                      INTEGER PRIMARY KEY DEFAULT nextval('app.exercises_seq'),
    name                    VARCHAR NOT NULL,
    category                VARCHAR NOT NULL,          -- 'squat', 'hinge', 'push_horizontal', etc.
    primary_muscle          VARCHAR NOT NULL,          -- 'quads', 'chest', 'back', etc.
    secondary_muscles_json  VARCHAR,                   -- JSON array of muscle groups
    equipment               VARCHAR,                   -- 'barbell', 'dumbbell', 'cable', 'bodyweight'
    is_unilateral           BOOLEAN DEFAULT FALSE,
    notes                   VARCHAR,
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Strength training sessions
CREATE TABLE IF NOT EXISTS app.strength_sessions (
    id              INTEGER PRIMARY KEY DEFAULT nextval('app.strength_sessions_seq'),
    user_id         INTEGER NOT NULL DEFAULT 1,
    date            DATE NOT NULL,
    name            VARCHAR,                   -- 'Push Day', 'Upper A', etc.
    program         VARCHAR,                   -- 'PPL', '531', 'GZCLP', etc.
    duration_min    INTEGER,
    overall_rpe     DOUBLE,                    -- Session RPE (1-10)
    fatigue_level   INTEGER,                   -- Pre-workout fatigue (1-5)
    sleep_quality   INTEGER,                   -- Night before (1-5)
    notes           VARCHAR,
    garmin_activity_id INTEGER,                -- FK to actual_sessions (optional link)
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Exercises performed in a session (junction table)
CREATE TABLE IF NOT EXISTS app.session_exercises (
    id              INTEGER PRIMARY KEY DEFAULT nextval('app.session_exercises_seq'),
    session_id      INTEGER NOT NULL,          -- FK to strength_sessions
    exercise_id     INTEGER NOT NULL,          -- FK to exercises
    exercise_order  INTEGER NOT NULL DEFAULT 1,
    target_sets     INTEGER,
    target_reps     VARCHAR,                   -- '8-12' or '5'
    target_rpe      DOUBLE,
    notes           VARCHAR
);

-- Individual sets within a session exercise
CREATE TABLE IF NOT EXISTS app.exercise_sets (
    id                  INTEGER PRIMARY KEY DEFAULT nextval('app.exercise_sets_seq'),
    session_exercise_id INTEGER NOT NULL,      -- FK to session_exercises
    set_number          INTEGER NOT NULL,
    reps                INTEGER NOT NULL,
    weight_kg           DOUBLE,
    rpe                 DOUBLE,                -- 1-10 scale
    rir                 INTEGER,               -- Reps In Reserve
    rest_sec            INTEGER,               -- Rest after this set
    tempo               VARCHAR,               -- '3-1-1-0' format
    is_warmup           BOOLEAN DEFAULT FALSE,
    is_failure          BOOLEAN DEFAULT FALSE,
    notes               VARCHAR
);

-- ============================================================
-- User Settings
-- ============================================================

CREATE TABLE IF NOT EXISTS app.user_settings (
    user_id                 INTEGER PRIMARY KEY DEFAULT 1,
    display_name            VARCHAR NOT NULL DEFAULT 'HUNTER',
    email                   VARCHAR,
    timezone                VARCHAR DEFAULT 'Europe/Paris',
    weekly_training_goal    INTEGER DEFAULT 6,
    rest_day_preference     VARCHAR DEFAULT 'monday',  -- comma-separated days
    fatigue_threshold       INTEGER DEFAULT 85,
    fitness_goal            VARCHAR DEFAULT 'build',   -- 'maintenance', 'build', 'peak', 'recovery'
    notifications_enabled   BOOLEAN DEFAULT TRUE,
    theme                   VARCHAR DEFAULT 'dark',    -- 'dark', 'darker', 'abyss'
    exercise_abbreviations  VARCHAR DEFAULT '{}',      -- JSON: {"bp": "bench press", "ng": "neutral grip", ...}
    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Insert default settings if not exists
INSERT INTO app.user_settings (user_id) 
SELECT 1 WHERE NOT EXISTS (SELECT 1 FROM app.user_settings WHERE user_id = 1);

-- ============================================================
-- Strava Integration
-- ============================================================

CREATE TABLE IF NOT EXISTS app.strava_tokens (
    user_id         INTEGER PRIMARY KEY DEFAULT 1,
    athlete_id      INTEGER,
    access_token    VARCHAR NOT NULL,
    refresh_token   VARCHAR NOT NULL,
    expires_at      INTEGER NOT NULL,
    athlete_name    VARCHAR,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- Banister Personalization (Task 1)
-- ============================================================

CREATE TABLE IF NOT EXISTS app.banister_coefficients (
    user_id         INTEGER PRIMARY KEY DEFAULT 1,
    k1              FLOAT NOT NULL DEFAULT 1.0,
    k2              FLOAT NOT NULL DEFAULT 2.0,
    baseline        FLOAT NOT NULL DEFAULT 100.0,
    r2              FLOAT,
    n_samples       INTEGER,
    fitted_at       TIMESTAMP DEFAULT now()
);
"""


def _run_migrations(con) -> None:
    """Apply schema migrations for existing databases.

    Each migration checks if the change is needed before applying,
    making them safe to run repeatedly (idempotent).
    """
    # Migration 1: Add exercise_abbreviations column to user_settings
    cols = {row[0] for row in con.execute("DESCRIBE app.user_settings").fetchall()}
    if "exercise_abbreviations" not in cols:
        con.execute(
            "ALTER TABLE app.user_settings "
            "ADD COLUMN exercise_abbreviations VARCHAR DEFAULT '{}'"
        )
        logger.info("Migration: added exercise_abbreviations to user_settings")

    # Migration 2: add analytics columns to actual_sessions
    _analytics_cols = {
        "name": "VARCHAR",
        "notes": "TEXT",
        "rpe": "INTEGER",
        "workout_type": "VARCHAR",
        "moving_time_sec": "INTEGER",
        "suffer_score": "INTEGER",
        "laps_json": "TEXT",
        "splits_json": "TEXT",
        "best_efforts_json": "TEXT",
        "avg_watts": "INTEGER",
        "weighted_avg_watts": "INTEGER",
        "device_name": "VARCHAR",
    }
    for col_name, col_type in _analytics_cols.items():
        try:
            con.execute(
                f"ALTER TABLE app.actual_sessions ADD COLUMN {col_name} {col_type}"
            )
            logger.info("Added column %s to actual_sessions", col_name)
        except Exception:
            pass  # Column already exists

    # Migration 3: add banister_coefficients table
    _banister_exists = con.execute(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
        "WHERE table_schema='app' AND table_name='banister_coefficients')"
    ).fetchone()[0]
    if not _banister_exists:
        con.execute("""
            CREATE TABLE app.banister_coefficients (
                user_id         INTEGER PRIMARY KEY DEFAULT 1,
                k1              FLOAT NOT NULL DEFAULT 1.0,
                k2              FLOAT NOT NULL DEFAULT 2.0,
                baseline        FLOAT NOT NULL DEFAULT 100.0,
                r2              FLOAT,
                n_samples       INTEGER,
                fitted_at       TIMESTAMP DEFAULT now()
            )
        """)
        logger.info("Migration: created banister_coefficients table")


def main():
    """Initialize the DuckDB database with the required schema."""
    con = None
    try:
        con = connect(False)
        for stmt in DDL.strip().split(";"):
            s = stmt.strip()
            if s:
                con.execute(s + ";")

        _run_migrations(con)

        tables = con.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='app'"
        ).fetchall()
        logger.info(f"Tables created: {tables}")
        print("Tables:", tables)
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise
    finally:
        if con:
            con.close()


if __name__ == "__main__":
    main()
