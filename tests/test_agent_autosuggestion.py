"""Optional completion suggestions must never contaminate or fail an answer."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import ValidationError
from test_agent_execution import Model

from arete.agent.middlewares.autosuggestion import AutoSuggestionMiddleware
from arete.agent.nodes.suggestions import SuggestionGenerator, Suggestions
from arete.agent.runtime.context import AgentContext
from arete.agent.runtime.execution import invoke_agent


@pytest.mark.parametrize("async_mode", [False, True])
def test_suggestions_run_once_after_final_answer_and_stay_out_of_history(
    monkeypatch, async_mode
):
    model = SimpleNamespace(
        invoke=Mock(
            return_value=AIMessage(content='{"suggestions":["Quelle séance demain ?"]}')
        ),
        ainvoke=AsyncMock(
            return_value=AIMessage(content='{"suggestions":["Quelle séance demain ?"]}')
        ),
    )
    monkeypatch.setattr(SuggestionGenerator, "_model", lambda self: model)
    graph = create_agent(
        Model(messages=iter([AIMessage(content="Repos aujourd'hui.")])),
        middleware=[AutoSuggestionMiddleware(SuggestionGenerator(model=None))],
        context_schema=AgentContext,
    )
    state = {"messages": [HumanMessage("Ma forme ?")]}
    result = (
        asyncio.run(invoke_agent(graph, state, context=AgentContext()))
        if async_mode
        else graph.invoke(state, context=AgentContext())
    )
    assert result["suggestions"] == ["Quelle séance demain ?"]
    assert len(result["messages"]) == 2
    assert model.invoke.call_count + model.ainvoke.call_count == 1


@pytest.mark.parametrize("failure", [RuntimeError("unavailable"), TimeoutError()])
def test_optional_failure_preserves_final_answer(monkeypatch, failure):
    model = SimpleNamespace(ainvoke=AsyncMock(side_effect=failure))
    monkeypatch.setattr(SuggestionGenerator, "_model", lambda self: model)
    graph = create_agent(
        Model(messages=iter([AIMessage(content="Réponse conservée.")])),
        middleware=[AutoSuggestionMiddleware(SuggestionGenerator(model=None))],
        context_schema=AgentContext,
    )
    result = asyncio.run(
        invoke_agent(
            graph, {"messages": [HumanMessage("question")]}, context=AgentContext()
        )
    )
    assert result["messages"][-1].text == "Réponse conservée."
    assert result["suggestions"] == []


@pytest.mark.parametrize(
    "values", [[""], ["x" * 121], ["a", "b", "c", "d"], ["A", " a "]]
)
def test_malformed_suggestions_are_rejected(values):
    with pytest.raises(ValidationError):
        Suggestions(suggestions=values)


def test_no_optional_call_when_deadline_near_or_background():
    middleware = AutoSuggestionMiddleware(SuggestionGenerator(model=None))
    state = {"messages": [HumanMessage("q"), AIMessage(content="a")]}
    context = AgentContext()
    context.deadline = 0
    assert (
        middleware.generator._messages(state, SimpleNamespace(context=context)) is None
    )
    assert (
        middleware.generator._messages(
            state, SimpleNamespace(context=AgentContext(profile="briefing"))
        )
        is None
    )


def test_suggestions_are_projected_without_overwriting_answer():
    from arete.api.agent_streaming import StreamProjection

    projection = StreamProjection()
    event = {"type": "suggestions", "suggestions": ["Et demain ?"]}
    assert projection.events({"type": "custom", "data": event}) == [event]
    projection.events(
        {
            "type": "updates",
            "data": {"model": {"messages": [AIMessage(content="Réponse.")]}},
        }
    )
    assert projection.done()["message"]["content"] == "Réponse."


def test_sse_emits_suggestions_before_done_without_leaking_auxiliary_text(monkeypatch):
    import json

    from arete.api.agent import StreamRequest, _sse_stream

    monkeypatch.setattr(
        SuggestionGenerator,
        "_model",
        lambda self: Model(
            messages=iter([AIMessage(content='{"suggestions":["Et demain ?"]}')])
        ),
    )
    graph = create_agent(
        Model(messages=iter([AIMessage(content="Réponse du coach.")])),
        middleware=[AutoSuggestionMiddleware(SuggestionGenerator(model=None))],
        context_schema=AgentContext,
    )
    monkeypatch.setattr("arete.api.agent.get_agent", lambda: graph)

    async def run():
        return [
            json.loads(frame.removeprefix("data: "))
            async for frame in _sse_stream(
                StreamRequest(messages=[{"role": "user", "content": "Ma forme ?"}])
            )
        ]

    events = asyncio.run(run())
    assert events[-1]["type"] == "done"
    assert events[-1]["message"]["content"] == "Réponse du coach."
    assert [e for e in events if e["type"] == "suggestions"] == [
        {"type": "suggestions", "suggestions": ["Et demain ?"]}
    ]
    assert all(
        "suggestions" not in e.get("text", "")
        for e in events
        if e["type"] in {"token", "message"}
    )
