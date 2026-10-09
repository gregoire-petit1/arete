"""Calendar boundary tests: real repository, offline provider, no live athlete data."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from pydantic import ValidationError

from arete.dataio.db import db_connection
from arete.dataio.init_duckdb import main as init_db
from arete.services.calendar import CalendarService
from arete.services.calendar_models import (
    SCOPES,
    CalendarError,
    CalendarProposal,
    CalendarSelection,
    EventDraft,
)
from arete.services.calendar_provider import ConnectProvider
from arete.services.calendar_repository import CalendarRepository

CAL = "athlete@example.com"
START, END = "2026-10-09T10:00:00+02:00", "2026-10-09T11:00:00+02:00"


class GoogleFake:
    def __init__(self):
        self.requests = []
        self.events = {}
        self.role = "owner"
        self.error = None
        self.write_error = None
        self.after_write_timeout = False
        self.next_page = False
        self.busy_error = False
        self.write_entered = None
        self.write_release = None

    @property
    def writes(self):
        return [
            r
            for r in self.requests
            if r.url.host == "www.googleapis.com"
            and r.method != "GET"
            and not r.url.path.endswith("/freeBusy")
        ]

    def __call__(self, request):
        self.requests.append(request)
        body = json.loads(request.content) if request.content else {}
        path = request.url.path
        if request.url.host == "api.vercel.com":
            if "/authorize/" in path:
                return httpx.Response(
                    200,
                    json={
                        "url": "https://vercel.com/connect/consent",
                        "request": "req",
                        "verifier": "private",
                    },
                )
            if request.method == "DELETE":
                if self.error:
                    return httpx.Response(self.error, json={})
                return httpx.Response(204)
            return httpx.Response(
                200, json={"token": "secret-google-token", "expiresAt": 9999999999999}
            )
        if self.error:
            return httpx.Response(self.error, json={})
        if "/calendarList/" in path:
            return httpx.Response(
                200,
                json={
                    "id": CAL,
                    "summary": "Personnel",
                    "accessRole": self.role,
                    "timeZone": "Europe/Paris",
                },
            )
        if path.endswith("/calendarList"):
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": CAL,
                            "summary": "Personnel",
                            "accessRole": self.role,
                            "timeZone": "Europe/Paris",
                        }
                    ]
                },
            )
        if path.endswith("/freeBusy"):
            return httpx.Response(
                200,
                json={
                    "calendars": {
                        CAL: {"errors": [{"reason": "internalError"}]}
                        if self.busy_error
                        else {"busy": []}
                    }
                },
            )
        if request.method == "GET":
            if path.endswith("/events"):
                return httpx.Response(
                    200,
                    json={
                        "items": list(self.events.values()),
                        **({"nextPageToken": "next"} if self.next_page else {}),
                    },
                )
            event_id = path.rsplit("/", 1)[-1]
            return (
                httpx.Response(200, json=self.events[event_id])
                if event_id in self.events
                else httpx.Response(404)
            )
        if self.write_entered:
            self.write_entered.set()
            assert self.write_release.wait(5)
        if self.write_error:
            return httpx.Response(self.write_error, json={})
        event_id = body.get("id") or path.rsplit("/", 1)[-1]
        if request.method == "DELETE":
            del self.events[event_id]
            result = {}
        else:
            result = {
                **self.events.get(event_id, {}),
                **body,
                "id": event_id,
                "etag": "v2",
            }
            self.events[event_id] = result
        if self.after_write_timeout:
            raise httpx.ReadTimeout("lost response", request=request)
        return httpx.Response(200, json=result)


@pytest.fixture
def calendar(tmp_path, monkeypatch):
    monkeypatch.setenv("ARETE_DB", str(tmp_path / "calendar.duckdb"))
    init_db()
    fake = GoogleFake()
    repo = CalendarRepository("test")
    repo.configure(enabled=True, selection={"readable": [CAL], "writable": [CAL]})
    provider = ConnectProvider(
        "google/arete-test",
        "athlete-server",
        lambda: "oidc-secret",
        transport=httpx.MockTransport(fake),
    )
    return SimpleNamespace(
        service=CalendarService(provider, repo), fake=fake, repo=repo
    )


def proposal(operation="create", event_id=None):
    return CalendarProposal(
        operation=operation,
        calendar_id=CAL,
        event_id=event_id,
        event=None
        if operation == "delete"
        else EventDraft(summary="Course", start=START, end=END),
    )


def existing(calendar, **extra):
    calendar.fake.events["existing"] = {
        "id": "existing",
        "etag": "v1",
        **EventDraft(summary="Ancien", start=START, end=END).google_body(),
        **extra,
    }


def test_propose_then_approve_exactly_once(calendar):
    action = calendar.service.propose(proposal(), "thread-1")
    assert action["status"] == "pending"
    assert not calendar.fake.writes
    approved = calendar.service.decide(action["id"], "approve")
    assert approved["status"] == "succeeded"
    assert calendar.service.decide(action["id"], "approve")["status"] == "succeeded"
    assert len(calendar.fake.writes) == 1
    assert json.loads(calendar.fake.writes[0].content) == {
        "id": action["event_id"],
        **action["after"],
    }
    token_request = next(r for r in calendar.fake.requests if "/token/" in r.url.path)
    assert json.loads(token_request.content) == {
        "subject": {"type": "user", "id": "athlete-server"},
        "scopes": SCOPES,
    }
    with db_connection() as con:
        assert "secret-google-token" not in str(
            con.execute("SELECT * FROM app.calendar_actions").fetchall()
        )


def test_read_empty_calendars_still_returns_ids(calendar):
    result = calendar.service.events(START, END)
    assert result["events"] == []
    assert result["calendars"][0]["id"] == CAL
    assert calendar.service.availability(START, END)["calendars"][CAL]["busy"] == []


@pytest.mark.parametrize("operation", ["update", "delete"])
def test_existing_writes_use_etag(calendar, operation):
    existing(calendar)
    action = calendar.service.propose(proposal(operation, "existing"), "thread-1")
    result = calendar.service.decide(action["id"], "approve")
    assert result["status"] == "succeeded"
    assert calendar.fake.writes[0].headers["If-Match"] == "v1"


@pytest.mark.parametrize("operation", ["create", "update", "delete"])
def test_uncertain_write_is_never_replayed_and_can_be_verified(calendar, operation):
    existing(calendar)
    action = calendar.service.propose(
        proposal(operation, None if operation == "create" else "existing"), "thread-1"
    )
    calendar.fake.after_write_timeout = True
    assert calendar.service.decide(action["id"], "approve")["status"] == "uncertain"
    assert calendar.service.decide(action["id"], "approve")["status"] == "uncertain"
    assert len(calendar.fake.writes) == 1
    assert calendar.service.verify(action["id"])["status"] == "succeeded"
    assert len(calendar.fake.writes) == 1


def test_two_approvals_cannot_execute_twice(calendar):
    action = calendar.service.propose(proposal(), "thread-1")
    calendar.fake.write_entered, calendar.fake.write_release = Event(), Event()
    with ThreadPoolExecutor(max_workers=1) as pool:
        first = pool.submit(calendar.service.decide, action["id"], "approve")
        try:
            assert calendar.fake.write_entered.wait(5)
            assert (
                calendar.service.decide(action["id"], "approve")["status"]
                == "executing"
            )
        finally:
            calendar.fake.write_release.set()
        assert first.result(timeout=5)["status"] == "succeeded"
    assert len(calendar.fake.writes) == 1


def test_reject_expiry_and_settings_invalidation(calendar):
    rejected = calendar.service.propose(proposal(), "a")
    assert calendar.service.decide(rejected["id"], "reject")["status"] == "rejected"
    assert calendar.service.decide(rejected["id"], "approve")["status"] == "rejected"
    expired = calendar.service.propose(proposal(), "b")
    with db_connection() as con:
        con.execute(
            "UPDATE app.calendar_actions SET expires = 0 WHERE id = ?", [expired["id"]]
        )
    assert calendar.service.decide(expired["id"], "approve")["status"] == "expired"
    invalid = calendar.service.propose(proposal(), "c")
    calendar.service.select(CalendarSelection(readable=[CAL]))
    assert calendar.service.decide(invalid["id"], "approve")["status"] == "invalidated"
    assert not calendar.fake.writes


def test_event_changed_after_preview_rejects_write(calendar):
    existing(calendar)
    action = calendar.service.propose(proposal("update", "existing"), "thread")
    calendar.fake.events["existing"]["etag"] = "changed"
    assert calendar.service.decide(action["id"], "approve")["status"] == "failed"
    assert not calendar.fake.writes


@pytest.mark.parametrize(
    "attributes",
    [
        {"attendees": [{"email": "other@example.com"}]},
        {"recurrence": ["RRULE:FREQ=WEEKLY"]},
        {"eventType": "outOfOffice"},
    ],
)
def test_unsupported_events_cannot_be_proposed(calendar, attributes):
    existing(calendar, **attributes)
    with pytest.raises(CalendarError):
        calendar.service.propose(proposal("delete", "existing"), "thread")


def test_individual_recurring_instance_is_supported(calendar):
    existing(calendar, recurringEventId="series")
    action = calendar.service.propose(proposal("delete", "existing"), "thread")
    assert calendar.service.decide(action["id"], "approve")["status"] == "succeeded"


def test_permissions_checked_locally_and_again_at_google(calendar):
    calendar.repo.configure(enabled=True, selection={"readable": [CAL], "writable": []})
    with pytest.raises(CalendarError, match="non autorisé"):
        calendar.service.propose(proposal(), "thread")
    calendar.repo.configure(
        enabled=True, selection={"readable": [CAL], "writable": [CAL]}
    )
    action = calendar.service.propose(proposal(), "thread")
    calendar.fake.role = "reader"
    assert calendar.service.decide(action["id"], "approve")["status"] == "failed"
    assert not calendar.fake.writes


def test_disconnect_blocks_even_when_revocation_fails(calendar):
    action = calendar.service.propose(proposal(), "thread")
    calendar.fake.error = 503
    assert calendar.service.disconnect()["revoked"] is False
    assert calendar.service.status()["connected"] is False
    assert calendar.repo.get(action["id"])["status"] == "invalidated"
    with pytest.raises(CalendarError, match="Connecte"):
        calendar.service.events(START, END)


@pytest.mark.parametrize("code", [401, 403, 429, 503])
def test_external_errors_are_not_empty_context(calendar, code):
    calendar.fake.error = code
    with pytest.raises(CalendarError):
        calendar.service.events(START, END)


def test_pagination_and_event_limits_fail_explicitly(calendar):
    calendar.fake.next_page = True
    with pytest.raises(CalendarError, match="pagination"):
        calendar.service.events(START, END)
    calendar.fake.next_page = False
    calendar.fake.events = {str(i): {"id": str(i)} for i in range(501)}
    with pytest.raises(CalendarError, match="500"):
        calendar.service.events(START, END)


def test_partial_availability_is_an_error(calendar):
    calendar.fake.busy_error = True
    with pytest.raises(CalendarError, match="partiellement"):
        calendar.service.availability(START, END)


def test_dates_dst_and_exclusive_all_day():
    draft = EventDraft(
        summary="Repos", start="2026-10-09", end="2026-10-10", all_day=True
    )
    assert draft.google_body()["end"] == {"date": "2026-10-10"}
    for start, end in [
        ("2026-03-29T02:30:00+01:00", "2026-03-29T04:00:00+02:00"),
        ("2026-10-09T10:00:00", "2026-10-09T11:00:00"),
        (END, START),
    ]:
        with pytest.raises(ValidationError):
            EventDraft(summary="Course", start=start, end=end)
    EventDraft(
        summary="Course",
        start="2026-10-25T02:30:00+02:00",
        end="2026-10-25T02:45:00+01:00",
    )


def test_budget_expired_before_provider_call(calendar):
    with pytest.raises(CalendarError, match="Délai"):
        calendar.service.events(START, END, deadline=1)
    assert not calendar.fake.requests


def test_consent_is_one_shot_and_browser_bound(calendar, monkeypatch, router_client):
    import arete.api.google_calendar as api

    monkeypatch.setattr(api, "get_calendar_service", lambda: calendar.service)
    monkeypatch.setenv("FRONTEND_URL", "http://testserver")
    client = router_client(api.router)
    # A production callback must be HTTPS; use HTTPS with TestClient cookies.
    monkeypatch.setenv("FRONTEND_URL", "https://testserver")
    client.base_url = httpx.URL("https://testserver")
    assert client.post("/google-calendar/authorize").status_code == 403
    response = client.post(
        "/google-calendar/authorize", headers={"X-Arete-Calendar": "1"}
    )
    assert response.status_code == 200
    assert "httponly" in response.headers["set-cookie"].lower()
    connect_request = next(
        r for r in calendar.fake.requests if "/authorize/" in r.url.path
    )
    callback = json.loads(connect_request.content)["returnUrl"]
    state = parse_qs(urlparse(callback).query)["state"][0]
    assert client.get("/google-calendar/callback?state=wrong").status_code == 403
    response = client.get(
        "/google-calendar/callback", params={"state": state}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"].endswith("google_calendar=connected")
    assert calendar.service.status()["selection"] == {"readable": [], "writable": []}
    client.cookies.set(api.COOKIE, state)
    response = client.get(
        "/google-calendar/callback", params={"state": state}, follow_redirects=False
    )
    assert response.headers["location"].endswith("google_calendar=error")


def test_api_rejects_forged_decisions(calendar, monkeypatch, router_client):
    import arete.api.google_calendar as api

    monkeypatch.setattr(api, "get_calendar_service", lambda: calendar.service)
    client = router_client(api.router)
    action = calendar.service.propose(proposal(), "thread")
    url = f"/google-calendar/actions/{action['id']}/decision"
    assert client.post(url, json={"decision": "approve"}).status_code == 403
    headers = {"X-Arete-Calendar": "1"}
    assert (
        client.post(
            url, json={"decision": "approve", "event": {}}, headers=headers
        ).status_code
        == 422
    )
    assert (
        client.post(
            url,
            json={"decision": "approve"},
            headers={**headers, "Origin": "https://attacker.example"},
        ).status_code
        == 403
    )
    assert not calendar.fake.writes


def test_expired_consent_and_disconnect_race(calendar):
    calendar.service.authorize(
        "nonce", "https://arete.example/api/google-calendar/callback"
    )
    with db_connection() as con:
        con.execute("UPDATE app.calendar_connections SET consent_expires = 0")
    with pytest.raises(CalendarError, match="expiré"):
        calendar.service.complete_consent("nonce")
    revision = calendar.repo.state()["revision"]
    calendar.service.disconnect()
    with pytest.raises(CalendarError, match="modifiée"):
        calendar.repo.configure(
            enabled=True,
            selection={"readable": [], "writable": []},
            expected_revision=revision,
        )


def test_denied_consent_cannot_be_replayed(calendar):
    calendar.service.authorize(
        "denied", "https://arete.example/api/google-calendar/callback"
    )
    with pytest.raises(CalendarError, match="refusé"):
        calendar.service.complete_consent("denied", granted=False)
    with pytest.raises(CalendarError, match="déjà utilisé"):
        calendar.service.complete_consent("denied")
    assert not calendar.service.status()["connected"]


def test_configured_calendar_is_preloaded_only_for_chat(calendar, monkeypatch):
    from unittest.mock import patch

    from arete import coaching

    monkeypatch.setenv("GOOGLE_CALENDAR_CONNECTOR", "google/test")
    monkeypatch.setenv("GOOGLE_CALENDAR_ACCESS_PROTECTED", "true")
    with (
        patch.object(coaching, "get_calendar_service", return_value=calendar.service),
        patch.object(coaching, "build_chat_model"),
        patch.object(coaching, "build_agent") as build,
    ):
        for mission in ("chat", "briefing", "feedback"):
            coaching._assemble(mission)
            args = build.call_args.kwargs
            profile = build.call_args.args[0]
            if mission == "chat":
                assert "calendar" in profile.preloaded
                assert "calendar" in profile.capabilities
                assert args["calendar"] is calendar.service
            else:
                assert not profile.capabilities
                assert args["calendar"] is None


def test_calendar_tools_stream_proposal_without_writing(calendar):
    import asyncio
    from dataclasses import replace

    from langchain.agents import create_agent
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage, HumanMessage

    from arete.agent.middlewares.capabilities import ToolkitMiddleware
    from arete.agent.middlewares.context import ContextBuilderMiddleware
    from arete.agent.middlewares.events import ToolEventMiddleware
    from arete.agent.middlewares.policy import ProfilePolicyMiddleware
    from arete.agent.profiles.catalog import get_profile
    from arete.agent.runtime.context import AgentContext
    from arete.agent.runtime.execution import stream_agent
    from arete.api.agent_streaming import StreamProjection

    seen = []

    class Model(GenericFakeChatModel):
        def bind_tools(self, tools, **kwargs):
            seen.append({t.name for t in tools})
            return self

    profile = replace(
        get_profile("chat"), capabilities=("calendar",), preloaded=("calendar",)
    )
    args = proposal().model_dump()
    graph = create_agent(
        Model(
            disable_streaming=True,
            messages=iter(
                [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {"name": "propose_calendar_event", "args": args, "id": "c1"}
                        ],
                    ),
                    AIMessage(content="Valide la proposition."),
                ]
            ),
        ),
        middleware=[
            ProfilePolicyMiddleware("chat", profile=profile, calendar=calendar.service),
            ToolEventMiddleware(),
            ToolkitMiddleware(),
            ContextBuilderMiddleware(),
        ],
        context_schema=AgentContext,
    )

    async def collect():
        projection = StreamProjection()
        events = []
        async for part in stream_agent(
            graph,
            {"messages": [HumanMessage("Planifie ma course")]},
            context=AgentContext(thread_id="thread"),
        ):
            events.extend(projection.events(part))
        return events

    events = asyncio.run(collect())
    actions = [e for e in events if e["type"] == "calendar_action"]
    assert len(actions) == 1
    assert calendar.repo.get(actions[0]["id"])["thread_id"] == "thread"
    assert not calendar.fake.writes
    assert "propose_calendar_event" in seen[0]
    assert not any("approve" in name or "decide" in name for name in seen[0])


def test_new_calendar_tables_are_migrated_on_existing_database(tmp_path, monkeypatch):
    monkeypatch.setenv("ARETE_DB", str(tmp_path / "migration.duckdb"))
    init_db()
    with db_connection() as con:
        con.execute("DROP TABLE app.calendar_actions")
        con.execute("DROP TABLE app.calendar_connections")
        con.execute("DELETE FROM app.schema_version WHERE version = 14")
    init_db()
    repo = CalendarRepository("migrated")
    repo.configure(enabled=False, selection={"readable": [], "writable": []})
    assert repo.state()["enabled"] is False
