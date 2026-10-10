"""Fallback retries only model boundaries and preserves completed operations."""

import asyncio
from dataclasses import replace

import pytest
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage
from langchain_core.outputs import ChatGenerationChunk

from arete.agent.capabilities.registry import CAPABILITIES
from arete.agent.factory import build_agent
from arete.agent.profiles.catalog import get_profile
from arete.agent.runtime.context import AgentContext
from arete.agent.runtime.execution import invoke_agent, run_config, stream_agent
from arete.api.agent_streaming import StreamProjection


class Model(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        result = super()._generate(
            messages, stop=stop, run_manager=run_manager, **kwargs
        )
        if result.generations[0].message.content == "FAIL":
            raise ConnectionError("Provider unavailable")
        return result


def graph_for(primary, fallbacks, *, context_tokens=65536):
    return build_agent(
        replace(get_profile("chat"), journal_tools=False),
        model=Model(messages=iter(primary), disable_streaming=True),
        fallback_models=tuple(
            Model(messages=iter(items), disable_streaming=True) for items in fallbacks
        ),
        filesystem=AgentMiddleware(),
        context_tokens=context_tokens,
        output_tokens=4096,
    )


def run(graph, mode, context):
    state = {"messages": [HumanMessage("Effectue ma demande.")]}

    async def stream():
        projection = StreamProjection()
        async for part in stream_agent(graph, state, context=context):
            projection.events(part)
        return projection.done()["message"]["content"]

    if mode == "stream":
        return asyncio.run(stream())
    result = (
        asyncio.run(invoke_agent(graph, state, context=context))
        if mode == "async"
        else graph.invoke(state, context=context, config=run_config(context=context))
    )
    return result["messages"][-1].text


@pytest.mark.parametrize("mode", ["sync", "async", "stream"])
def test_fallback_after_write_does_not_replay_tool_and_counts_attempts(
    monkeypatch, mode
):
    writes = []
    writer = next(
        t for t in CAPABILITIES["planning"].tools if t.name == "create_planned_session"
    )
    monkeypatch.setattr(
        writer, "func", lambda **kwargs: writes.append(kwargs) or '{"id": 12}'
    )
    graph = graph_for(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_planned_session",
                        "args": {"date_str": "2099-01-01", "session_type": "tempo"},
                        "id": "write",
                    }
                ],
            ),
            AIMessage(content="FAIL"),
        ],
        [[AIMessage(content="Séance créée.")]],
    )
    context = AgentContext()
    assert run(graph, mode, context) == "Séance créée."
    assert len(writes) == 1
    assert context.stats.model_calls == 3
    assert context.stats.tool_calls == 1


@pytest.mark.parametrize("mode", ["sync", "async", "stream"])
def test_exhausted_fallbacks_propagate_last_error(mode):
    graph = graph_for(
        [AIMessage(content="FAIL")],
        [[AIMessage(content="FAIL")], [AIMessage(content="FAIL")]],
    )
    context = AgentContext()
    with pytest.raises(ConnectionError, match="Provider unavailable"):
        run(graph, mode, context)
    assert context.stats.model_calls == 3


def test_context_failure_does_not_call_any_candidate():
    graph = graph_for(
        [AIMessage(content="Unexpected")],
        [[AIMessage(content="Unexpected")]],
        context_tokens=8192,
    )
    context = AgentContext()
    with pytest.raises(ValueError, match="context|contexte|tokens"):
        graph.invoke(
            {"messages": [HumanMessage("large " * 30000)]},
            context=context,
            config=run_config(),
        )
    assert context.stats.model_calls == 0


def test_failed_partial_stream_does_not_pollute_the_final_answer():
    class Interrupted(Model):
        def _stream(self, messages, stop=None, run_manager=None, **kwargs):
            yield ChatGenerationChunk(
                message=AIMessageChunk(content="Réponse interrompue", id="failed")
            )
            raise ConnectionError("Stream interrupted")

    graph = build_agent(
        replace(get_profile("chat"), journal_tools=False),
        model=Interrupted(messages=iter([])),
        fallback_models=(
            Model(messages=iter([AIMessage(content="Réponse complète", id="success")])),
        ),
        filesystem=AgentMiddleware(),
        context_tokens=65536,
        output_tokens=4096,
    )
    context = AgentContext()
    assert run(graph, "stream", context) == "Réponse complète"
    assert context.stats.model_calls == 2


def test_cancellation_does_not_start_a_fallback():
    started = asyncio.Event()
    fallbacks = []

    class Cancelled(Model):
        async def _agenerate(self, messages, **kwargs):
            started.set()
            await asyncio.Event().wait()

    class Fallback(Model):
        def _generate(self, messages, *args, **kwargs):
            fallbacks.append(True)
            return super()._generate(messages, *args, **kwargs)

    graph = build_agent(
        replace(get_profile("chat"), journal_tools=False),
        model=Cancelled(messages=iter([]), disable_streaming=True),
        fallback_models=(Fallback(messages=iter([AIMessage(content="Unexpected")])),),
        filesystem=AgentMiddleware(),
        context_tokens=65536,
        output_tokens=4096,
    )

    async def cancel():
        async with asyncio.timeout(5):
            task = asyncio.create_task(
                invoke_agent(
                    graph,
                    {"messages": [HumanMessage("Vérifie.")]},
                    context=AgentContext(),
                )
            )
            await started.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task

    asyncio.run(cancel())
    assert not fallbacks
