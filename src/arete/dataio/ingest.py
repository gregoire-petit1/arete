import pathlib
from arete.dataio.db import connect

COLUMNS = [
    "date",
    "sport",
    "type",
    "duree_min",
    "distance_km",
    "allure_minkm",
    "avg_hr",
    "rpe",
    "sommeil_h",
    "hrv",
    "poids_kg",
    "denivele_m",
    "terrain",
    "douleurs",
    "stress",
    "notes",
    "course_date",
    "course_type",
    "objectif_tps",
]


def duck_type(col: str) -> str:
    if col in {"date", "course_date"}:
        return "DATE"
    if col in {"duree_min", "avg_hr", "denivele_m", "stress"}:
        return "INTEGER"
    if col in {"distance_km", "allure_minkm", "rpe", "sommeil_h", "hrv", "poids_kg"}:
        return "DOUBLE"
    return "VARCHAR"


def ingest_csv(csv_path: str | pathlib.Path) -> int:
    p = pathlib.Path(csv_path)
    if not p.exists():
        raise FileNotFoundError(p)
    con = connect(False)
    cols_select = ", ".join([f"TRY_CAST({c} AS {duck_type(c)}) AS {c}" for c in COLUMNS])
    q = f"""
    INSERT INTO app.training_log
    SELECT {cols_select}
    FROM read_csv_auto('{p.as_posix()}', HEADER=TRUE, SAMPLE_SIZE=-1)
    """
    con.execute(q)
    total = con.execute("SELECT COUNT(*) FROM app.training_log").fetchone()[0]
    print(f"Ingestion OK. Total lignes: {total}")
    return total


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m arete.dataio.ingest <path_csv>")
        raise SystemExit(1)
    ingest_csv(sys.argv[1])
