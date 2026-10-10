"""Read remote Garmin credentials from their source of truth on each request.

The general file mirror caches a worker's local files. Credentials need stronger
freshness: another worker may have disconnected or reconnected this athlete.
"""

from __future__ import annotations

from pathlib import Path

from arete.dataio.db import db_connection

TOKEN_PATH = "garmin_tokens/garmin_tokens.json"
MAX_TOKEN_BYTES = 64 * 1024


def hydrate(path: Path) -> bool:
    with db_connection() as con:
        row = con.execute(
            "SELECT content FROM app.visible_files WHERE path=?", [TOKEN_PATH]
        ).fetchone()
    if row is None:
        path.unlink(missing_ok=True)
        return False
    data = bytes(row[0])
    assert len(data) <= MAX_TOKEN_BYTES
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    path.chmod(0o600)
    return True


def save(path: Path) -> None:
    data = path.read_bytes()
    assert len(data) <= MAX_TOKEN_BYTES
    with db_connection() as con:
        con.execute(
            "INSERT OR REPLACE INTO app.files(path,content,updated_at) VALUES(?,?,now())",
            [TOKEN_PATH, data],
        )


def delete() -> None:
    with db_connection() as con:
        con.execute(
            "DELETE FROM app.files WHERE athlete_id=getvariable('arete_athlete_id') AND path=?",
            [TOKEN_PATH],
        )
