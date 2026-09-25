import logging
from collections.abc import Callable
from typing import Any

from arete.dataio.db import connect

logger = logging.getLogger(__name__)

DDL = """
CREATE SCHEMA IF NOT EXISTS app;

CREATE TABLE IF NOT EXISTS app.schema_version (
    version     INTEGER PRIMARY KEY,
    applied_at  TIMESTAMP DEFAULT now()
);

-- ============================================================
-- Garmin Pipeline Tables (Phase 1)
-- ============================================================

-- Sequences for auto-increment
CREATE SEQUENCE IF NOT EXISTS app.planned_sessions_seq START 1;
CREATE SEQUENCE IF NOT EXISTS app.actual_sessions_seq START 1;

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
    garmin_activity_id  VARCHAR,               -- Garmin Connect activity ID (or Strava ID when source = strava)
    strava_activity_id  VARCHAR,               -- Strava ID merged into a Garmin session

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
    actual_session_id INTEGER,                 -- FK to app.actual_sessions.id (optional link)
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
    coach_briefing_enabled  BOOLEAN DEFAULT TRUE,  -- the coach writes a daily briefing
    theme                   VARCHAR DEFAULT 'dark',    -- 'dark', 'darker', 'abyss'
    exercise_abbreviations  VARCHAR DEFAULT '{}',      -- JSON: {"bp": "bench press", "ng": "neutral grip", ...}
    weekly_volume_target_kg INTEGER DEFAULT 20000,     -- strength tonnage goal per week
    lthr                    INTEGER,                   -- threshold heart rate, drives HR zones
    max_hr                  INTEGER,                   -- fallback reference when no threshold
    threshold_pace_sec_km   INTEGER,                   -- pace held at threshold, seconds per km
    lthr_measured_on        DATE,                      -- when Garmin measured that threshold
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

-- ============================================================
-- Garmin Health (daily HRV / sleep / body battery / readiness)
-- ============================================================

CREATE TABLE IF NOT EXISTS app.daily_metrics (
    user_id              INTEGER NOT NULL,
    date                 DATE NOT NULL,
    hrv_weekly_avg       INTEGER,
    hrv_last_night       INTEGER,
    hrv_status           VARCHAR,
    sleep_duration_sec   INTEGER,
    sleep_score          INTEGER,
    sleep_deep_sec       INTEGER,
    sleep_light_sec      INTEGER,
    sleep_rem_sec        INTEGER,
    sleep_awake_sec      INTEGER,
    body_battery_charged INTEGER,
    body_battery_drained INTEGER,
    body_battery_high    INTEGER,
    body_battery_low     INTEGER,
    resting_hr           INTEGER,
    stress_avg           INTEGER,
    stress_max           INTEGER,
    steps                INTEGER,
    intensity_minutes    INTEGER,
    readiness_score      INTEGER,
    source               VARCHAR DEFAULT 'garmin',
    fetched_at           TIMESTAMP DEFAULT now(),
    PRIMARY KEY (user_id, date)
);

-- ============================================================
-- Coach Briefings (the agent's daily word, written once a day)
-- ============================================================

CREATE SEQUENCE IF NOT EXISTS app.coach_briefings_seq START 1;

-- One row per produced briefing. Kept rather than recomputed: the agent run
-- costs a model call, and a failed run must stay visible instead of leaving
-- the dashboard silently empty.
CREATE TABLE IF NOT EXISTS app.coach_briefings (
    id           INTEGER PRIMARY KEY DEFAULT nextval('app.coach_briefings_seq'),
    user_id      INTEGER NOT NULL DEFAULT 1,
    date         DATE NOT NULL,
    text         VARCHAR NOT NULL,           -- the briefing itself, or the rule text
    priority     VARCHAR NOT NULL DEFAULT 'info',   -- 'info', 'warning', 'alert'
    source       VARCHAR NOT NULL DEFAULT 'rules',  -- 'agent', 'rules'
    status       VARCHAR NOT NULL DEFAULT 'ok',     -- 'ok', 'failed'
    error        VARCHAR,                    -- why the agent run failed, when it did
    trigger      VARCHAR NOT NULL DEFAULT 'api',    -- 'scheduler', 'api'
    created_at   TIMESTAMP DEFAULT now()
);
"""


