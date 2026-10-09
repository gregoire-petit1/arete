"""The signed-in user's Google access token, for the Calendar integration.

With Google as the sign-in provider, Clerk keeps the OAuth refresh token and
hands out a fresh access token on demand: nothing of Google's is stored in
Arete's database. Sign-in asks for basic scopes only; a feature asks for more
from the browser (Clerk's ``reauthorize``), and ``has_scopes`` tells it whether
the user granted them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from arete.config import config

GOOGLE_PROVIDER = "oauth_google"
#: Clerk answers in well under a second; a hung call must not hold a request.
CLERK_TIMEOUT_MS = 10_000


@dataclass(frozen=True)
class GoogleToken:
    token: str
    scopes: tuple[str, ...]
    expires_at: datetime | None

    def has_scopes(self, wanted: tuple[str, ...]) -> bool:
        return all(scope in self.scopes for scope in wanted)


class GoogleTokenUnavailable(Exception):
    """No Google account on this user, or Clerk could not refresh its token."""


def google_access_token(clerk_user_id: str) -> GoogleToken:
    """A valid Google access token for the user; raises ``GoogleTokenUnavailable``."""
    if not config.clerk_secret_key:
        raise GoogleTokenUnavailable("Clerk n'est pas configuré.")
    from clerk_backend_api import Clerk

    try:
        with Clerk(
            bearer_auth=config.clerk_secret_key, timeout_ms=CLERK_TIMEOUT_MS
        ) as clerk:
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
