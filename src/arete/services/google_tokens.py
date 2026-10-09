"""The signed-in user's Google access token, for the Calendar integration.

With Google as the sign-in provider, Clerk keeps the OAuth refresh token and
hands out a fresh access token on demand: one consent at sign-in covers the
calendar, and nothing of Google's is stored in Arete's database. The scopes
asked for at sign-in are configured in the Clerk dashboard (Google: additional
OAuth scopes); ``has_scopes`` tells a feature whether the user granted them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from arete.config import config

GOOGLE_PROVIDER = "oauth_google"
CALENDAR_SCOPES = (
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.events.freebusy",
)


@dataclass(frozen=True)
class GoogleToken:
    token: str
    scopes: tuple[str, ...]
    expires_at: datetime | None

    def has_scopes(self, wanted: tuple[str, ...] = CALENDAR_SCOPES) -> bool:
        return all(scope in self.scopes for scope in wanted)


class GoogleTokenUnavailable(Exception):
    """No Google account on this user, or Clerk could not refresh its token."""


def google_access_token(clerk_user_id: str) -> GoogleToken:
    """A valid Google access token for the user; raises ``GoogleTokenUnavailable``."""
    if not config.clerk_secret_key:
        raise GoogleTokenUnavailable("Clerk n'est pas configuré.")
    from clerk_backend_api import Clerk

    try:
        with Clerk(bearer_auth=config.clerk_secret_key) as clerk:
            tokens = clerk.users.get_o_auth_access_token(
                user_id=clerk_user_id, provider=GOOGLE_PROVIDER
            )
    except Exception as e:  # noqa: BLE001 - the caller reports, not retries
        raise GoogleTokenUnavailable(f"Jeton Google indisponible : {e}") from e
    for item in tokens or []:
        token = getattr(item, "token", None)
        if not token:
            continue
        scopes = tuple(getattr(item, "scopes", None) or ())
        expires = getattr(item, "expires_at", None)
        expires_at = (
            datetime.fromtimestamp(expires)
            if isinstance(expires, int | float)
            else None
        )
        return GoogleToken(token=str(token), scopes=scopes, expires_at=expires_at)
    raise GoogleTokenUnavailable("Ce compte n'est pas connecté à Google.")