def _columns(con, table: str) -> set[str]:
    return {row[0] for row in con.execute(f"DESCRIBE app.{table}").fetchall()}


def _m1_exercise_abbreviations(con) -> None:
    if "exercise_abbreviations" not in _columns(con, "user_settings"):
        con.execute(
            "ALTER TABLE app.user_settings ADD COLUMN exercise_abbreviations VARCHAR DEFAULT '{}'"
        )


def _m2_analytics_columns(con) -> None:
    wanted = {
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
    existing = _columns(con, "actual_sessions")
    for col_name, col_type in wanted.items():
        if col_name not in existing:
            con.execute(
                f"ALTER TABLE app.actual_sessions ADD COLUMN {col_name} {col_type}"
            )


def _m3_rename_strength_link(con) -> None:
    cols = _columns(con, "strength_sessions")
    if "garmin_activity_id" in cols and "actual_session_id" not in cols:
        con.execute(
            "ALTER TABLE app.strength_sessions RENAME COLUMN garmin_activity_id TO actual_session_id"
        )


# (version, migration). Append only; each migration must be idempotent because
# a fresh database already carries the latest DDL and gets every version recorded.
def _m4_strava_activity_id(con) -> None:
    if "strava_activity_id" not in _columns(con, "actual_sessions"):
        con.execute(
            "ALTER TABLE app.actual_sessions ADD COLUMN strava_activity_id VARCHAR"
        )


def _m5_weekly_volume_target(con) -> None:
    if "weekly_volume_target_kg" not in _columns(con, "user_settings"):
        con.execute(
            "ALTER TABLE app.user_settings ADD COLUMN weekly_volume_target_kg INTEGER DEFAULT 20000"
        )


def _m6_hr_reference(con) -> None:
    """The athlete's own thresholds: HR zones are computed from these."""
    columns = _columns(con, "user_settings")
    for name in ("lthr", "max_hr", "threshold_pace_sec_km"):
        if name not in columns:
            con.execute(f"ALTER TABLE app.user_settings ADD COLUMN {name} INTEGER")


def _m7_threshold_measured_on(con) -> None:
    """Date of the threshold Garmin reported, so a newer test wins."""
    if "lthr_measured_on" not in _columns(con, "user_settings"):
        con.execute("ALTER TABLE app.user_settings ADD COLUMN lthr_measured_on DATE")


def _m8_coach_briefing_enabled(con) -> None:
    """Its own switch, not ``notifications_enabled``.

    One flag meaning both "write me a briefing" and "send me a push" leaves no
    way to have one without the other the day push lands.
    """
    if "coach_briefing_enabled" not in _columns(con, "user_settings"):
        con.execute(
            "ALTER TABLE app.user_settings "
            "ADD COLUMN coach_briefing_enabled BOOLEAN DEFAULT TRUE"
        )


MIGRATIONS: list[tuple[int, Callable[[Any], None]]] = [
    (1, _m1_exercise_abbreviations),
    (2, _m2_analytics_columns),
    (3, _m3_rename_strength_link),
    (4, _m4_strava_activity_id),
    (5, _m5_weekly_volume_target),
    (6, _m6_hr_reference),
    (7, _m7_threshold_measured_on),
    (8, _m8_coach_briefing_enabled),
]


def _run_migrations(con) -> None:
    """Apply pending migrations and record them in app.schema_version."""
    row = con.execute(
        "SELECT COALESCE(MAX(version), 0) FROM app.schema_version"
    ).fetchone()
    current = int(row[0]) if row else 0
    for version, migrate in MIGRATIONS:
        if version <= current:
            continue
        migrate(con)
        con.execute("INSERT INTO app.schema_version (version) VALUES (?)", [version])
        logger.info("Schema migration %d applied", version)


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
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")
        raise
    finally:
        if con:
            con.close()


if __name__ == "__main__":
    main()
