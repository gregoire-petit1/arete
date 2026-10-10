"""Login accounts, retained contact details and private athlete provisioning."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from arete.config import config
from arete.dataio.db import connect

OWNER_ATHLETE_ID = 1
_COLUMNS = "id, clerk_user_id, email, name, athlete_id, email_verified_at, profile_synced_at, deleted_at"


@dataclass(frozen=True)
class AppUser:
    id: int
    clerk_user_id: str
    email: str
    name: str | None
    athlete_id: int | None
    email_verified_at: datetime | None = None
    profile_synced_at: datetime | None = None
    deleted_at: datetime | None = None

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
    con = connect()
    try:
        row = con.execute(
            "SELECT email FROM app.user_settings WHERE user_id = 1"
        ).fetchone()
    finally:
        con.close()
    value = str(row[0] or "").strip().lower() if row else ""
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


def upsert_user(
    clerk_user_id: str, email: str, name: str | None = None, *, verified: bool = False
) -> AppUser:
    """Atomically provision a private athlete; never infer ownership from unverified mail."""
    email = email.strip().lower()
    now = datetime.now()
    legacy_owner = verified and email in owner_emails()
    con = connect()
    try:
        con.execute("BEGIN TRANSACTION")
        con.execute(
            "INSERT INTO app.users (clerk_user_id,email,name,email_verified_at,profile_synced_at) "
            "VALUES (?,?,?,?,?) ON CONFLICT (clerk_user_id) DO UPDATE SET "
            "email=EXCLUDED.email,name=coalesce(EXCLUDED.name,app.users.name), "
            "email_verified_at=EXCLUDED.email_verified_at,profile_synced_at=EXCLUDED.profile_synced_at, "
            "last_seen_at=EXCLUDED.profile_synced_at",
            [clerk_user_id, email, name, now if verified else None, now],
        )
        row = con.execute(
            f"SELECT {_COLUMNS} FROM app.users WHERE clerk_user_id=?", [clerk_user_id]
        ).fetchone()
        assert row is not None
        user = _from_row(row)
        if user.athlete_id is None and user.deleted_at is None:
            athlete_id = OWNER_ATHLETE_ID
            if not legacy_owner:
                created = con.execute(
                    "INSERT INTO app.athletes(id) VALUES(nextval('app.athletes_seq')) RETURNING id"
                ).fetchone()
                assert created is not None
                athlete_id = int(created[0])
            con.execute(
                "UPDATE app.users SET athlete_id=? WHERE clerk_user_id=?",
                [athlete_id, clerk_user_id],
            )
            # Fresh accounts start empty; only defaults are shared with the
            # original athlete, never their preferences, files or credentials.
            con.execute(
                "INSERT INTO app.user_settings(user_id,display_name,email) VALUES(?,?,?) ON CONFLICT DO NOTHING",
                [athlete_id, name or "Athlète", email],
            )
            for statement in (
                "INSERT INTO app.game_profile(id,athlete_id) VALUES(1,?) ON CONFLICT DO NOTHING",
                "INSERT INTO app.game_owned(skin,athlete_id) VALUES('base',?) ON CONFLICT DO NOTHING",
                "INSERT INTO app.document_quota(id,used_bytes,athlete_id) VALUES(1,0,?) ON CONFLICT DO NOTHING",
            ):
                con.execute(statement, [athlete_id])
        row = con.execute(
            f"SELECT {_COLUMNS} FROM app.users WHERE clerk_user_id=?", [clerk_user_id]
        ).fetchone()
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()
    assert row is not None
    return _from_row(row)


def athlete_is_active(athlete_id: int) -> bool:
    con = connect()
    try:
        return (
            con.execute(
                "SELECT 1 FROM app.athletes WHERE id=? AND deleted_at IS NULL",
                [athlete_id],
            ).fetchone()
            is not None
        )
    finally:
        con.close()


def list_users() -> list[AppUser]:
    con = connect()
    try:
        rows = con.execute(f"SELECT {_COLUMNS} FROM app.users ORDER BY id").fetchall()
    finally:
        con.close()
    return [_from_row(r) for r in rows]


def deactivate_current_athlete() -> None:
    """Revoke every login mapped to this athlete without losing contact/history."""
    from arete.services.athlete_scope import current_athlete_id

    con = connect()
    try:
        con.execute("BEGIN TRANSACTION")
        con.execute(
            "UPDATE app.athletes SET deleted_at=current_timestamp WHERE id=? AND deleted_at IS NULL",
            [current_athlete_id()],
        )
        con.execute(
            "UPDATE app.users SET deleted_at=current_timestamp WHERE athlete_id=? AND deleted_at IS NULL",
            [current_athlete_id()],
        )
        con.execute("COMMIT")
    except BaseException:
        con.execute("ROLLBACK")
        raise
    finally:
        con.close()
