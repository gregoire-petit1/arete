"""Single-athlete Slack conversations and durable, at-most-once dispatch.

Slack owns history. The database stores delivery IDs and a single execution
reservation, never conversation text. A crashed/ambiguous run stays reserved:
replaying a coach that can write training data would be unsafe.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

import httpx
from anyio import to_thread

from arete.dataio.db import transaction

logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 60
MAX_MESSAGE_CHARS = 16_000
MAX_REPLY_CHARS = 39_000
MAX_DELIVERY_RECORDS = 100_000
MAX_JOB_SECONDS = 240
SLACK_HTTP_TIMEOUT_SECONDS = 10

FAILURE_MESSAGE = (
    "Le coach n’a pas pu terminer. Des modifications ont peut-être déjà été "
    "effectuées : vérifie Arete avant de poursuivre. Cette demande ne sera "
    "pas relancée automatiquement."
)
BUSY_MESSAGE = (
    "Une demande est déjà en cours ou doit être vérifiée après une interruption. "
    "Ce message n’a pas été exécuté. Attends la réponse avant de poursuivre."
)


@dataclass(frozen=True)
class SlackMessage:
    team: str
    event_id: str
    app_id: str
    channel: str
    user: str
    ts: str
    thread_ts: str
    text: str

    @property
    def key(self) -> str:
        return f"{self.team}:{self.event_id}"

    @property
    def thread_id(self) -> str:
        return f"slack:{self.team}:{self.channel}:{self.thread_ts}"


class SlackError(RuntimeError):
    """An operating error, without token or message contents."""


class HistoryError(SlackError):
    """A complete usable thread could not be retrieved."""


def reserve(message: SlackMessage) -> Literal["running", "duplicate", "busy"]:
    """Commit ownership before any model or Slack write; never retry a conflict."""
    with transaction() as con:
        if con.execute(
            "SELECT 1 FROM app.slack_deliveries WHERE event_key = ?", [message.key]
        ).fetchone():
            return "duplicate"
        count = con.execute("SELECT count(*) FROM app.slack_deliveries").fetchone()
        assert count is not None
        if count[0] >= MAX_DELIVERY_RECORDS:
            raise SlackError("Slack delivery ledger is full; operator review required")
        # Touch even a busy singleton: all admissions must conflict on this row,
        # otherwise simultaneous busy deliveries could exceed the ledger bound.
        owner = con.execute(
            "UPDATE app.slack_execution SET event_key = coalesce(event_key, ?) "
            "WHERE id = 1 RETURNING event_key",
            [message.key],
        ).fetchone()
        assert owner is not None, "Slack execution singleton is missing"
        status: Literal["running", "busy"] = (
            "running" if owner[0] == message.key else "busy"
        )
        con.execute(
            "INSERT INTO app.slack_deliveries (event_key, status) VALUES (?, ?)",
            [message.key, status],
        )
        return status


def finish(message: SlackMessage, status: str, *, release: bool) -> None:
    with transaction() as con:
        con.execute(
            "UPDATE app.slack_deliveries SET status = ?, updated_at = now() "
            "WHERE event_key = ?",
            [status, message.key],
        )
        if release:
            con.execute(
                "UPDATE app.slack_execution SET event_key = NULL "
                "WHERE id = 1 AND event_key = ?",
                [message.key],
            )


class SlackClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self.http = http

    async def call(self, method: str, payload: dict) -> dict:
        # No SDK retries: an uncertain chat.postMessage must not be replayed.
        url = f"https://slack.com/api/{method}"
        if method == "conversations.replies":
            response = await self.http.get(url, params=payload)
        else:
            response = await self.http.post(url, json=payload)
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise SlackError(f"Slack {method} failed")
        return result

    async def history(self, message: SlackMessage) -> list[dict[str, str]]:
        if message.thread_ts == message.ts:
            return [{"role": "user", "content": message.text}]
        result = await self.call(
            "conversations.replies",
            {
                "channel": message.channel,
                "ts": message.thread_ts,
                "latest": message.ts,
                "inclusive": True,
                "limit": MAX_HISTORY_MESSAGES + 1,
            },
        )
        rows = result.get("messages")
        if (
            not isinstance(rows, list)
            or not rows
            or len(rows) > MAX_HISTORY_MESSAGES
            or result.get("has_more")
            or result.get("response_metadata", {}).get("next_cursor")
        ):
            raise HistoryError(
                "Le fil est trop long ou incomplet. Commence une nouvelle conversation "
                "en envoyant un nouveau message privé à Arete."
            )
        history = []
        for row in rows:
            if row.get("app_id") == message.app_id and row.get("bot_id"):
                role = "assistant"
            elif row.get("user") == message.user and not row.get("bot_id"):
                role = "user"
            else:
                raise HistoryError("Ce fil contient un participant non autorisé.")
            text = row.get("text")
            if row.get("files") or not isinstance(text, str) or not text.strip():
                raise HistoryError(
                    "Ce fil contient un message non textuel non pris en charge."
                )
            limit = MAX_REPLY_CHARS if role == "assistant" else MAX_MESSAGE_CHARS
            if len(text) > limit:
                raise HistoryError(
                    "Un message du fil est trop long. Commence un nouveau fil."
                )
            history.append({"role": role, "content": text})
        # Fail closed if Slack returned stale or unexpected history. Never silently
        # lose the current objective or append it twice.
        if rows[0].get("ts") != message.thread_ts or rows[-1].get("ts") != message.ts:
            raise HistoryError(
                "L’historique Slack est incomplet. Réessaie dans un nouveau fil."
            )
        if history[-1] != {"role": "user", "content": message.text}:
            raise HistoryError(
                "Le message a changé pendant son traitement. Envoie un nouveau message."
            )
        return history

    async def reply(self, message: SlackMessage, text: str) -> None:
        if not text.strip() or len(text) > MAX_REPLY_CHARS:
            raise SlackError("Coach answer is empty or exceeds Slack's message budget")
        await self.call(
            "chat.postMessage",
            {
                "channel": message.channel,
                "thread_ts": message.thread_ts,
                "text": text,
                "mrkdwn": False,
                "parse": "none",
                "link_names": False,
                "unfurl_links": False,
                "unfurl_media": False,
            },
        )


async def dispatch(
    message: SlackMessage,
    *,
    client: SlackClient,
    produce: Callable[[list[dict[str, str]], str], Awaitable[str]],
) -> None:
    status = await to_thread.run_sync(reserve, message)
    if status == "duplicate":
        return
    if status == "busy":
        await client.reply(message, BUSY_MESSAGE)
        return
    started_coach = False
    completed_coach = False
    try:
        async with asyncio.timeout(MAX_JOB_SECONDS):
            if not message.text.strip() or len(message.text) > MAX_MESSAGE_CHARS:
                raise HistoryError("Envoie un message texte de 1 à 16 000 caractères.")
            history = await client.history(message)
            started_coach = True
            answer = await produce(history, message.thread_id)
            completed_coach = True
            await client.reply(message, answer)
        await to_thread.run_sync(lambda: finish(message, "sent", release=True))
    except HistoryError as exc:
        await to_thread.run_sync(lambda: finish(message, "rejected", release=True))
        await client.reply(message, str(exc))
    except BaseException:
        # A cancelled synchronous tool can still be writing in an AnyIO worker.
        # Keep the reservation until an operator has checked ambiguous runs.
        await to_thread.run_sync(
            lambda: finish(
                message, "failed", release=not started_coach or completed_coach
            )
        )
        logger.exception("Slack delivery failed: %s", message.key)
        # A failed send may actually have landed. Do not post another message then.
        if not completed_coach:
            await client.reply(message, FAILURE_MESSAGE)
        raise
