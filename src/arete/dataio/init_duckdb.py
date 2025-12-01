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
