"""Slack conversations for every athlete and durable, at-most-once dispatch.

Slack owns history. The database stores delivery IDs and one run reservation
per athlete, never conversation text. A crashed/ambiguous run stays reserved:
replaying a coach that can write training data would be unsafe. The caller
resolves the author's athlete and runs ``dispatch`` in that athlete's scope.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Literal

import duckdb
import httpx
from anyio import to_thread

from arete.dataio.db import transaction
from arete.services import slack_athletes
from arete.services.athlete_scope import current_athlete_id

logger = logging.getLogger(__name__)

MAX_HISTORY_MESSAGES = 60
MAX_MESSAGE_CHARS = 16_000
MAX_REPLY_CHARS = 39_000
MAX_DELIVERY_RECORDS = 100_000
MAX_JOB_SECONDS = 240
SLACK_HTTP_TIMEOUT_SECONDS = 10
FINISH_ATTEMPTS = 5
FINISH_RETRY_SECONDS = 0.2

FAILURE_MESSAGE = (
    "Le coach n’a pas pu terminer. Des modifications ont peut-être déjà été "
    "effectuées : vérifie Arete avant de poursuivre. Cette demande ne sera "
    "pas relancée automatiquement."
)
BUSY_MESSAGE = (
    "Une demande est déjà en cours ou doit être vérifiée après une interruption. "
    "Ce message n’a pas été exécuté. Attends la réponse avant de poursuivre."
)
UNLINKED_MESSAGE = (
    "Aucun compte Arete n’est associé à l’adresse e-mail de ton profil Slack. "
    "Connecte-toi à Arete avec cette adresse, puis réessaie."
)
PRIVATE_NOTE = (
    "<@{user}> je t’ai répondu en message privé. Pour recevoir les réponses ici, "
    "active les réponses publiques dans Réglages → Connexions."
)
OTHER_PARTICIPANT = "[Autre participant <@{user}>] "

Visibility = Literal["private", "public"]
Producer = Callable[[list[dict[str, str]], str, Visibility], Awaitable[str]]


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
    # The dedicated channel rather than a direct message.
    in_channel: bool = False
    # The text mentions the bot user, so a channel message addresses Arete.
    mentioned: bool = False
    bot_user: str = ""

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
    athlete_id = current_athlete_id()
    slack_athletes.ensure_row(athlete_id)
    with transaction() as con:
        if con.execute(
            "SELECT 1 FROM app.slack_deliveries WHERE event_key = ?", [message.key]
        ).fetchone():
            return "duplicate"
        count = con.execute("SELECT count(*) FROM app.slack_deliveries").fetchone()
        assert count is not None
        if count[0] >= MAX_DELIVERY_RECORDS:
            raise SlackError("Slack delivery ledger is full; operator review required")
        # Touch even a busy row: all of an athlete's admissions must conflict on
        # it, otherwise simultaneous busy deliveries could exceed the ledger bound.
        owner = con.execute(
            "UPDATE app.slack_athletes SET run_event_key = coalesce(run_event_key, ?) "
            "WHERE athlete_id = ? RETURNING run_event_key",
            [message.key, athlete_id],
        ).fetchone()
        assert owner is not None, "Slack athlete row is missing"
        status: Literal["running", "busy"] = (
            "running" if owner[0] == message.key else "busy"
        )
        con.execute(
            "INSERT INTO app.slack_deliveries (event_key, status) VALUES (?, ?)",
            [message.key, status],
        )
        return status


def finish(message: SlackMessage, status: str, *, release: bool) -> None:
    """Idempotent, so a write conflict is retried: a lost release would leave
    every later message busy until an operator unblocks it."""
    for attempt in range(1, FINISH_ATTEMPTS + 1):
        try:
            with transaction() as con:
                con.execute(
                    "UPDATE app.slack_deliveries SET status = ?, updated_at = now() "
                    "WHERE event_key = ?",
                    [status, message.key],
                )
                if release:
                    con.execute(
                        "UPDATE app.slack_athletes SET run_event_key = NULL "
                        "WHERE athlete_id = ? AND run_event_key = ?",
                        [current_athlete_id(), message.key],
                    )
            return
        except duckdb.TransactionException:
            if attempt == FINISH_ATTEMPTS:
                raise
            time.sleep(FINISH_RETRY_SECONDS * attempt)


class SlackClient:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self.http = http

    async def call(self, method: str, payload: dict) -> dict:
        # No SDK retries: an uncertain chat.postMessage must not be replayed.
        url = f"https://slack.com/api/{method}"
        if method in ("conversations.replies", "users.info"):
            response = await self.http.get(url, params=payload)
        else:
            response = await self.http.post(url, json=payload)
        response.raise_for_status()
        result = response.json()
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise SlackError(f"Slack {method} failed")
        return result

    async def _thread(self, message: SlackMessage) -> list[dict]:
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
                "en écrivant un nouveau message à Arete."
            )
        return rows

    @staticmethod
    def _from_this_app(row: dict, message: SlackMessage) -> bool:
        return row.get("app_id") == message.app_id and bool(row.get("bot_id"))

    async def engaged(self, message: SlackMessage) -> bool:
        """Whether a channel thread reply belongs to a conversation with Arete."""
        rows = await self._thread(message)
        root = rows[0].get("text")
        return any(self._from_this_app(row, message) for row in rows) or (
            bool(message.bot_user)
            and isinstance(root, str)
            and f"<@{message.bot_user}>" in root
        )

    async def author_email(self, message: SlackMessage) -> str | None:
        """A full member's confirmed workspace address, else None."""
        result = await self.call("users.info", {"user": message.user})
        user = result.get("user")
        if (
            not isinstance(user, dict)
            or user.get("team_id") != message.team
            or user.get("deleted")
            or user.get("is_bot")
            or user.get("is_restricted")
            or user.get("is_ultra_restricted")
            or user.get("is_email_confirmed") is False
        ):
            return None
        email = (user.get("profile") or {}).get("email")
        return email if isinstance(email, str) and email.strip() else None

    async def history(self, message: SlackMessage) -> list[dict[str, str]]:
        if message.thread_ts == message.ts:
            return [{"role": "user", "content": message.text}]
        rows = await self._thread(message)
        history = []
        for row in rows:
            prefix = ""
            if self._from_this_app(row, message):
                role = "assistant"
            elif row.get("user") == message.user and not row.get("bot_id"):
                role = "user"
            elif message.in_channel and row.get("user") and not row.get("bot_id"):
                # Another member of the channel: never this athlete's own words.
                role = "user"
                prefix = OTHER_PARTICIPANT.format(user=row["user"])
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
            history.append({"role": role, "content": prefix + text})
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

    async def open_dm(self, user: str) -> str:
        result = await self.call("conversations.open", {"users": user})
        channel = (result.get("channel") or {}).get("id")
        if not isinstance(channel, str) or not channel:
            raise SlackError("Slack conversations.open returned no channel")
        return channel

    async def post(self, channel: str, thread_ts: str | None, text: str) -> None:
        if not text.strip() or len(text) > MAX_REPLY_CHARS:
            raise SlackError("Coach answer is empty or exceeds Slack's message budget")
        payload: dict = {
            "channel": channel,
            "text": text,
            "mrkdwn": False,
            "parse": "none",
            "link_names": False,
            "unfurl_links": False,
            "unfurl_media": False,
        }
        if thread_ts:
            payload["thread_ts"] = thread_ts
        await self.call("chat.postMessage", payload)

    async def reply(self, message: SlackMessage, text: str) -> None:
        await self.post(message.channel, message.thread_ts, text)


