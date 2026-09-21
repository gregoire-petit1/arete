"""Tests for the coaching agent (graph mocked — no network)."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from arete.agent.api import ChatRequest, _panel_context_source
from arete.agent.context import (
    MAX_PANEL_CONTEXT_CHARS,
    PANEL_CONTEXT_KEY,
    AgentContext,
)
from arete.agent.middlewares import RuntimeContextMiddleware, _panel_context_message
from arete.agent.tools import get_page_context

# ---------------------------------------------------------------------------
# Unit: context + middleware injection contract
# ---------------------------------------------------------------------------


class _Runtime:
    def __init__(self, context):
        self.context = context


class _Request:
    """Minimal ModelRequest stand-in: only ``runtime`` is read."""

    def __init__(self, context):
        self.runtime = _Runtime(context)


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
    ctx = AgentContext(source={PANEL_CONTEXT_KEY: json.dumps({"page": "log", "d": oversized})})
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
        _panel_context_source(ChatRequest(messages=[{"role": "user", "content": "hi"}], page="nope"))


def test_source_writer_rejects_oversized_payload():
    body = ChatRequest(
        messages=[{"role": "user", "content": "hi"}],
        panel_context={"blob": "x" * (MAX_PANEL_CONTEXT_CHARS + 1)},
    )
    with pytest.raises(Exception, match="over budget"):
        _panel_context_source(body)


def test_source_writer_merges_page_and_freeform():
    source = _panel_context_source(
        ChatRequest(messages=[{"role": "user", "content": "hi"}], page="log", panel_context={"x": 1})
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


@pytest.mark.parametrize("page", ["dashboard", "analytics", "planning", "log", "settings"])
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
        def invoke(self, state, *, context=None, config=None):
            assert config["recursion_limit"] > 0
            assert isinstance(context, AgentContext)
            return {"messages": [state["messages"][-1], _FakeFinal()]}

    with patch("arete.agent.api.get_agent", return_value=_FakeGraph()):
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
    middleware = RuntimeContextMiddleware()

    class _Bare:
        pass

    request = _Bare()
    sentinel = "ok"
    result = middleware.wrap_model_call(request, lambda _r: sentinel)
    assert result == sentinel


# ---------------------------------------------------------------------------
# Streaming endpoint + tool events
# ---------------------------------------------------------------------------


def test_tool_event_middleware_emits_start_and_end():
    from arete.agent.middlewares import ToolEventMiddleware

    events: list[dict] = []

    class _FakeWriter:
        def __call__(self, event):
            events.append(event)

    class _Request:
        tool_call = {"name": "get_page_context", "args": {"page": "log"}}

    with patch("langgraph.config.get_stream_writer", return_value=_FakeWriter()):
        middleware = ToolEventMiddleware()
        result = middleware.wrap_tool_call(_Request(), lambda _r: "result")

    assert result == "result"
    assert events == [
        {"type": "tool_start", "name": "get_page_context", "args": "log"},
        {"type": "tool_end", "name": "get_page_context"},
    ]


def test_chat_stream_endpoint_sse(client):
    import json as _json

    class _FakePart:
        def __init__(self, data):
            self.data = data

    def _fake_astream(self, _input, **_kwargs):
        async def _gen():
            yield {"type": "custom", "data": {"type": "tool_start", "name": "get_page_context", "args": "log"}}
            from langchain_core.messages import AIMessageChunk

            yield {"type": "messages", "data": (AIMessageChunk(content="Salut"), {"langgraph_node": "model"})}

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
