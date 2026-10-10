"""Signed, short-lived OAuth ``state`` values, so a callback can be trusted.

Strava redirects the browser to ``/strava/callback`` with no session of ours:
the state issued by the authenticated ``/strava/authorize`` is what proves
the round trip started in this app, not in an attacker's tab.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
import time

STATE_TTL_S = 600


def issue(
    secret: str, now: float | None = None, *, athlete_id: int | None = None
) -> str:
    stamp = str(int(now if now is not None else time.time()))
    nonce = secrets.token_urlsafe(16)
    if athlete_id is not None:
        assert athlete_id > 0
        nonce = f"{athlete_id}~{nonce}"
    return f"{stamp}.{nonce}.{_sign(secret, stamp, nonce)}"


def verify(secret: str, state: str | None, now: float | None = None) -> bool:
    if not state:
        return False
    parts = state.split(".")
    if len(parts) != 3:
        return False
    stamp, nonce, signature = parts
    if not hmac.compare_digest(signature, _sign(secret, stamp, nonce)):
        return False
    try:
        issued = int(stamp)
    except ValueError:
        return False
    current = now if now is not None else time.time()
    return 0 <= current - issued <= STATE_TTL_S


def _sign(secret: str, stamp: str, nonce: str) -> str:
    message = f"{stamp}.{nonce}".encode()
    return hmac.new(secret.encode(), message, hashlib.sha256).hexdigest()[:32]


def athlete_for_state(secret: str, state: str) -> int | None:
    if not verify(secret, state):
        return None
    nonce = state.split(".")[1]
    owner, separator, _ = nonce.partition("~")
    if not separator or not owner.isdecimal():
        return None
    value = int(owner)
    return value if value > 0 else None
