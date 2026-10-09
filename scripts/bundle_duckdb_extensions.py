"""Download the MotherDuck extension at build time, into ``duckdb_extensions/``.

Usage (Vercel and Docker builds run it; locally it is optional):
    uv run python scripts/bundle_duckdb_extensions.py

A fresh instance would otherwise download it (~55 MB, 3-7 s) on its first
connection. ``LOAD`` fetches the implementation library too. The files are
for the platform this runs on, so run it where the API will run.
"""

from __future__ import annotations

from pathlib import Path

import duckdb

TARGET = Path(__file__).resolve().parent.parent / "duckdb_extensions"


def main() -> None:
    con = duckdb.connect()
    con.execute(f"SET extension_directory='{TARGET}'")
    con.execute("INSTALL motherduck")
    con.execute("LOAD motherduck")
    platform = con.execute("PRAGMA platform").fetchone()
    version = con.execute("PRAGMA version").fetchone()
    print(
        f"DuckDB {version[0] if version else '?'} on {platform[0] if platform else '?'}"
    )
    for path in sorted(TARGET.rglob("*")):
        if path.is_file():
            print(f"{path.relative_to(TARGET)}  {path.stat().st_size / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
