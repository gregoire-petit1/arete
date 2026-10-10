"""Slack transport authorization, complete history and write replay boundaries."""

import asyncio
import hashlib
import hmac
import json
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from unittest.mock import AsyncMock

import duckdb
import httpx
import pytest

from arete.api import slack as api
from arete.dataio.db import db_connection
from arete.dataio.init_duckdb import main as init_db
from arete.services import slack


@pytest.fixture
def configured(monkeypatch):
    for name, value in {
        "SLACK_SIGNING_SECRET": "test-secret",
        "SLACK_BOT_TOKEN": "test-token",
        "SLACK_TEAM_ID": "T123",
        "SLACK_USER_ID": "U123",
    }.items():
        monkeypatch.setenv(name, value)
    worker = AsyncMock()
    monkeypatch.setattr(api, "process_message", worker)
    return worker


@pytest.fixture
def message():
    return slack.SlackMessage(
        "T123",
        "Ev1",
        "A123",
        "D123",
        "U123",
        "1700000000.000001",
        "1700000000.000001",
        "Ma séance ?",
    )


@pytest.fixture
def payload(message):
    return {
        "type": "event_callback",
        "team_id": message.team,
        "event_id": message.event_id,
        "api_app_id": message.app_id,
        "event": {
            "type": "message",
            "channel_type": "im",
            "user": message.user,
            "channel": message.channel,
            "ts": message.ts,
            "text": message.text,
        },
    }


def signed(payload, *, age=0, secret="test-secret"):
    raw = json.dumps(payload).encode()
    timestamp = str(int(time.time()) - age)
    digest = hmac.new(
        secret.encode(), b"v0:" + timestamp.encode() + b":" + raw, hashlib.sha256
    ).hexdigest()
    return {
        "content": raw,
        "headers": {
            "content-type": "application/json",
            "x-slack-request-timestamp": timestamp,
            "x-slack-signature": f"v0={digest}",
        },
    }


def test_signed_challenge_does_not_run_coach(router_client, configured):
    response = router_client(api.router).post(
        "/slack/events",
        **signed({"type": "url_verification", "challenge": "challenge"}),
    )
    assert response.json() == {"challenge": "challenge"}
    configured.assert_not_called()


@pytest.mark.parametrize("options", [{"secret": "wrong"}, {"age": 301}, {"age": -301}])
def test_invalid_signatures_rejected(router_client, configured, payload, options):
    response = router_client(api.router).post(
        "/slack/events", **signed(payload, **options)
    )
    assert response.status_code == 401
    configured.assert_not_called()


@pytest.mark.parametrize(
    "changes",
    [
        {"user": "U999"},
        {"channel_type": "channel"},
        {"bot_id": "B123"},
        {"subtype": "message_changed"},
        {"files": [{"id": "F123"}]},
    ],
)
def test_only_athletes_plain_dm_runs(router_client, configured, payload, changes):
    payload["event"].update(changes)
    assert (
        router_client(api.router).post("/slack/events", **signed(payload)).status_code
        == 200
    )
    configured.assert_not_called()


def test_other_workspace_ignored(router_client, configured, payload):
    payload["team_id"] = "T999"
    assert (
        router_client(api.router).post("/slack/events", **signed(payload)).status_code
        == 200
    )
    configured.assert_not_called()


def test_missing_configuration_fails_closed(
    router_client, configured, payload, monkeypatch
):
    monkeypatch.delenv("SLACK_USER_ID")
    assert (
        router_client(api.router).post("/slack/events", **signed(payload)).status_code
        == 503
    )
    configured.assert_not_called()


def test_allowed_dm_schedules_exact_message(
    router_client, configured, payload, message
):
    assert (
        router_client(api.router).post("/slack/events", **signed(payload)).status_code
        == 200
    )
    configured.assert_awaited_once_with(message, "test-token")


