"""Identity at the HTTP boundary: who is calling, and whether they may.

Off by default (``ARETE_AUTH`` unset): the API is as open as a self-hosted
instance behind its own network. With ``ARETE_AUTH=clerk`` every request
except the public paths needs a Clerk session token (``Authorization:
Bearer``), or the long-lived ``ARETE_API_KEY`` that scripts and the MCP
server use. The account is recorded in ``app.users``; only the owner's e-mail
is attached to the athlete, every other account is refused the data (403)
until the multi-athlete work attaches it to its own.

Pure ASGI middleware, like the mirror's: the coach streams, and a
``BaseHTTPMiddleware`` would sit between the stream and the client. The Clerk
SDK is imported inside the verification so a cold boot does not pay for it.
"""

from __future__ import annotations

import hmac
import logging
from typing import Any

import anyio
from fastapi import APIRouter, HTTPException, Request
from starlette.datastructures import Headers
from starlette.responses import JSONResponse

from arete.config import config
from arete.services import users as user_service
from arete.services.users import API_KEY_USER, OWNER_ATHLETE_ID, AppUser

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/auth", tags=["auth"])

#: Reachable without a credential: the health probe, what the browser needs
#: before signing in, OAuth callbacks (their own state), the cron (its own
#: secret) and the API schema (no data in it).
PUBLIC_PATHS = frozenset(
    {
        "/health",
        "/auth/config",
        "/strava/callback",
        "/google-calendar/callback",
        "/cron/daily-sync",
        "/openapi.json",
    }
)
PUBLIC_PREFIXES = ("/docs", "/redoc")
#: Where a signed-in account goes before it has an athlete.
ACCOUNT_PATHS = frozenset({"/auth/me"})

NO_ATHLETE_DETAIL = (
    "Aucun athlète n'est associé à ce compte. Demande l'accès au propriétaire "
    "de cette instance."
)


class AuthError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def auth_enabled() -> bool:
    return config.auth_provider == "clerk"


def auth_misconfigured() -> str | None:
    """Why the enforced mode cannot work; None when it can (or is off)."""
    if not auth_enabled():
        return None
    if not config.clerk_secret_key:
        return "CLERK_SECRET_KEY manquante"
    if not config.clerk_publishable_key:
        return "clé publique Clerk manquante"
    return None


def is_public(path: str) -> bool:
    if path.startswith("/api/"):  # the deployment keeps the prefix in front
        path = path[4:]
    return path in PUBLIC_PATHS or path.startswith(PUBLIC_PREFIXES)


def is_account_path(path: str) -> bool:
    if path.startswith("/api/"):
        path = path[4:]
    return path in ACCOUNT_PATHS


# ---------------------------------------------------------------- Clerk --
def _verify_session_token(token: str) -> dict[str, Any]:
    """Clerk session JWT → claims (signature, expiry, optional ``azp``)."""
    from clerk_backend_api.security import (
        TokenVerificationError,
        VerifyTokenOptions,
        verify_token,
    )

    options = VerifyTokenOptions(
        secret_key=config.clerk_secret_key,
        authorized_parties=list(config.auth_origins) or None,
    )
    try:
        return verify_token(token, options)
    except TokenVerificationError as e:
        raise AuthError(401, "Session invalide ou expirée.") from e


def _fetch_clerk_profile(clerk_user_id: str) -> tuple[str, str | None]:
    """(primary e-mail, display name) of a Clerk user, once per new account."""
    from clerk_backend_api import Clerk

    with Clerk(bearer_auth=config.clerk_secret_key) as clerk:
        user = clerk.users.get(user_id=clerk_user_id)
    addresses = {
        getattr(a, "id", None): getattr(a, "email_address", None)
        for a in (getattr(user, "email_addresses", None) or [])
    }
    email = addresses.get(getattr(user, "primary_email_address_id", None)) or next(
        (a for a in addresses.values() if a), None
    )
    if not email:
        raise AuthError(403, "Ce compte n'a pas d'adresse e-mail.")
    parts = (getattr(user, "first_name", None), getattr(user, "last_name", None))
    name = " ".join(p for p in parts if p) or None
    return str(email), name


def resolve_user(authorization: str | None) -> AppUser:
    """The account behind a bearer credential; raises ``AuthError``."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise AuthError(401, "Connexion requise.")
    token = authorization[7:].strip()
    if not token:
        raise AuthError(401, "Connexion requise.")
    key = config.api_key
    if key and hmac.compare_digest(token, key):
        return API_KEY_USER
    claims = _verify_session_token(token)
    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise AuthError(401, "Session invalide ou expirée.")
    user = user_service.get_user(subject)
    if user is None:
        email, name = _fetch_clerk_profile(subject)
        user = user_service.upsert_user(subject, email, name)
    elif user.athlete_id is None:
        # The owner's e-mail may have been configured since the first sign-in.
        user = user_service.upsert_user(subject, user.email, user.name)
    return user


# ----------------------------------------------------------- middleware --
class AuthMiddleware:
    """Refuse every non-public request without a valid credential."""

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope["type"] != "http" or not auth_enabled():
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if is_public(path):
            await self.app(scope, receive, send)
            return
        problem = auth_misconfigured()
        if problem:
            logger.error("Authentication enabled but unusable: %s", problem)
            response = JSONResponse(
                {"detail": "Authentification mal configurée sur le serveur."},
                status_code=503,
            )
            await response(scope, receive, send)
            return
        authorization = Headers(scope=scope).get("authorization")
        try:
            # Token verification may fetch Clerk's keys, and the account read
            # is a database round trip: both leave the event loop free.
            user = await anyio.to_thread.run_sync(resolve_user, authorization)
        except AuthError as e:
            headers = {"WWW-Authenticate": "Bearer"} if e.status == 401 else None
            response = JSONResponse(
                {"detail": e.detail}, status_code=e.status, headers=headers
            )
            await response(scope, receive, send)
            return
        except Exception:  # noqa: BLE001 - identity provider or database down
            logger.warning("Authentication failed unexpectedly", exc_info=True)
            response = JSONResponse(
                {"detail": "Service d'identité indisponible."}, status_code=503
            )
            await response(scope, receive, send)
            return
        if user.athlete_id is None and not is_account_path(path):
            response = JSONResponse({"detail": NO_ATHLETE_DETAIL}, status_code=403)
            await response(scope, receive, send)
            return
        scope.setdefault("state", {})["user"] = user
        await self.app(scope, receive, send)


# --------------------------------------------------------------- routes --
def current_user(request: Request) -> AppUser:
    """The signed-in account, or the implicit owner when auth is off."""
    user = getattr(request.state, "user", None)
    if isinstance(user, AppUser):
        return user
    if auth_enabled():
        raise HTTPException(status_code=401, detail="Connexion requise.")
    return AppUser(
        id=0, clerk_user_id="", email="", name=None, athlete_id=OWNER_ATHLETE_ID
    )


@router.get("/config")
def auth_config() -> dict[str, Any]:
    """What the browser needs before signing in; public."""
    enabled = auth_enabled()
    return {
        "enabled": enabled,
        "publishable_key": config.clerk_publishable_key or None if enabled else None,
    }


@router.get("/me")
def me(request: Request) -> dict[str, Any]:
    """The signed-in account; reachable before an athlete is attached."""
    return current_user(request).to_dict()
