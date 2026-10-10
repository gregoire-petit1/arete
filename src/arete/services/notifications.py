"""Web Push: the browsers that accepted notifications, and the sending.

Bounded and quiet by design: at most ``MAX_SUBSCRIPTIONS`` browsers, a
10-second timeout per send, no retry, and a subscription the push service
reports gone (404/410) is dropped. ``notify`` never raises: a notification is
never worth failing the sync, the briefing or a decision for.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from datetime import datetime

from arete.config import config
from arete.dataio.db import connect
from arete.dataio.settings import get_user_settings

logger = logging.getLogger(__name__)

MAX_SUBSCRIPTIONS = 10
PUSH_TIMEOUT_S = 10
PUSH_TTL_S = 3600


@dataclass(frozen=True)
class NotifyResult:
    sent: int
    dropped: int
    skipped_reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "sent": self.sent,
            "dropped": self.dropped,
            "skipped_reason": self.skipped_reason,
        }


def configured() -> bool:
    return bool(config.web_push_vapid_public_key and config.web_push_vapid_private_key)


def public_key() -> str | None:
    return config.web_push_vapid_public_key or None


def subscribe(
    endpoint: str, p256dh: str, auth: str, user_agent: str | None = None
) -> None:
    """Keep this browser's subscription, and only the newest few."""
    con = connect()
    try:
        con.execute(
            "INSERT INTO app.push_subscriptions (endpoint, p256dh, auth, user_agent) "
            "VALUES (?, ?, ?, ?) ON CONFLICT (athlete_id, endpoint) DO UPDATE SET "
            "p256dh = EXCLUDED.p256dh, auth = EXCLUDED.auth, "
            "user_agent = EXCLUDED.user_agent, created_at = now()",
            [endpoint, p256dh, auth, (user_agent or "")[:300] or None],
        )
        con.execute(
            "DELETE FROM app.push_subscriptions WHERE athlete_id = getvariable('arete_athlete_id') AND deleted_at IS NULL AND EXISTS (SELECT 1 FROM app.athletes scope_owner WHERE scope_owner.id=athlete_id AND scope_owner.deleted_at IS NULL) AND (endpoint NOT IN (SELECT endpoint FROM app.visible_push_subscriptions ORDER BY created_at DESC LIMIT ?)) ",
            [MAX_SUBSCRIPTIONS],
        )
    finally:
        con.close()


def unsubscribe(endpoint: str) -> None:
    con = connect()
    try:
        con.execute(
            "DELETE FROM app.push_subscriptions WHERE athlete_id = getvariable('arete_athlete_id') AND deleted_at IS NULL AND EXISTS (SELECT 1 FROM app.athletes scope_owner WHERE scope_owner.id=athlete_id AND scope_owner.deleted_at IS NULL) AND (endpoint = ?) ",
            [endpoint],
        )
    finally:
        con.close()


def _subscriptions() -> list[tuple[str, str, str]]:
    con = connect()
    try:
        return con.execute(
            "SELECT endpoint, p256dh, auth FROM app.visible_push_subscriptions ORDER BY created_at DESC LIMIT ?",
            [MAX_SUBSCRIPTIONS],
        ).fetchall()
    finally:
        con.close()


def _status_of(error: Exception) -> int | None:
    response = getattr(error, "response", None)
    return getattr(response, "status_code", None)


def notify(title: str, body: str, url: str = "/") -> NotifyResult:
    """Send one notification to every subscribed browser. Never raises."""
    try:
        if not bool((get_user_settings() or {}).get("notifications_enabled", True)):
            return NotifyResult(0, 0, "notifications désactivées")
        if not configured():
            return NotifyResult(0, 0, "clés Web Push absentes du serveur")
        subscriptions = _subscriptions()
    except Exception as e:  # noqa: BLE001
        logger.warning("Push skipped: %s", e)
        return NotifyResult(0, 0, f"erreur : {e}")
    if not subscriptions:
        return NotifyResult(0, 0, "aucun appareil abonné")

    from pywebpush import WebPushException, webpush

    payload = json.dumps(
        {"title": title, "body": body[:300], "url": url}, ensure_ascii=False
    )
    sent = dropped = 0
    for endpoint, p256dh, auth in subscriptions:
        try:
            webpush(
                subscription_info={
                    "endpoint": endpoint,
                    "keys": {"p256dh": p256dh, "auth": auth},
                },
                data=payload,
                vapid_private_key=config.web_push_vapid_private_key,
                vapid_claims={"sub": config.web_push_subject},
                ttl=PUSH_TTL_S,
                timeout=PUSH_TIMEOUT_S,
            )
        except WebPushException as e:
            if _status_of(e) in (404, 410):
                unsubscribe(endpoint)  # the browser dropped it: forget it
                dropped += 1
            else:
                logger.warning("Push to one device failed: %s", e)
            continue
        except Exception as e:  # noqa: BLE001 - network, bad key: next device
            logger.warning("Push to one device failed: %s", e)
            continue
        sent += 1
        try:
            con = connect()
            try:
                con.execute(
                    "UPDATE app.push_subscriptions SET last_success_at = ? WHERE athlete_id = getvariable('arete_athlete_id') AND deleted_at IS NULL AND EXISTS (SELECT 1 FROM app.athletes scope_owner WHERE scope_owner.id=athlete_id AND scope_owner.deleted_at IS NULL) AND (endpoint = ?) ",
                    [datetime.now(), endpoint],
                )
            finally:
                con.close()
        except Exception:  # noqa: BLE001
            pass
    return NotifyResult(sent, dropped)


def first_sentence(text: str, limit: int = 160) -> str:
    """The opening sentence, for a notification body."""
    match = re.match(r"(.+?[.!?…])(\s|$)", text.strip(), re.DOTALL)
    sentence = match.group(1) if match else text.strip()
    return sentence if len(sentence) <= limit else sentence[: limit - 1].rstrip() + "…"
