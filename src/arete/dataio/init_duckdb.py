from arete.dataio.db import connect

DDL = """
CREATE SCHEMA IF NOT EXISTS app;

CREATE TABLE IF NOT EXISTS app.training_log (
    date          DATE,
    sport         VARCHAR,
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
    id              INTEGER,
    date            DATE NOT NULL,
    objective       VARCHAR,
    duration        INTEGER,
    fatigue         INTEGER,
    rpe_avg7d       DOUBLE
);

CREATE TABLE IF NOT EXISTS app.users (
    id                     INTEGER,
    sex                    VARCHAR,
    age                    INTEGER,
    height                 DOUBLE,
    weight                 DOUBLE,
    desired_training_load  DOUBLE
);

CREATE TABLE IF NOT EXISTS app.objectives (
    id        INTEGER,
    sport     VARCHAR,
    name      VARCHAR,
    priority  INTEGER
);

CREATE TABLE IF NOT EXISTS app.personal_records (
    id           INTEGER,
    sport        VARCHAR,
    event        VARCHAR,
    performance  DOUBLE,
    unit         VARCHAR
);
"""


def main():
    con = connect(False)
    for stmt in DDL.strip().split(";"):
        s = stmt.strip()
        if s:
            con.execute(s + ";")
    tables = con.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema='app'"
    ).fetchall()
    print("Tables:", tables)


if __name__ == "__main__":
    main()