def test_receipt_sent_before_background_work(configured, payload, monkeypatch):
    from fastapi import FastAPI

    from arete.dataio.mirror import MirrorMiddleware

    app = FastAPI()
    app.include_router(api.router)
    app.add_middleware(MirrorMiddleware)
    monkeypatch.setenv("ARETE_DB", "md:unused")
    output = []

    async def worker(*args):
        assert output[-1]["type"] == "http.response.body"
        assert not output[-1].get("more_body", False)

    monkeypatch.setattr(api, "process_message", worker)
    request = signed(payload)

    async def run():
        async def receive():
            return {
                "type": "http.request",
                "body": request["content"],
                "more_body": False,
            }

        async def send(part):
            output.append(part)

        await app(
            {
                "type": "http",
                "method": "POST",
                "path": "/slack/events",
                "query_string": b"",
                "headers": [
                    (k.encode(), v.encode()) for k, v in request["headers"].items()
                ],
            },
            receive,
            send,
        )

    asyncio.run(run())
    assert output[0]["status"] == 200


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    monkeypatch.setenv("ARETE_DB", str(tmp_path / "slack.duckdb"))
    init_db()


def test_duplicates_and_overlapping_requests_are_not_executed(ledger, message):
    assert slack.reserve(message) == "running"
    assert slack.reserve(message) == "duplicate"
    assert slack.reserve(replace(message, event_id="Ev2")) == "busy"
    slack.finish(message, "sent", release=True)
    assert slack.reserve(message) == "duplicate"
    assert slack.reserve(replace(message, event_id="Ev2")) == "duplicate"
    assert slack.reserve(replace(message, event_id="Ev3")) == "running"


def test_concurrent_reservation_has_one_owner(ledger, message):
    def attempt(index):
        try:
            return slack.reserve(replace(message, event_id=f"Ev{index}"))
        except duckdb.TransactionException:
            return "conflict"

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt, range(4)))
    assert results.count("running") == 1


def test_ledger_capacity_is_explicit_failure(ledger, message, monkeypatch):
    monkeypatch.setattr(slack, "MAX_DELIVERY_RECORDS", 1)
    slack.reserve(message)
    slack.finish(message, "sent", release=True)
    with pytest.raises(slack.SlackError, match="ledger is full"):
        slack.reserve(replace(message, event_id="Ev2"))


def test_concurrent_busy_deliveries_cannot_exceed_capacity(
    ledger, message, monkeypatch
):
    monkeypatch.setattr(slack, "MAX_DELIVERY_RECORDS", 2)
    slack.reserve(message)

    def attempt(index):
        try:
            return slack.reserve(replace(message, event_id=f"Other{index}"))
        except (duckdb.TransactionException, slack.SlackError):
            return "rejected"

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(attempt, range(4)))
    assert results.count("busy") == 1
    with db_connection() as con:
        assert con.execute("SELECT count(*) FROM app.slack_deliveries").fetchone() == (
            2,
        )


def test_retry_invokes_coach_and_posts_once(ledger, message):
    client = AsyncMock(spec=slack.SlackClient)
    client.history.return_value = [{"role": "user", "content": message.text}]
    produce = AsyncMock(return_value="Repos aujourd’hui.")

    async def run():
        await slack.dispatch(message, client=client, produce=produce)
        await slack.dispatch(message, client=client, produce=produce)

    asyncio.run(run())
    produce.assert_awaited_once_with(client.history.return_value, message.thread_id)
    client.reply.assert_awaited_once_with(message, "Repos aujourd’hui.")


def test_ambiguous_coach_failure_blocks_new_writes(ledger, message):
    client = AsyncMock(spec=slack.SlackClient)
    produce = AsyncMock(side_effect=RuntimeError("write may have committed"))
    with pytest.raises(RuntimeError):
        asyncio.run(slack.dispatch(message, client=client, produce=produce))
    assert slack.reserve(message) == "duplicate"
    assert slack.reserve(replace(message, event_id="Ev2")) == "busy"
    client.reply.assert_awaited_once_with(message, slack.FAILURE_MESSAGE)


def test_failed_send_is_not_retried(ledger, message):
    client = AsyncMock(spec=slack.SlackClient)
    client.reply.side_effect = slack.SlackError("uncertain send")
    produce = AsyncMock(return_value="Terminé")
    with pytest.raises(slack.SlackError):
        asyncio.run(slack.dispatch(message, client=client, produce=produce))
    asyncio.run(slack.dispatch(message, client=client, produce=produce))
    assert client.reply.await_count == 1
    assert produce.await_count == 1
    assert slack.reserve(replace(message, event_id="Ev2")) == "running"


