"""Tests for the coaching agent (graph mocked — no network)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import HumanMessage

from arete.agent.context.sections import _panel_context_message
from arete.agent.middlewares.context import ContextBuilderMiddleware
from arete.agent.runtime.context import (
    MAX_PANEL_CONTEXT_CHARS,
    PANEL_CONTEXT_KEY,
    AgentContext,
)
from arete.agent.tools.pages import get_page_context
from arete.api.agent import ChatRequest, _panel_context_source

# ---------------------------------------------------------------------------
# Unit: context + middleware injection contract
# ---------------------------------------------------------------------------


class _Runtime:
    def __init__(self, context):
        self.context = context


class _Request:
    """Minimal ModelRequest stand-in: the fields the middlewares touch.

    ``override`` matters as much as the fields: it is what keeps a middleware
    from writing into the state's own message list.
    """

    def __init__(self, context=None, *, messages=None, runtime=None):
        self.runtime = runtime if runtime is not None else _Runtime(context)
        self.messages = messages if messages is not None else []
        self.tool_call: dict = {}
        self.tools = []
        self.system_message = None
        self.state = {}

    def override(self, **overrides):
        return _Request(
            messages=overrides.get("messages", self.messages),
            runtime=self.runtime,
        )


def test_panel_context_roundtrip():
    ctx = AgentContext(source={PANEL_CONTEXT_KEY: json.dumps({"page": "analytics"})})
    assert ctx.panel_context == {"page": "analytics"}


def test_panel_context_invalid_json_is_none():
    ctx = AgentContext(source={PANEL_CONTEXT_KEY: "{not json"})
    assert ctx.panel_context is None


def test_middleware_injects_page_message():
    ctx = AgentContext(source={PANEL_CONTEXT_KEY: json.dumps({"page": "log"})})
    message = _panel_context_message(_Request(ctx))
    assert message is not None
    assert "Log page" in message.content
    assert '"page": "log"' in message.content


def test_middleware_skips_oversized_payload(caplog):
    # Skip, never truncate: over budget → no injection at all.
    oversized = "x" * (MAX_PANEL_CONTEXT_CHARS + 1)
    ctx = AgentContext(
        source={PANEL_CONTEXT_KEY: json.dumps({"page": "log", "d": oversized})}
    )
    assert _panel_context_message(_Request(ctx)) is None


def test_middleware_skips_malformed_payload():
    ctx = AgentContext(source={PANEL_CONTEXT_KEY: "{broken"})
    assert _panel_context_message(_Request(ctx)) is None


def test_middleware_noop_without_context():
    class _NoRuntime:
        pass

    request = _Request(None)
    request.runtime = _NoRuntime()
    assert _panel_context_message(request) is None


# ---------------------------------------------------------------------------
# Unit: API-layer panel_context writer (the only writer)
# ---------------------------------------------------------------------------


def test_source_writer_rejects_unknown_page():
    with pytest.raises(Exception, match="Unknown page"):
        _panel_context_source(
            ChatRequest(messages=[{"role": "user", "content": "hi"}], page="nope")
        )


def test_source_writer_rejects_oversized_payload():
    body = ChatRequest(
        messages=[{"role": "user", "content": "hi"}],
        panel_context={"blob": "x" * (MAX_PANEL_CONTEXT_CHARS + 1)},
    )
    with pytest.raises(Exception, match="over budget"):
        _panel_context_source(body)


def test_source_writer_merges_page_and_freeform():
    source = _panel_context_source(
        ChatRequest(
            messages=[{"role": "user", "content": "hi"}],
            page="log",
            panel_context={"x": 1},
        )
    )
    payload = json.loads(source[PANEL_CONTEXT_KEY])
    assert payload["page"] == "log"
    assert payload["x"] == 1


# ---------------------------------------------------------------------------
# Tool: get_page_context
# ---------------------------------------------------------------------------


def test_get_page_context_unknown_page():
    out = json.loads(get_page_context.invoke({"page": "bogus"}))
    assert "error" in out


@pytest.mark.parametrize(
    "page", ["dashboard", "analytics", "planning", "log", "settings"]
)
def test_get_page_context_all_pages_parse(page):
    out = json.loads(get_page_context.invoke({"page": page}))
    assert "error" not in out, out


# ---------------------------------------------------------------------------
# Endpoint: POST /agent/chat (graph mocked)
# ---------------------------------------------------------------------------


class _FakeFinal:
    def __init__(self):
        self.content = "Réponse du coach."

    def text(self):
        return self.content


@pytest.fixture()
def client():
    from arete.api.main import app

    with TestClient(app) as c:
        yield c


def test_chat_endpoint_with_mocked_graph(client):
    class _FakeGraph:
        async def ainvoke(self, state, *, context=None, config=None):
            assert config["recursion_limit"] > 0
            assert isinstance(context, AgentContext)
            return {"messages": [state["messages"][-1], _FakeFinal()]}

    with patch("arete.api.agent.get_agent", return_value=_FakeGraph()):
        response = client.post(
            "/agent/chat",
            json={
                "messages": [{"role": "user", "content": "Comment ça va ?"}],
                "page": "dashboard",
            },
        )
    assert response.status_code == 200
    body = response.json()
    assert body["message"]["role"] == "assistant"
    assert body["message"]["content"] == "Réponse du coach."


def test_chat_endpoint_rejects_unknown_page(client):
    response = client.post(
        "/agent/chat",
        json={"messages": [{"role": "user", "content": "hi"}], "page": "nope"},
    )
    assert response.status_code == 422


def test_chat_endpoint_rejects_empty_messages(client):
    response = client.post("/agent/chat", json={"messages": []})
    assert response.status_code == 422


def test_middleware_wraps_handler_without_context():
    # Smoke: with no context at all the middleware must pass through cleanly.
    middleware = ContextBuilderMiddleware()

    request = _Request()
    sentinel = "ok"
    result = middleware.wrap_model_call(request, lambda _r: sentinel)
    assert result == sentinel


# ---------------------------------------------------------------------------
# Streaming endpoint + tool events
# ---------------------------------------------------------------------------


def test_tool_event_middleware_emits_start_and_end():
    from arete.agent.middlewares.events import ToolEventMiddleware

    events: list[dict] = []

    class _FakeWriter:
        def __call__(self, event):
            events.append(event)

    class _Request:
        tool_call = {
            "id": "call-1",
            "name": "get_page_context",
            "args": {"page": "log"},
        }

    with patch("langgraph.config.get_stream_writer", return_value=_FakeWriter()):
        middleware = ToolEventMiddleware()
        result = middleware.wrap_tool_call(_Request(), lambda _r: "result")

    assert result == "result"
    assert events[0] == {
        "type": "tool_start",
        "id": "call-1",
        "name": "get_page_context",
        "args": {"text": '{"page": "log"}', "truncated": False},
    }
    assert events[1]["id"] == "call-1"
    assert events[1]["status"] == "done"
    assert events[1]["output"]["text"] == "result"
    assert events[1]["elapsed_ms"] >= 0


def test_chat_stream_endpoint_sse(client):
    import json as _json

    class _FakePart:
        def __init__(self, data):
            self.data = data

    def _fake_astream(self, _input, **_kwargs):
        async def _gen():
            yield {
                "type": "custom",
                "data": {
                    "type": "tool_start",
                    "name": "get_page_context",
                    "args": "log",
                },
            }
            from langchain_core.messages import AIMessageChunk

            yield {
                "type": "messages",
                "data": (AIMessageChunk(content="Salut"), {"langgraph_node": "model"}),
            }

        return _gen()

    with patch("langgraph.graph.state.CompiledStateGraph.astream", _fake_astream):
        response = client.post(
            "/agent/chat/stream",
            json={"messages": [{"role": "user", "content": "salut"}], "page": "log"},
        )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    events = [
        _json.loads(line[6:])
        for line in response.text.split("\n")
        if line.startswith("data: ")
    ]
    types = [e["type"] for e in events]
    assert types == ["tool_start", "token", "done"]
    assert events[1]["text"] == "Salut"


def test_chat_stream_endpoint_error_event(client):
    import json as _json

    def _fake_astream(self, _input, **_kwargs):
        async def _gen():
            raise RuntimeError("boom")
            yield  # pragma: no cover

        return _gen()

    with patch("langgraph.graph.state.CompiledStateGraph.astream", _fake_astream):
        response = client.post(
            "/agent/chat/stream",
            json={"messages": [{"role": "user", "content": "salut"}]},
        )
    assert response.status_code == 200  # error rides an SSE event, not the status
    events = [
        _json.loads(line[6:])
        for line in response.text.split("\n")
        if line.startswith("data: ")
    ]
    assert events[-1]["type"] == "error"
    assert "boom" in events[-1]["detail"]


# ---------------------------------------------------------------------------
# Provider mapping
# ---------------------------------------------------------------------------


class TestBuildChatModel:
    """Every provider `.env.example` documents must build, or the agent 500s."""

    def test_ollama_is_the_default(self, monkeypatch):
        from arete.agent.models.providers import build_chat_model

        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        monkeypatch.delenv("LLM_MODEL", raising=False)
        assert build_chat_model().openai_api_base.startswith("http")

    @staticmethod
    def _payload(model):
        # Exercise tool binding: the router needs the schemas to select a
        # capable model.
        with patch.object(model.client.with_raw_response, "create") as create:
            create.return_value.headers = {}
            create.return_value.parse.return_value = {
                "choices": [{"message": {"role": "assistant", "content": "OK"}}],
                "model": "selected/model",
            }
            model.bind_tools([get_page_context]).invoke("Hello")
        return create.call_args.kwargs

    @staticmethod
    def _openrouter(monkeypatch, model=None, fallbacks=None):
        monkeypatch.setenv("LLM_PROVIDER", "openrouter")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
        for name, value in (("LLM_MODEL", model), ("LLM_MODEL_FALLBACKS", fallbacks)):
            if value is None:
                monkeypatch.delenv(name, raising=False)
            else:
                monkeypatch.setenv(name, value)

    @pytest.mark.parametrize("configured_model", [None, ""])
    def test_openrouter_default_sends_its_fallback_list(
        self, monkeypatch, configured_model
    ):
        from arete.agent.models.providers import build_chat_model
        from arete.agent.models.registry import (
            DEFAULT_OPENROUTER_FALLBACKS,
            DEFAULT_OPENROUTER_MODEL,
        )

        self._openrouter(monkeypatch, configured_model)
        model = build_chat_model()
        assert model.openai_api_base == "https://openrouter.ai/api/v1"
        assert not model.default_headers
        payload = self._payload(model)
        assert payload["model"] == DEFAULT_OPENROUTER_MODEL
        assert payload["tools"][0]["function"]["name"] == "get_page_context"
        assert payload["extra_body"]["models"] == [
            DEFAULT_OPENROUTER_MODEL,
            *DEFAULT_OPENROUTER_FALLBACKS,
        ]
        assert payload["extra_body"]["models"][-1] == "openrouter/free"

    def test_a_pinned_model_is_never_rerouted_silently(self, monkeypatch):
        from arete.agent.models.providers import build_chat_model

        self._openrouter(monkeypatch, "custom/model:free")
        payload = self._payload(build_chat_model())
        assert payload["model"] == "custom/model:free"
        assert "models" not in (payload.get("extra_body") or {})

    def test_a_pinned_model_takes_explicit_fallbacks_in_order(self, monkeypatch):
        from arete.agent.models.providers import build_chat_model

        self._openrouter(monkeypatch, "a/one:free", "b/two:free, openrouter/free")
        payload = self._payload(build_chat_model())
        assert payload["extra_body"]["models"] == [
            "a/one:free",
            "b/two:free",
            "openrouter/free",
        ]

    def test_more_than_three_models_is_refused_before_any_request(self, monkeypatch):
        # OpenRouter answers HTTP 400 to a longer list.
        from arete.agent.models.providers import build_chat_model

        self._openrouter(monkeypatch, "a:free", "b:free,c:free,d:free")
        with pytest.raises(ValueError, match="3 models"):
            build_chat_model()

    def test_openrouter_without_a_key_is_actionable(self, monkeypatch):
        from arete.agent.models.providers import build_chat_model

        monkeypatch.setenv("LLM_PROVIDER", "openrouter")
        monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
        with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
            build_chat_model()

    def test_github_provider_builds(self, monkeypatch):
        # Documented in .env.example; it used to raise ValueError here while
        # working fine for the tips path.
        from arete.agent.models.providers import build_chat_model
        from arete.agent.models.registry import DEFAULT_GITHUB_MODEL

        monkeypatch.setenv("LLM_PROVIDER", "github")
        monkeypatch.setenv("GITHUB_TOKEN", "ghp_test")
        monkeypatch.delenv("LLM_MODEL", raising=False)
        model = build_chat_model()
        assert model.model_name == DEFAULT_GITHUB_MODEL
        assert "models.inference.ai.azure.com" in model.openai_api_base

    def test_github_without_a_token_is_actionable(self, monkeypatch):
        import pytest

        from arete.agent.models.providers import build_chat_model

        monkeypatch.setenv("LLM_PROVIDER", "github")
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        with pytest.raises(ValueError, match="GITHUB_TOKEN"):
            build_chat_model()

    def test_unknown_provider_lists_the_supported_ones(self, monkeypatch):
        import pytest

        from arete.agent.models.providers import build_chat_model

        monkeypatch.setenv("LLM_PROVIDER", "bedrock")
        with pytest.raises(ValueError, match="ollama, openrouter, github"):
            build_chat_model()


class TestPanelContextStaysOutOfState:
    """The page stamp is for the request, not for the conversation.

    `request.messages` IS the state's message list. Appending to it in place
    left a copy of the block behind on every model call: a three-turn run
    carried three identical stamps, re-sent to the model on every later turn
    and handed back to the client, growing with the conversation.
    """

    def test_the_caller_list_is_not_mutated(self):
        from arete.agent.middlewares.context import ContextBuilderMiddleware

        middleware = ContextBuilderMiddleware()
        request = _Request(
            messages=[HumanMessage("salut")],
            runtime=_Runtime(
                AgentContext(source={PANEL_CONTEXT_KEY: '{"page": "log"}'})
            ),
        )
        middleware.wrap_model_call(request, lambda r: "ok")
        assert len(request.messages) == 1

    def test_the_model_still_receives_it(self):
        from arete.agent.middlewares.context import ContextBuilderMiddleware

        middleware = ContextBuilderMiddleware()
        seen: list[int] = []

        def handler(req):
            seen.append(len(req.messages))
            assert "untrusted client data" in req.messages[-1].text
            return "ok"

        request = _Request(
            messages=[HumanMessage("salut")],
            runtime=_Runtime(
                AgentContext(source={PANEL_CONTEXT_KEY: '{"page": "log"}'})
            ),
        )
        middleware.wrap_model_call(request, handler)
        assert seen == [2]

    def test_two_turns_do_not_pile_up(self):
        from arete.agent.middlewares.context import ContextBuilderMiddleware

        middleware = ContextBuilderMiddleware()
        runtime = _Runtime(AgentContext(source={PANEL_CONTEXT_KEY: '{"page": "log"}'}))
        messages = [HumanMessage("salut")]
        counts: list[int] = []

        for _ in range(3):
            request = _Request(messages=messages, runtime=runtime)
            middleware.wrap_model_call(
                request, lambda r: counts.append(len(r.messages)) or "ok"
            )

        # One stamp per request, every time — never two, never three.
        assert counts == [2, 2, 2]
        assert len(messages) == 1


@pytest.mark.parametrize("endpoint", ["/agent/chat", "/agent/chat/stream"])
def test_chat_routes_preserve_thread_id(client, endpoint):
    from langchain_core.messages import AIMessage

    thread_id = "dfe771b8-661a-46af-9cee-dce80e6bc304"

    class Graph:
        async def ainvoke(self, state, *, context, config):
            assert context.thread_id == thread_id
            assert config["metadata"]["thread_id"] == thread_id
            return {"messages": [AIMessage(content="ok")]}

        async def astream(self, state, *, context, config, **kwargs):
            result = await self.ainvoke(state, context=context, config=config)
            yield {"type": "updates", "data": {"model": result}}

    with patch("arete.api.agent.get_agent", return_value=Graph()):
        response = client.post(
            endpoint,
            json={
                "messages": [{"role": "user", "content": "hi"}],
                "thread_id": thread_id,
            },
        )
    assert response.status_code == 200
    assert "ok" in response.text
    assert '"type": "error"' not in response.text


@pytest.mark.parametrize("endpoint", ["/agent/chat", "/agent/chat/stream"])
def test_chat_routes_reject_invalid_thread_id(client, endpoint):
    response = client.post(
        endpoint,
        json={
            "messages": [{"role": "user", "content": "hi"}],
            "thread_id": "not-a-uuid",
        },
    )
    assert response.status_code == 422


class TestPlanningPageRead:
    """The Planning page read is a window, not the whole plan.

    Read whole, a plan that runs months out overflowed the 32k bound — 109
    sessions on real data — and the tool answered with an error, so the coach
    on the Planning page could not see the plan at all.
    """

    def _plan(self, offsets_days):
        from datetime import date, timedelta

        from arete.garmin.models import PlannedSession, SessionType
        from arete.garmin.repository import GarminRepository

        repo = GarminRepository()
        today = date.today()
        return repo, [
            repo.create_planned_session(
                PlannedSession(
                    date=today + timedelta(days=offset),
                    sport="running",
                    session_type=SessionType.ENDURANCE,
                    description=f"offset {offset}",
                )
            )
            for offset in offsets_days
        ]

    def test_only_the_window_is_read(self):
        from arete.services.pages import PLANNING_AHEAD_DAYS, PLANNING_PAST_DAYS

        repo, ids = self._plan(
            [-(PLANNING_PAST_DAYS + 5), -2, 3, PLANNING_AHEAD_DAYS + 30]
        )
        try:
            out = json.loads(get_page_context.invoke({"page": "planning"}))
            seen = {row["description"] for row in out["planned_sessions"]}
        finally:
            for i in ids:
                repo.delete_planned_session(i)
        assert "offset -2" in seen and "offset 3" in seen
        assert f"offset {-(PLANNING_PAST_DAYS + 5)}" not in seen
        assert f"offset {PLANNING_AHEAD_DAYS + 30}" not in seen

    def test_rows_are_in_date_order_and_carry_no_nulls(self):
        repo, ids = self._plan([5, 1, 3])
        try:
            rows = json.loads(get_page_context.invoke({"page": "planning"}))[
                "planned_sessions"
            ]
        finally:
            for i in ids:
                repo.delete_planned_session(i)
        dates = [row["date"] for row in rows]
        assert dates == sorted(dates)
        assert all(value is not None for row in rows for value in row.values())

    def test_the_read_says_where_to_look_beyond_it(self):
        out = json.loads(get_page_context.invoke({"page": "planning"}))
        assert out["window"]["from"] < out["window"]["to"]
        assert "list_planned" in out["beyond_the_window"]


class TestAnalyticsPageRead:
    """The coach reads what each card says; the chart keeps its points.

    The daily series were 84 % of an Analytics read on real data. The agent
    reasons from the headline, the previous-period comparison and the card's
    insight, and asks the analytics toolkit when it needs a trend.
    """

    def test_the_agent_read_has_no_series(self):
        out = json.loads(get_page_context.invoke({"page": "analytics"}))
        cards = out["overview"]["cards"]
        assert cards, "no cards at all"
        assert all("series" not in card for card in cards.values())

    def test_what_each_card_says_is_kept(self):
        out = json.loads(get_page_context.invoke({"page": "analytics"}))
        for card in out["overview"]["cards"].values():
            assert "headline" in card

    def test_the_read_points_at_the_toolkit_for_trends(self):
        out = json.loads(get_page_context.invoke({"page": "analytics"}))
        assert "get_workload" in out["trends"]

    def test_the_page_itself_still_gets_its_series(self, client):
        # Trimming the agent's read must not touch the route the chart uses.
        cards = client.get("/analytics/overview?period=30d").json()["cards"]
        assert any("series" in card for card in cards.values())


class TestLedgerTools:
    """The journal's tools, described for a journal — and safe to append with."""

    def _tools(self):
        from arete.agent.backends.memory import build_memory_filesystem

        return {t.name: t for t in build_memory_filesystem().tools}

    def test_no_tool_can_delete_a_journal_file(self):
        # Rotation is the server's job; a delete could only lose data.
        assert "delete" not in self._tools()

    def test_reading_points_at_the_end_of_the_journal(self):
        """`read_file` reads 100 lines from the top; new entries are appended.

        Past 100 lines, a default read returns the oldest entries and misses
        the recent ones.
        """
        assert "fin" in self._tools()["read_file"].description

    def test_rewriting_the_journal_whole_is_warned_against(self):
        # Read 100 lines, rewrite with an entry appended, lose the rest.
        description = self._tools()["write_file"].description
        assert "sessions.md" in description and "edit_file" in description

    def test_appending_is_routed_to_edit_file(self):
        assert "ajouter" in self._tools()["edit_file"].description
