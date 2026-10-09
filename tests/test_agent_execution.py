"""Exercise runtime bounds and mission policy through actual compiled graphs."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool

from arete.agent.capabilities.registry import CAPABILITIES
from arete.agent.middlewares.capabilities import ToolkitMiddleware
from arete.agent.middlewares.context import ContextBuilderMiddleware
from arete.agent.middlewares.limits import ToolConcurrencyMiddleware, execution_limits
from arete.agent.runtime.budget import MAX_MODEL_CALLS, MAX_TOOL_CALLS
from arete.agent.runtime.context import AgentContext
from arete.agent.runtime.execution import (
    RUN_LIMIT_ERRORS,
    invoke_agent,
    run_config,
)


class Model(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def call(name, args, identifier="call"):
    return AIMessage(
        content="", tool_calls=[{"name": name, "args": args, "id": identifier}]
    )


@pytest.mark.parametrize("profile", ["briefing", "feedback"])
@pytest.mark.parametrize("async_mode", [False, True])
def test_background_cannot_load_or_execute_training_writes(
    profile, async_mode, monkeypatch
):
    # A forged loaded state must not authorize a background write.
    writer = CAPABILITIES["planning"].tools[1]
    invoked = []
    monkeypatch.setattr(writer, "func", lambda *a, **k: invoked.append(True))
    graph = create_agent(
        Model(
            messages=iter(
                [
                    call("load_toolkit", {"toolkit_id": "planning"}, "load"),
                    call(
                        "create_planned_session",
                        {"date_str": "2099-01-01", "session_type": "tempo"},
                    ),
                    AIMessage(content="Fin."),
                ]
            )
        ),
        middleware=[ToolkitMiddleware(), ContextBuilderMiddleware()],
        context_schema=AgentContext,
    )
    state = {"messages": [HumanMessage("planifie")], "loaded_toolkits": ["planning"]}
    kwargs = {"context": AgentContext(profile=profile), "config": run_config()}
    result = (
        asyncio.run(graph.ainvoke(state, **kwargs))
        if async_mode
        else graph.invoke(state, **kwargs)
    )
    assert not invoked
    assert all(m.status == "error" for m in result["messages"] if m.type == "tool")


@pytest.mark.usefixtures("progressive_chat")
def test_unloaded_tool_is_rejected_before_execution():
    graph = create_agent(
        Model(messages=iter([call("list_planned", {}), AIMessage(content="Fin.")])),
        middleware=[ToolkitMiddleware(), ContextBuilderMiddleware()],
        context_schema=AgentContext,
    )
    result = graph.invoke({"messages": [HumanMessage("lis")]}, context=AgentContext())
    message = next(m for m in result["messages"] if m.type == "tool")
    assert message.status == "error" and "Load toolkit" in message.content


@pytest.mark.parametrize("profile", ["briefing", "feedback"])
def test_missions_bind_no_tool(profile):
    """Facts in, text out: one model request, nothing to call."""
    seen = []

    class Capture(Model):
        def bind_tools(self, tools, **kwargs):
            seen.append({t.name for t in tools})
            return self

    graph = create_agent(
        Capture(messages=iter([AIMessage(content="Fin.")])),
        middleware=[ToolkitMiddleware(), ContextBuilderMiddleware()],
        context_schema=AgentContext,
    )
    graph.invoke(
        {"messages": [HumanMessage("faits")]}, context=AgentContext(profile=profile)
    )
    assert seen in ([], [set()])


def test_chat_binds_its_toolkits_without_a_loading_round():
    seen = []

    class Capture(Model):
        def bind_tools(self, tools, **kwargs):
            seen.append({t.name for t in tools})
            return self

    graph = create_agent(
        Capture(messages=iter([AIMessage(content="Fin.")])),
        middleware=[ToolkitMiddleware(), ContextBuilderMiddleware()],
        context_schema=AgentContext,
    )
    graph.invoke({"messages": [HumanMessage("ma forme ?")]}, context=AgentContext())
    assert {"get_workload", "list_planned", "read_workout"} <= seen[0]
    assert not {"load_toolkit", "search_toolkits"} & seen[0]


def test_model_budget_stops_loop():
    graph = create_agent(
        Model(
            messages=iter(
                [
                    call("search_toolkits", {"query": "analytics"}, str(i))
                    for i in range(MAX_MODEL_CALLS + 1)
                ]
            )
        ),
        middleware=[
            *execution_limits(),
            ToolkitMiddleware(),
            ContextBuilderMiddleware(),
        ],
        context_schema=AgentContext,
    )
    with pytest.raises(RUN_LIMIT_ERRORS):
        asyncio.run(
            invoke_agent(
                graph, {"messages": [HumanMessage("loop")]}, context=AgentContext()
            )
        )


def test_oversized_tool_batch_executes_nothing():
    executed = []

    @tool
    def record() -> str:
        """Record one execution."""
        executed.append(True)
        return "ok"

    message = AIMessage(
        content="",
        tool_calls=[
            {"name": "record", "args": {}, "id": str(i)}
            for i in range(MAX_TOOL_CALLS + 1)
        ],
    )
    graph = create_agent(
        Model(messages=iter([message])),
        tools=[record],
        middleware=execution_limits(),
        context_schema=AgentContext,
    )
    with pytest.raises(RUN_LIMIT_ERRORS):
        asyncio.run(
            invoke_agent(
                graph, {"messages": [HumanMessage("batch")]}, context=AgentContext()
            )
        )
    assert not executed


def test_deadline_cancels_provider_wait(monkeypatch):
    monkeypatch.setattr("arete.agent.runtime.execution.MAX_RUN_SECONDS", 0.01)
    cancelled = []

    async def stuck(*args, **kwargs):
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)

    with pytest.raises(TimeoutError):
        asyncio.run(
            invoke_agent(SimpleNamespace(ainvoke=stuck), {}, context=AgentContext())
        )
    assert cancelled


def test_async_tool_concurrency_is_bounded_and_contexts_are_independent():
    async def run():
        first, second = AgentContext(), AgentContext()
        assert first.tool_slots is not second.tool_slots
        middleware = ToolConcurrencyMiddleware()
        active = peak = 0

        async def handler(request):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.001)
            active -= 1

        request = SimpleNamespace(runtime=SimpleNamespace(context=first))
        await asyncio.gather(
            *(middleware.awrap_tool_call(request, handler) for _ in range(10))
        )
        assert peak == 4

    asyncio.run(run())


def test_chat_misconfiguration_is_an_actionable_error(router_client, monkeypatch):
    from arete.api.agent import router

    def fail():
        raise ValueError("Missing provider key")

    monkeypatch.setattr("arete.api.agent.get_agent", fail)
    response = router_client(router).post(
        "/agent/chat", json={"messages": [{"role": "user", "content": "hi"}]}
    )
    assert response.status_code == 500
    assert response.json()["detail"] == "Missing provider key"


def test_chat_timeout_is_504(router_client, monkeypatch):
    from arete.api.agent import router

    monkeypatch.setattr("arete.api.agent.get_agent", lambda: object())
    monkeypatch.setattr(
        "arete.api.agent.invoke_agent", AsyncMock(side_effect=TimeoutError)
    )
    response = router_client(router).post(
        "/agent/chat", json={"messages": [{"role": "user", "content": "hi"}]}
    )
    assert response.status_code == 504


def test_sync_workers_reuse_the_server_event_loop():
    from functools import partial

    import anyio

    from arete.agent.runtime.execution import invoke_agent_sync

    async def run():
        server_loop = asyncio.get_running_loop()
        seen = []

        async def invoke(*args, **kwargs):
            seen.append(asyncio.get_running_loop())
            return {"messages": []}

        graph = SimpleNamespace(ainvoke=invoke)
        for _ in range(2):
            await anyio.to_thread.run_sync(
                partial(invoke_agent_sync, graph, {}, context=AgentContext())
            )
        assert seen == [server_loop, server_loop]

    asyncio.run(run())
