"""Signed-in accounts (``app.users``) and which one is the athlete.

Arete's data belongs to one athlete, ``user_id = 1`` everywhere. Sign-up is
open, so an account gets that athlete only when its e-mail is one of the
owner's (``ARETE_OWNER_EMAIL``, comma-separated for someone with several
Google accounts, else the e-mail in Settings); every other account is
recorded and waits with no data access. Attaching more athletes is the
multi-athlete work, not this module's.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from arete.config import config
from arete.dataio.db import connect
from arete.dataio.settings import get_user_settings

OWNER_ATHLETE_ID = 1
_COLUMNS = "id, clerk_user_id, email, name, athlete_id"


@dataclass(frozen=True)
class AppUser:
    id: int
    clerk_user_id: str
    email: str
    name: str | None
    athlete_id: int | None

    @property
    def is_owner(self) -> bool:
        return self.athlete_id == OWNER_ATHLETE_ID

    def to_dict(self) -> dict:
        return {
            "email": self.email,
            "name": self.name,
            "athlete_id": self.athlete_id,
            "is_owner": self.is_owner,
        }


#: What scripts and the MCP server act as, with the API key: the athlete.
API_KEY_USER = AppUser(
    id=0, clerk_user_id="api-key", email="", name="API key", athlete_id=OWNER_ATHLETE_ID
)


def owner_emails() -> frozenset[str]:
    """The addresses that are the athlete: the environment first, then Settings."""
    if config.owner_emails:
        return frozenset(config.owner_emails)
    settings = get_user_settings(user_id=OWNER_ATHLETE_ID) or {}
    value = (settings.get("email") or "").strip().lower()
    return frozenset({value}) if value else frozenset()


def _from_row(row: tuple) -> AppUser:
    return AppUser(*row)


def get_user(clerk_user_id: str) -> AppUser | None:
    con = connect()
    try:
        row = con.execute(
            f"SELECT {_COLUMNS} FROM app.users WHERE clerk_user_id = ?", [clerk_user_id]
        ).fetchone()
    finally:
        con.close()
    return _from_row(row) if row else None


def upsert_user(clerk_user_id: str, email: str, name: str | None = None) -> AppUser:
    """Record a sign-in; an owner address gets the athlete."""
    email = email.strip().lower()
    con = connect()
    try:
        con.execute(
            "INSERT INTO app.users (clerk_user_id, email, name) VALUES (?, ?, ?) "
            "ON CONFLICT (clerk_user_id) DO UPDATE SET email = EXCLUDED.email, "
            "name = COALESCE(EXCLUDED.name, app.users.name), last_seen_at = ?",
            [clerk_user_id, email, name, datetime.now()],
        )
        if email in owner_emails():
            con.execute(
                "UPDATE app.users SET athlete_id = ? WHERE clerk_user_id = ? "
                "AND athlete_id IS NULL",
                [OWNER_ATHLETE_ID, clerk_user_id],
            )
        row = con.execute(
            f"SELECT {_COLUMNS} FROM app.users WHERE clerk_user_id = ?", [clerk_user_id]
        ).fetchone()
    finally:
        con.close()
    assert row is not None
    return _from_row(row)


def list_users() -> list[AppUser]:
    con = connect()
    try:
        rows = con.execute(f"SELECT {_COLUMNS} FROM app.users ORDER BY id").fetchall()
    finally:
        con.close()
    return [_from_row(r) for r in rows]
