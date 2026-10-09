"""Durable connection preferences and one-shot actions, never chat history."""

import json
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta

import duckdb

from arete.dataio.db import db_connection
from arete.services.calendar_models import (
    ACTION_TTL_SECONDS,
    MAX_ACTION_CHARS,
    MAX_PENDING_ACTIONS,
    CalendarError,
)

CALENDAR_DDL = """
CREATE TABLE IF NOT EXISTS app.calendar_connections (
    connection_key VARCHAR PRIMARY KEY, enabled BOOLEAN NOT NULL DEFAULT FALSE,
    revision BIGINT NOT NULL DEFAULT 0, selection VARCHAR NOT NULL DEFAULT '{"readable":[],"writable":[]}',
    consent_hash VARCHAR, consent_expires DOUBLE
);
CREATE TABLE IF NOT EXISTS app.calendar_actions (
    id VARCHAR PRIMARY KEY, connection_key VARCHAR NOT NULL,
    revision BIGINT NOT NULL, thread_id VARCHAR NOT NULL,
    payload VARCHAR NOT NULL, status VARCHAR NOT NULL,
    expires DOUBLE NOT NULL, updated DOUBLE NOT NULL,
    result VARCHAR NOT NULL DEFAULT '{}'
);
"""


def now() -> float:
    return datetime.now(UTC).timestamp()


class CalendarRepository:
    def __init__(self, key: str):
        self.key = key

    @contextmanager
    def transaction(self):
        try:
            with db_connection() as con:
                con.execute("BEGIN TRANSACTION")
                try:
                    con.execute(
                        "INSERT INTO app.calendar_connections (connection_key) VALUES (?) ON CONFLICT DO NOTHING",
                        [self.key],
                    )
                    # Serialize decisions/settings across workers through an MVCC row write.
                    con.execute(
                        "UPDATE app.calendar_connections SET revision = revision WHERE connection_key = ?",
                        [self.key],
                    )
                    yield con
                    con.execute("COMMIT")
                except BaseException:
                    con.execute("ROLLBACK")
                    raise
        except duckdb.TransactionException as exc:
            raise CalendarError(
                "Une autre opération Calendar est en cours. Actualise son état.", 409
            ) from exc

    def state(self) -> dict:
        with db_connection() as con:
            row = con.execute(
                "SELECT enabled, revision, selection FROM app.calendar_connections WHERE connection_key = ?",
                [self.key],
            ).fetchone()
        return {
            "enabled": bool(row and row[0]),
            "revision": row[1] if row else 0,
            "selection": json.loads(row[2])
            if row
            else {"readable": [], "writable": []},
        }

    def configure(
        self, *, enabled: bool, selection: dict, expected_revision: int | None = None
    ) -> None:
        with self.transaction() as con:
            if expected_revision is not None:
                row = con.execute(
                    "SELECT revision FROM app.calendar_connections WHERE connection_key = ?",
                    [self.key],
                ).fetchone()
                if row[0] != expected_revision:
                    raise CalendarError(
                        "Connexion modifiée pendant l’opération. Recommence.", 409
                    )
            con.execute(
                "UPDATE app.calendar_connections SET enabled = ?, selection = ?, revision = revision + 1, consent_hash = NULL, consent_expires = NULL WHERE connection_key = ?",
                [enabled, json.dumps(selection), self.key],
            )
            con.execute(
                "UPDATE app.calendar_actions SET status = 'invalidated', updated = ? WHERE connection_key = ? AND status = 'pending'",
                [now(), self.key],
            )

    def add(self, action_id: str, revision: int, thread_id: str, payload: dict) -> None:
        if len(json.dumps(payload, ensure_ascii=False)) > MAX_ACTION_CHARS:
            raise CalendarError(
                "Événement trop volumineux pour une validation complète.", 413
            )
        with self.transaction() as con:
            state = con.execute(
                "SELECT enabled, revision FROM app.calendar_connections WHERE connection_key = ?",
                [self.key],
            ).fetchone()
            if not state or not state[0] or state[1] != revision:
                raise CalendarError(
                    "Connexion ou permissions modifiées. Recommence la proposition.",
                    409,
                )
            count = con.execute(
                "SELECT COUNT(*) FROM app.calendar_actions WHERE connection_key = ? AND status = 'pending' AND expires > ?",
                [self.key, now()],
            ).fetchone()[0]
            if count >= MAX_PENDING_ACTIONS:
                raise CalendarError("Trop de propositions Calendar en attente.", 429)
            # Keep a bounded time horizon for sensitive event snapshots.
            con.execute(
                "DELETE FROM app.calendar_actions WHERE connection_key = ? AND updated < ?",
                [self.key, now() - timedelta(days=30).total_seconds()],
            )
            con.execute(
                "INSERT INTO app.calendar_actions (id, connection_key, revision, thread_id, payload, status, expires, updated) VALUES (?, ?, ?, ?, ?, 'pending', ?, ?)",
                [
                    action_id,
                    self.key,
                    revision,
                    thread_id,
                    json.dumps(payload),
                    now() + ACTION_TTL_SECONDS,
                    now(),
                ],
            )

    def get(self, action_id: str) -> dict:
        with db_connection() as con:
            row = con.execute(
                "SELECT id, thread_id, payload, status, expires, updated, result, revision FROM app.calendar_actions WHERE id = ? AND connection_key = ?",
                [action_id, self.key],
            ).fetchone()
        if row is None:
            raise CalendarError("Proposition introuvable.", 404)
        status = row[3]
        if status == "pending" and row[4] <= now():
            status = "expired"
        if status == "executing" and row[5] + 60 <= now():
            status = "uncertain"
        return {
            "id": row[0],
            "thread_id": row[1],
            **json.loads(row[2]),
            "status": status,
            "expires_at": datetime.fromtimestamp(row[4], UTC).isoformat(),
            "result": json.loads(row[6]),
            "revision": row[7],
        }

    def claim(self, action_id: str, decision: str) -> bool:
        with self.transaction() as con:
            row = con.execute(
                """UPDATE app.calendar_actions SET status = ?, updated = ?
                WHERE id = ? AND connection_key = ? AND status = 'pending' AND expires > ?
                AND revision = (SELECT revision FROM app.calendar_connections WHERE connection_key = ? AND enabled)
                RETURNING id""",
                [
                    "executing" if decision == "approve" else "rejected",
                    now(),
                    action_id,
                    self.key,
                    now(),
                    self.key,
                ],
            ).fetchone()
        return row is not None

    def finish(self, action_id: str, status: str, result: dict) -> None:
        with db_connection() as con:
            con.execute(
                "UPDATE app.calendar_actions SET status = ?, result = ?, updated = ? WHERE id = ? AND connection_key = ? AND status IN ('executing', 'uncertain')",
                [status, json.dumps(result), now(), action_id, self.key],
            )
