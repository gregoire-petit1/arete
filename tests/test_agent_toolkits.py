"""Tests for the toolkit middleware (progressive tool loading) + planning tools."""

from __future__ import annotations

import json

from langchain_core.messages import SystemMessage

from arete.agent.planning_tools import PLANNING_INSTRUCTIONS, PLANNING_TOOLS
from arete.agent.toolkit_middleware import (
    _TOOLKIT_REGISTRY,
    ToolkitMiddleware,
    _augment_tools,
    _load_toolkit,
    _search_toolkits,
)
from arete.agent.toolkits import _ToolkitRuntimeState

# ---------------------------------------------------------------------------
# Registry + search/load state machine
# ---------------------------------------------------------------------------


def test_planning_toolkit_registered():
    tk = _TOOLKIT_REGISTRY["planning"]
    assert tk.id == "planning"
    assert {t.name for t in tk.tools} == {
        "list_planned",
        "create_planned_session",
        "update_planned_status",
        "delete_planned_session",
    }
    assert "planning" in tk.instructions.lower()


def test_search_finds_planning_by_capability():
    state = _ToolkitRuntimeState()
    out = json.loads(_search_toolkits("planifier", state))
    assert out["results"][0]["toolkit_id"] == "planning"
    assert out["results"][0]["loaded"] is False


def test_search_unknown_returns_available_list():
    state = _ToolkitRuntimeState()
    out = json.loads(_search_toolkits("cuisine italienne moleculaire", state))
    assert out["results"] == []
    assert any(a["toolkit_id"] == "planning" for a in out["available"])


def test_search_empty_query_returns_catalog():
    state = _ToolkitRuntimeState()
    out = json.loads(_search_toolkits("", state))
    assert out["results"] == []
    assert any(a["toolkit_id"] == "planning" for a in out["available"])


def test_search_french_capability_finds_planning():
    # Token matching must bridge "planifier une séance" ↔ "créer… des séances"
    state = _ToolkitRuntimeState()
    out = json.loads(_search_toolkits("planifier une séance", state))
    assert out["results"][0]["toolkit_id"] == "planning"


def test_load_marks_loaded_and_pins_instructions():
    state = _ToolkitRuntimeState()
    out = json.loads(_load_toolkit("planning", state))
    assert out["loaded"] is True
    assert "planning" in state.loaded
    assert state.pinned_instructions == [PLANNING_INSTRUCTIONS]


def test_load_unknown_toolkit_errors():
    state = _ToolkitRuntimeState()
    out = json.loads(_load_toolkit("nope", state))
    assert "error" in out


def test_augment_tools_meta_always_present_and_deduped():
    middleware = ToolkitMiddleware()
    out = _augment_tools([], middleware.tools, middleware._state)
    names = [getattr(t, "name", "") for t in out]
    assert names.count("search_toolkits") == 1
    assert names.count("load_toolkit") == 1


def test_augment_tools_includes_loaded_toolkit_tools():
    middleware = ToolkitMiddleware()
    _load_toolkit("planning", middleware._state)
    out = _augment_tools([], middleware.tools, middleware._state)
    names = {getattr(t, "name", "") for t in out}
    assert {"list_planned", "create_planned_session"} <= names


def test_middleware_before_agent_resets_state_in_place():
    middleware = ToolkitMiddleware()
    middleware._state.loaded.add("planning")
    state_before = middleware._state
    middleware.before_agent({})
    # In-place reset: the meta-tools close over this exact object, so the
    # identity must survive the reset.
    assert middleware._state is state_before
    assert middleware._state.loaded == set()


class _Request:
    """Minimal ModelRequest stand-in: the fields the middleware touches plus
    the immutable ``override`` contract it goes through."""

    def __init__(self, tools=None, system_message=None):
        self.tools = tools if tools is not None else []
        self.system_message = system_message

    def override(self, **overrides):
        return _Request(
            tools=overrides.get("tools", self.tools),
            system_message=overrides.get("system_message", self.system_message),
        )


