"""Durable facts about the athlete: few, dated, editable, given to every call.

The free-text ``notes.md`` grew by appending and was injected by its tail, so
the oldest facts (an injury, a constraint) were the first to fall out of the
prompt. These are rows instead: the coach records or closes one with a tool,
the athlete edits them in Settings, and every active fact reaches the model.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from arete.dataio.db import connect

KINDS = ("injury", "constraint", "preference", "goal", "other")
STATUSES = ("active", "resolved")
KIND_FR = {
    "injury": "blessure",
    "constraint": "contrainte",
    "preference": "préférence",
    "goal": "objectif",
    "other": "autre",
}
MAX_TEXT = 300
MAX_ACTIVE = 30  # past it, the oldest stay stored but leave the prompt
_COLUMNS = "id, kind, text, since, status, source, created_at, updated_at"


@dataclass(frozen=True)
class Fact:
    id: int
    kind: str
    text: str
    since: date
    status: str
    source: str
    created_at: datetime | None
    updated_at: datetime | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind,
            "text": self.text,
            "since": self.since.isoformat(),
            "status": self.status,
            "source": self.source,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }


def _validate(kind: str | None, text: str | None, status: str | None) -> None:
    if kind is not None and kind not in KINDS:
        raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    if status is not None and status not in STATUSES:
        raise ValueError("status must be active or resolved")
    if text is not None and not 1 <= len(text.strip()) <= MAX_TEXT:
        raise ValueError(f"text must be 1 to {MAX_TEXT} characters")


def list_facts(*, active_only: bool = False) -> list[Fact]:
    con = connect()
    try:
        where = "AND status = 'active'" if active_only else ""
        rows = con.execute(
            f"SELECT {_COLUMNS} FROM app.athlete_facts WHERE user_id = 1 {where} "
            "ORDER BY status, since DESC, id DESC"
        ).fetchall()
    finally:
        con.close()
    return [Fact(*r) for r in rows]


def get_fact(fact_id: int) -> Fact | None:
    con = connect()
    try:
        row = con.execute(
            f"SELECT {_COLUMNS} FROM app.athlete_facts WHERE id = ?", [fact_id]
        ).fetchone()
    finally:
        con.close()
    return Fact(*row) if row else None


def add_fact(
    kind: str, text: str, *, since: date | None = None, source: str = "coach"
) -> Fact:
    _validate(kind, text, None)
    con = connect()
    try:
        row = con.execute(
            "INSERT INTO app.athlete_facts (kind, text, since, source) VALUES (?, ?, ?, ?) "
            f"RETURNING {_COLUMNS}",
            [kind, text.strip(), since or date.today(), source],
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    return Fact(*row)


def update_fact(
    fact_id: int,
    *,
    kind: str | None = None,
    text: str | None = None,
    status: str | None = None,
    since: date | None = None,
) -> Fact | None:
    _validate(kind, text, status)
    fields = {
        k: v
        for k, v in (
            ("kind", kind),
            ("text", text.strip() if text else None),
            ("status", status),
            ("since", since),
        )
        if v is not None
    }
    if fields:
        con = connect()
        try:
            con.execute(
                f"UPDATE app.athlete_facts SET {', '.join(f'{k} = ?' for k in fields)}, "
                "updated_at = now() WHERE id = ?",
                [*fields.values(), fact_id],
            )
        finally:
            con.close()
    return get_fact(fact_id)


def delete_fact(fact_id: int) -> bool:
    con = connect()
    try:
        row = con.execute(
            "DELETE FROM app.athlete_facts WHERE id = ? RETURNING id", [fact_id]
        ).fetchone()
    finally:
        con.close()
    return row is not None


def facts_block() -> str:
    """The active facts, for the prompt; empty when there are none."""
    try:
        facts = list_facts(active_only=True)[:MAX_ACTIVE]
    except Exception:  # noqa: BLE001 - a missing table must not break a call
        return ""
    if not facts:
        return ""
    lines = [
        f"- #{f.id} [{KIND_FR[f.kind]}, depuis le {f.since.isoformat()}] {f.text}"
        for f in facts
    ]
    return (
        "Faits durables sur l'athlète (actifs, l'athlète peut les corriger) :\n"
        + "\n".join(lines)
    )
