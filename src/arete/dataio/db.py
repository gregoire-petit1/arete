"""DuckDB connection helpers."""

from __future__ import annotations

import pathlib
from collections.abc import Iterator
from contextlib import contextmanager

import duckdb

from arete.config import config


def get_db_path() -> pathlib.Path:
    return config.db_path


def connect(read_only: bool = False) -> duckdb.DuckDBPyConnection:
    db_path = get_db_path()
    if not read_only:
        db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path), read_only=read_only)
    con.execute("PRAGMA threads=4;")
    con.execute(f"PRAGMA temp_directory='{db_path.parent}';")
    return con


@contextmanager
def db_connection(read_only: bool = False) -> Iterator[duckdb.DuckDBPyConnection]:
    """Always close; default to the same mode as concurrent API writers.

    DuckDB rejects overlapping connections with different read_only settings,
    even when the read-only caller only executes SELECT statements.
    """
    con = connect(read_only=read_only)
    try:
        yield con
    finally:
        con.close()