async def resolve(message: SlackMessage, *, client: SlackClient) -> int | None:
    """The author's athlete, or None once the message needs nothing more.

    A channel message that neither mentions Arete nor continues one of its
    threads is ignored. An author without a verified Arete account is told so.
    """
    # Top-level chatter costs no Slack call; only thread replies are checked.
    if (
        message.in_channel
        and not message.mentioned
        and (message.thread_ts == message.ts or not await client.engaged(message))
    ):
        return None
    email = await client.author_email(message)
    athlete_id = (
        await to_thread.run_sync(slack_athletes.athlete_for_email, email)
        if email
        else None
    )
    if athlete_id is None:
        await client.reply(message, UNLINKED_MESSAGE)
    return athlete_id


async def dispatch(
    message: SlackMessage, *, client: SlackClient, produce: Producer
) -> None:
    """Answer one message; the caller holds the author's athlete scope."""
    try:
        status = await to_thread.run_sync(reserve, message)
    except duckdb.TransactionException:
        # A concurrent admission touched the reservation first. Nothing was
        # recorded or executed, so say so rather than dropping the message.
        status = "busy"
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
            # A channel answer is public only with the athlete's consent.
            visibility: Visibility = (
                "public"
                if message.in_channel
                and await to_thread.run_sync(slack_athletes.public_replies)
                else "private"
            )
            history = await client.history(message)
            started_coach = True
            answer = await produce(history, message.thread_id, visibility)
            completed_coach = True
            if message.in_channel and visibility == "private":
                await client.post(await client.open_dm(message.user), None, answer)
                await client.reply(message, PRIVATE_NOTE.format(user=message.user))
            else:
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
