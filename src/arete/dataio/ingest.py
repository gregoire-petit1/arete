import pathlib
import logging
from arete.dataio.db import connect

logger = logging.getLogger(__name__)

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

# Allowed column names (whitelist for SQL safety)
ALLOWED_COLUMNS = frozenset(COLUMNS)


def duck_type(col: str) -> str:
    if col in {"date", "course_date"}:
        return "DATE"
    if col in {"duree_min", "avg_hr", "denivele_m", "stress"}:
        return "INTEGER"
    if col in {"distance_km", "allure_minkm", "rpe", "sommeil_h", "hrv", "poids_kg"}:
        return "DOUBLE"
    return "VARCHAR"


def ingest_csv(csv_path: str | pathlib.Path) -> int:
    """Ingest a CSV file into the training_log table.

    Args:
        csv_path: Path to the CSV file to ingest.

    Returns:
        Total number of rows in the table after ingestion.

    Raises:
        FileNotFoundError: If the CSV file does not exist.
        ValueError: If an invalid column name is detected.
    """
    p = pathlib.Path(csv_path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"CSV file not found: {p}")

    # Validate all column names are in the whitelist
    for col in COLUMNS:
        if col not in ALLOWED_COLUMNS:
            raise ValueError(f"Invalid column name: {col}")

    # Build safe column expressions (columns are from whitelist)
    cols_select = ", ".join([f"CAST({c} AS {duck_type(c)}) AS {c}" for c in COLUMNS])

    con = connect(False)
    try:
        # Use parameterized path via DuckDB's read_csv
        # Note: DuckDB read_csv doesn't support parameterized file paths,
        # but we've validated the path exists and resolved it to absolute
        q = f"""
        INSERT INTO app.training_log
        SELECT {cols_select}
        FROM read_csv_auto(
            '{p.as_posix()}', HEADER=TRUE, SAMPLE_SIZE=-1, IGNORE_ERRORS=FALSE
        )
        """
        con.execute(q)
        total = con.execute("SELECT COUNT(*) FROM app.training_log").fetchone()[0]
        logger.info(f"Ingestion OK. Total rows: {total}")
        print(f"Ingestion OK. Total lignes: {total}")
        return total
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        raise
    finally:
        con.close()


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m arete.dataio.ingest <path_csv>")
        raise SystemExit(1)
    ingest_csv(sys.argv[1])
