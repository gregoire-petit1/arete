"""Protocol regressions: correlation, final snapshots, errors and prompt scope."""

import asyncio
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, AIMessageChunk, ToolMessage
from langgraph.types import Command

from arete.agent.middlewares import ToolEventMiddleware
from arete.agent.streaming import StreamProjection
from arete.agent.tool_events import MAX_TOOL_PREVIEW_CHARS, preview, tool_result_event


def token(text, message_id, **metadata):
    return {
        "type": "messages",
        "ns": (),
        "data": (
            AIMessageChunk(content=text, id=message_id),
            {"langgraph_node": "model", **metadata},
        ),
    }


def test_turns_are_separate_and_final_update_reconciles_tokens():
    stream = StreamProjection()
    assert stream.events(token("Je consulte.", "first"))[0]["id"] == "first"
    stream.events(token("**Bon", "answer"))
    stream.events(token("jour**", "answer"))
    update = {
        "type": "updates",
        "data": {
            "model": {"messages": [AIMessage(content="**Bonjour** !", id="answer")]}
        },
    }
    assert stream.events(update) == [
        {"type": "message", "id": "answer", "text": "**Bonjour** !"}
    ]
    assert stream.done()["message"]["content"] == "**Bonjour** !"
    assert stream.texts["first"] == "Je consulte."


def test_nonstreaming_provider_and_nested_messages():
    stream = StreamProjection()
    nested = token("Private subagent text", "child")
    nested["ns"] = ("tools:child",)
    assert stream.events(nested) == []
    stream.events(
        {
            "type": "updates",
            "data": {"model": {"messages": [AIMessage(content="Answer", id="root")]}},
        }
    )
    assert stream.done()["message"]["content"] == "Answer"


def test_empty_and_oversized_stream_fail_explicitly():
    stream = StreamProjection()
    with pytest.raises(ValueError, match="aucune réponse"):
        stream.done()
    with (
        patch("arete.agent.streaming.MAX_STREAM_TEXT_CHARS", 5),
        pytest.raises(ValueError, match="taille"),
    ):
        stream.events(token("Too long", "m"))


@pytest.mark.parametrize(
    "result",
    [
        ToolMessage(content='{"error":"Invalid date"}', tool_call_id="t"),
        ToolMessage(content="Failure", status="error", tool_call_id="t"),
        Command(
            update={
                "messages": [
                    ToolMessage(content='{"error":"Unknown toolkit"}', tool_call_id="t")
                ]
            }
        ),
        ToolMessage(content="Error: File missing", tool_call_id="t"),
    ],
)
def test_error_results_are_not_successful_tool_events(result):
    event = tool_result_event(result, call_id="t", name="tool", elapsed_ms=12)
    assert event["status"] == "error"
    assert event["id"] == "t"
    assert event["output"]["text"]


def test_preview_marks_omitted_content():
    result = preview("x" * (MAX_TOOL_PREVIEW_CHARS + 10))
    assert result["truncated"] is True
    assert len(result["text"]) == MAX_TOOL_PREVIEW_CHARS


@pytest.mark.parametrize("async_mode", [False, True])
def test_tool_exception_emits_failure_and_propagates(async_mode):
    events = []
    request = SimpleNamespace(tool_call={"id": "t", "name": "tool", "args": {}})

    def fail(_request):
        raise RuntimeError("Failed operation")

    async def afail(_request):
        return fail(_request)

    middleware = ToolEventMiddleware()
    with (
        patch("langgraph.config.get_stream_writer", return_value=events.append),
        pytest.raises(RuntimeError, match="Failed operation"),
    ):
        if async_mode:
            asyncio.run(middleware.awrap_tool_call(request, afail))
        else:
            middleware.wrap_tool_call(request, fail)
    assert [e["type"] for e in events] == ["tool_start", "tool_end"]
    assert events[-1]["status"] == "error"
    assert events[-1]["id"] == "t"


@pytest.mark.parametrize("async_mode", [False, True])
def test_system_skill_catalog_and_loaded_instructions_reach_every_model_call(
    monkeypatch, tmp_path, async_mode
):
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

    from arete.agent.agent import get_agent
    from arete.agent.context import AgentContext
    from arete.agent.system_skill import SYSTEM_SKILL
    from arete.agent.toolkit_middleware import _TOOLKIT_REGISTRY

    monkeypatch.setenv("ARETE_DB", str(tmp_path / "isolated.duckdb"))
    seen = []
    bound_tools = []

    class Model(GenericFakeChatModel):
        def bind_tools(self, tools, **kwargs):
            bound_tools.append({t.name for t in tools})
            return self

        def _generate(self, messages, *args, **kwargs):
            seen.append(messages[0].text)
            return super()._generate(messages, *args, **kwargs)

    model = Model(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "id": "load",
                            "name": "load_toolkit",
                            "args": {"toolkit_id": "analytics"},
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="Les outils sont prêts."),
            ]
        )
    )
    get_agent.cache_clear()
    try:
        with patch("arete.agent.agent.build_chat_model", return_value=model):
            graph = get_agent()
        args = ({"messages": [{"role": "user", "content": "Charge analytics"}]},)
        kwargs = {"context": AgentContext(source={}), "config": {"recursion_limit": 8}}
        if async_mode:
            asyncio.run(graph.ainvoke(*args, **kwargs))
        else:
            graph.invoke(*args, **kwargs)
    finally:
        get_agent.cache_clear()
    assert len(seen) == 2
    for prompt in seen:
        assert SYSTEM_SKILL in prompt
        assert prompt.count("Skills disponibles") == 1
        for tk in _TOOLKIT_REGISTRY.values():
            assert tk.description in prompt
    assert all("read_file" in tools for tools in bound_tools)
    assert _TOOLKIT_REGISTRY["analytics"].instructions not in seen[0]
    assert _TOOLKIT_REGISTRY["analytics"].instructions in seen[1]


def test_real_graph_sse_delivers_correlated_tools_and_final_snapshot(client):
    import json

    from langchain.agents import create_agent
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel

    from arete.agent.toolkit_middleware import ToolkitMiddleware

    class Model(GenericFakeChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    graph = create_agent(
        Model(
            # GenericFake streaming omits native tool_calls. Completed messages
            # exercise the same graph and the non-streaming-provider fallback.
            disable_streaming=True,
            messages=iter(
                [
                    AIMessage(
                        content="Je charge les outils.",
                        tool_calls=[
                            {
                                "id": "t1",
                                "name": "load_toolkit",
                                "args": {"toolkit_id": "analytics"},
                                "type": "tool_call",
                            }
                        ],
                    ),
                    AIMessage(content="## Prêt\n\n- **Analyser** ta forme."),
                ]
            ),
        ),
        middleware=[ToolEventMiddleware(), ToolkitMiddleware()],
    )
    with patch("arete.agent.execution.get_agent", return_value=graph):
        response = client.post(
            "/agent/chat/stream",
            json={"messages": [{"role": "user", "content": "Charge analytics"}]},
        )
    events = [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    starts = [e for e in events if e["type"] == "tool_start"]
    ends = [e for e in events if e["type"] == "tool_end"]
    assert len(starts) == len(ends) == 1, events
    assert starts[0]["id"] == ends[0]["id"] == "t1"
    assert ends[0]["status"] == "done"
    snapshots = [e for e in events if e["type"] == "message"]
    assert len(snapshots) == 2
    assert snapshots[0]["id"] != snapshots[1]["id"]
    assert events[-1]["message"]["content"] == "## Prêt\n\n- **Analyser** ta forme."
