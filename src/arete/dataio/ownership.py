"""Validate links against live, athlete-scoped relations before domain writes."""

from __future__ import annotations

import duckdb

from arete.dataio.tenant_schema import PRIVATE_TABLES


class OwnershipError(ValueError):
    """A missing or inaccessible parent; deliberately indistinguishable."""


def require_owned(
    con: duckdb.DuckDBPyConnection, table: str, identifier: int | str | None
) -> None:
    if identifier is None:
        return
    assert table in PRIVATE_TABLES
    key = "connection_key" if table == "calendar_connections" else "id"
    row = con.execute(
        f"SELECT 1 FROM app.visible_{table} WHERE {key}=?", [identifier]
    ).fetchone()
    if row is None:
        raise OwnershipError("Objet introuvable ou inaccessible pour cet athlète.")
