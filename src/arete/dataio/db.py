import os
import pathlib

import duckdb
from dotenv import load_dotenv

load_dotenv()
DEFAULT_DB_PATH = pathlib.Path("data/arete.duckdb")


def get_db_path() -> pathlib.Path:
    env_path = os.getenv("ARETE_DB")
    return pathlib.Path(env_path) if env_path else DEFAULT_DB_PATH


def connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    db_path = get_db_path()
    if not read_only:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path), read_only=read_only)
    con.execute("PRAGMA threads=4;")
    con.execute(f"PRAGMA temp_directory='{db_path.parent}';")
    return con
