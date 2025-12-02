import logging

from arete.dataio.db import connect

logger = logging.getLogger(__name__)

# Note: DuckDB 1.x has limited support for PRIMARY KEY and FOREIGN KEY constraints.
# IDs are managed application-side via COALESCE(MAX(id),0)+1 in repository.py.
# NOT NULL constraints are added where data integrity is critical.

DDL = """
CREATE SCHEMA IF NOT EXISTS app;

CREATE TABLE IF NOT EXISTS app.training_log (
    date          DATE NOT NULL,
    sport         VARCHAR NOT NULL,
    type          VARCHAR,
    duree_min     INTEGER,
    distance_km   DOUBLE,
    allure_minkm  DOUBLE,
    avg_hr        INTEGER,
    rpe           DOUBLE,
    sommeil_h     DOUBLE,
    hrv           DOUBLE,
    poids_kg      DOUBLE,
    denivele_m    INTEGER,
    terrain       VARCHAR,
    douleurs      VARCHAR,
    stress        INTEGER,
    notes         VARCHAR,
    course_date   DATE,
    course_type   VARCHAR,
    objectif_tps  VARCHAR
);

CREATE TABLE IF NOT EXISTS app.sessions (
    id              INTEGER NOT NULL,
    date            DATE NOT NULL,
    objective       VARCHAR NOT NULL,
    duration        INTEGER NOT NULL,
    fatigue         INTEGER NOT NULL,
    rpe_avg7d       DOUBLE
);

CREATE TABLE IF NOT EXISTS app.users (
    id                     INTEGER NOT NULL,
    sex                    VARCHAR NOT NULL,
    age                    INTEGER NOT NULL,
    height                 DOUBLE NOT NULL,
    weight                 DOUBLE NOT NULL,
    desired_training_load  DOUBLE
);

CREATE TABLE IF NOT EXISTS app.objectives (
    id        INTEGER NOT NULL,
    sport     VARCHAR NOT NULL,
    name      VARCHAR NOT NULL,
    priority  INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS app.personal_records (
    id           INTEGER NOT NULL,
    sport        VARCHAR NOT NULL,
    event        VARCHAR NOT NULL,
    performance  DOUBLE NOT NULL,
    unit         VARCHAR NOT NULL
);

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
    
    -- Computed adherence (filled by matching logic)
    adherence_score     DOUBLE,                -- 0-100: how well it matched the plan
    intensity_deviation DOUBLE,                -- % deviation from planned intensity
    
    -- Timestamps
    start_time          TIMESTAMP,
    created_at          TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
"""


def main():
    """Initialize the DuckDB database with the required schema."""
    con = None
    try:
        con = connect(False)
        for stmt in DDL.strip().split(";"):
            s = stmt.strip()
            if s:
                con.execute(s + ";")
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