def test_toolkit_tools_not_in_primary_request_until_loaded():
    # Simulate two model calls in one run: before load, planning tools absent;
    # after load_toolkit, they are bound.
    middleware = ToolkitMiddleware()

    seen: list[list[str]] = []

    def handler_a(request):
        seen.append([getattr(t, "name", "") for t in request.tools])
        # The agent calls load_toolkit during this turn: mutate state, then
        # the next model call (same handler chain) sees the toolkit.
        _load_toolkit("planning", middleware._state)
        return "ok"

    middleware.wrap_model_call(_Request(), handler_a)
    middleware.wrap_model_call(
        _Request(),
        lambda r: seen.append([getattr(t, "name", "") for t in r.tools]) or "ok",
    )

    assert "create_planned_session" not in seen[0]
    assert "create_planned_session" in seen[1]
    # Meta-tools ride every request.
    assert "search_toolkits" in seen[0] and "load_toolkit" in seen[0]


def test_wrap_model_call_leaves_caller_request_untouched():
    # override() is the contract: the request the caller holds must not be
    # mutated (direct attribute assignment is deprecated in LangChain 1.x).
    middleware = ToolkitMiddleware()
    request = _Request()
    middleware.wrap_model_call(request, lambda r: "ok")
    assert request.tools == []


def test_pinned_instructions_reach_the_system_message_after_load():
    """The point of a toolkit: loading it must teach the model how to use it.

    Regression guard — pinning the instructions in state is not enough, they
    have to be appended to the system message of every later model call.
    """
    middleware = ToolkitMiddleware()
    seen: list[str | None] = []

    def capture(request):
        seen.append(request.system_message.text if request.system_message else None)
        return "ok"

    base = SystemMessage(content="Tu es le coach.")
    middleware.wrap_model_call(_Request(system_message=base), capture)
    _load_toolkit("planning", middleware._state)
    middleware.wrap_model_call(_Request(system_message=base), capture)

    # Before the load: untouched system message, no planning instructions.
    assert seen[0] == "Tu es le coach."
    # After: the base prompt is kept and the instructions appended, not replaced.
    assert seen[1].startswith("Tu es le coach.")
    assert PLANNING_INSTRUCTIONS in seen[1]


def test_before_agent_unpins_instructions_for_the_next_request():
    middleware = ToolkitMiddleware()
    _load_toolkit("planning", middleware._state)
    middleware.before_agent({})

    seen: list[str | None] = []
    middleware.wrap_model_call(
        _Request(system_message=SystemMessage(content="Tu es le coach.")),
        lambda r: seen.append(r.system_message.text) or "ok",
    )
    assert seen[0] == "Tu es le coach."


def test_full_graph_load_then_execute_planning():
    """End-to-end through create_agent: load_toolkit then a toolkit tool.

    Guards the two wiring traps found the hard way:
    - toolkit tools added to request.tools reach the model but NOT the
      ToolNode — wrap_tool_call must execute them (request.override pattern);
    - the meta-tools and the middleware state must close over ONE state
      object, or 'loaded' silently diverges from 'bound'.
    """
    from langchain.agents import create_agent
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage

    from arete.agent.context import AgentContext
    from arete.agent.filesystem import build_memory_filesystem
    from arete.agent.tools import get_page_context

    class FakeToolModel(GenericFakeChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    middleware = ToolkitMiddleware()
    messages = iter(
        [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "load_toolkit",
                        "args": {"toolkit_id": "planning"},
                        "id": "1",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "create_planned_session",
                        "args": {
                            "date_str": "2099-01-15",
                            "session_type": "tempo",
                            "target_duration_min": 45,
                        },
                        "id": "2",
                        "type": "tool_call",
                    }
                ],
            ),
            AIMessage(content="Séance planifiée."),
        ]
    )
    graph = create_agent(
        FakeToolModel(messages=messages),
        tools=[get_page_context],
        middleware=[middleware, build_memory_filesystem()],
        system_prompt="t",
        context_schema=AgentContext,
    )
    result = graph.invoke(
        {"messages": [{"role": "user", "content": "planifie"}]},
        context=AgentContext(source={}),
        config={"recursion_limit": 10},
    )
    tool_messages = [m for m in result["messages"] if m.type == "tool"]
    assert len(tool_messages) == 2
    assert '"loaded": true' in tool_messages[0].content
    assert '"created": true' in tool_messages[1].content