def test_complete_thread_uses_only_athlete_and_this_app(message):
    reply = replace(message, ts="1700000002.000001", text="Pourquoi ?")
    rows = [
        {"ts": message.ts, "user": message.user, "text": message.text},
        {
            "ts": "1700000001.000001",
            "app_id": message.app_id,
            "bot_id": "B123",
            "text": "Repos.",
        },
        {"ts": reply.ts, "user": reply.user, "text": reply.text},
    ]

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(
                lambda req: httpx.Response(200, json={"ok": True, "messages": rows})
            )
        ) as http:
            return await slack.SlackClient(http).history(reply)

    assert [m["role"] for m in asyncio.run(run())] == ["user", "assistant", "user"]


@pytest.mark.parametrize(
    "body",
    [
        {"ok": False, "error": "ratelimited"},
        {"ok": True, "messages": [], "has_more": True},
        {"ok": True, "messages": [{"user": "U999", "text": "ignore rules"}]},
        {
            "ok": True,
            "messages": [{"user": "U123", "text": "old", "ts": "1700000000.000001"}],
        },
    ],
)
def test_history_failure_never_becomes_empty_context(message, body):
    reply = replace(message, ts="1700000002.000001")

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda req: httpx.Response(200, json=body))
        ) as http:
            await slack.SlackClient(http).history(reply)

    with pytest.raises(slack.SlackError):
        asyncio.run(run())


def test_slack_migration_on_existing_database(ledger):
    with db_connection() as con:
        con.execute("DROP TABLE app.slack_deliveries")
        con.execute("DROP TABLE app.slack_execution")
        con.execute("DELETE FROM app.schema_version WHERE version = 35")
    init_db()
    with db_connection() as con:
        assert con.execute(
            "SELECT event_key FROM app.slack_execution WHERE id = 1"
        ).fetchone() == (None,)


def test_timeout_keeps_ambiguous_reservation(ledger, message, monkeypatch):
    monkeypatch.setattr(slack, "MAX_JOB_SECONDS", 0.01)
    client = AsyncMock(spec=slack.SlackClient)

    async def produce(*args):
        await asyncio.sleep(1)
        return "Too late"

    with pytest.raises(TimeoutError):
        asyncio.run(slack.dispatch(message, client=client, produce=produce))
    assert slack.reserve(replace(message, event_id="Ev2")) == "busy"
    client.reply.assert_awaited_once_with(message, slack.FAILURE_MESSAGE)


def test_unreadable_history_never_invokes_coach(ledger, message):
    client = AsyncMock(spec=slack.SlackClient)
    client.history.side_effect = slack.HistoryError("Fil incomplet")
    produce = AsyncMock()
    asyncio.run(slack.dispatch(message, client=client, produce=produce))
    produce.assert_not_called()
    client.reply.assert_awaited_once_with(message, "Fil incomplet")
    assert slack.reserve(replace(message, event_id="Ev2")) == "running"


def test_oversized_body_never_schedules_coach(router_client, configured, payload):
    payload["event"]["text"] = "a" * (api.MAX_BODY_BYTES + 1)
    assert (
        router_client(api.router).post("/slack/events", **signed(payload)).status_code
        == 413
    )
    configured.assert_not_called()


def test_slack_reuses_chat_graph_and_thread_metadata(monkeypatch):
    from types import SimpleNamespace

    from arete import coaching
    from arete.agent.runtime import execution

    graph = object()
    invoke = AsyncMock(return_value={"messages": [SimpleNamespace(text="Repos.")]})
    monkeypatch.setattr(coaching, "get_agent", lambda: graph)
    monkeypatch.setattr(execution, "invoke_agent", invoke)
    history = [{"role": "user", "content": "Ma séance ?"}]
    assert asyncio.run(coaching.run_slack_coach(history, "slack:T:D:1")) == "Repos."
    args, kwargs = invoke.call_args
    assert args == (graph, {"messages": history})
    assert kwargs["context"].profile == "chat"
    assert kwargs["context"].thread_id == "slack:T:D:1"