# ---------------------------------------------------------------------------
# Planning tools over the real repository (shared session test DB)
# ---------------------------------------------------------------------------


def test_create_and_list_planned():
    from arete.agent.planning_tools import create_planned_session, list_planned

    out = json.loads(
        create_planned_session.invoke(
            {
                "date_str": "2026-09-25",
                "session_type": "tempo",
                "description": "6x3' au seuil",
                "sport": "running",
                "target_duration_min": 60,
            }
        )
    )
    assert out["created"] is True
    assert out["session"]["source"] == "coach"

    listing = json.loads(list_planned.invoke({}))
    assert listing["count"] >= 1
    assert any(s["id"] == out["session"]["id"] for s in listing["sessions"])


def test_create_planned_rejects_bad_type():
    from arete.agent.planning_tools import create_planned_session

    out = json.loads(
        create_planned_session.invoke(
            {"date_str": "2026-09-25", "session_type": "yoga_hot"}
        )
    )
    assert "error" in out


def test_update_and_delete_planned():
    from arete.agent.planning_tools import (
        create_planned_session,
        delete_planned_session,
        update_planned_status,
    )

    created = json.loads(
        create_planned_session.invoke(
            {"date_str": "2026-09-26", "session_type": "recovery"}
        )
    )
    sid = created["session"]["id"]

    updated = json.loads(
        update_planned_status.invoke({"session_id": sid, "status": "skipped"})
    )
    assert updated["updated"] is True
    assert updated["session"]["status"] == "skipped"

    deleted = json.loads(delete_planned_session.invoke({"session_id": sid}))
    assert deleted["deleted"] is True

    missing = json.loads(delete_planned_session.invoke({"session_id": sid}))
    assert "error" in missing


def test_planning_tools_have_names_matching_registry():
    assert {t.name for t in PLANNING_TOOLS} == {
        t.name for t in _TOOLKIT_REGISTRY["planning"].tools
    }


def test_full_graph_async_path_executes_toolkit_tools():
    """Same flow over astream/ainvoke — guards the sync-handler-in-async-chain
    coroutine bug ("Unsupported message type: <class 'coroutine'>")."""
    import asyncio

    from langchain.agents import create_agent
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage

    from arete.agent.context import AgentContext
    from arete.agent.filesystem import build_memory_filesystem
    from arete.agent.middlewares import ToolEventMiddleware
    from arete.agent.tools import get_page_context

    class FakeToolModel(GenericFakeChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    async def run() -> list[str]:
        middleware = ToolkitMiddleware()
        messages = iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "load_toolkit",
                            "args": {"toolkit_id": "planning"},
                            "id": "1",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(
                    content="",
                    tool_calls=[
                        {
                            "name": "create_planned_session",
                            "args": {
                                "date_str": "2099-01-21",
                                "session_type": "endurance",
                                "target_duration_min": 30,
                            },
                            "id": "2",
                            "type": "tool_call",
                        }
                    ],
                ),
                AIMessage(content="Planifié."),
            ]
        )
        graph = create_agent(
            FakeToolModel(messages=messages),
            tools=[get_page_context],
            middleware=[
                middleware,
                ToolEventMiddleware(),
                build_memory_filesystem(),
            ],
            system_prompt="t",
            context_schema=AgentContext,
        )
        result = await graph.ainvoke(
            {"messages": [{"role": "user", "content": "planifie"}]},
            context=AgentContext(source={}),
            config={"recursion_limit": 10},
        )
        return [m.content for m in result["messages"] if m.type == "tool"]

    contents = asyncio.run(run())
    assert len(contents) == 2
    assert '"loaded": true' in contents[0]
    assert '"created": true' in contents[1]
