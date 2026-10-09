"""Tests for the toolkit middleware (progressive tool loading) + planning tools."""

from __future__ import annotations

import json
from datetime import date, timedelta

import pytest
from langchain_core.messages import SystemMessage

from arete.agent.capabilities.discovery import (
    _search_toolkits,
    loaded_toolkits,
    tool_instructions_suffix,
)
from arete.agent.capabilities.registry import CAPABILITIES, PLANNING_INSTRUCTIONS
from arete.agent.context.builder import _augment_tools
from arete.agent.middlewares.capabilities import ToolkitMiddleware
from arete.agent.middlewares.context import ContextBuilderMiddleware
from arete.agent.runtime.state import merge_loaded
from arete.agent.tools.planning import PLANNING_TOOLS
from arete.agent.tools.toolkits import _load


class _Runtime:
    """The two ToolRuntime fields load_toolkit reads. The real injection is
    covered by the full-graph tests at the bottom of this file."""

    def __init__(self, state=None):
        self.state = state if state is not None else {}
        self.tool_call_id = "call-1"


def load_toolkit(toolkit_id: str, state=None) -> dict:
    """Run the load_toolkit tool body, returning its Command state update."""
    return _load(_Runtime(state), toolkit_id).update


# ---------------------------------------------------------------------------
# Registry + search/load state machine
# ---------------------------------------------------------------------------


def test_planning_toolkit_registered():
    tk = CAPABILITIES["planning"]
    assert tk.id == "planning"
    assert {t.name for t in tk.tools} == {
        "list_planned",
        "create_planned_session",
        "update_planned_status",
        "delete_planned_session",
        "prepare_import",
        "inspect_import",
    }
    assert "planning" in tk.instructions.lower()


def test_search_finds_planning_by_capability():
    out = json.loads(_search_toolkits("planifier", []))
    assert out["results"][0]["toolkit_id"] == "planning"
    assert out["results"][0]["loaded"] is False


def test_search_unknown_returns_available_list():
    out = json.loads(_search_toolkits("cuisine italienne moleculaire", []))
    assert out["results"] == []
    assert any(a["toolkit_id"] == "planning" for a in out["available"])


def test_search_empty_query_returns_catalog():
    out = json.loads(_search_toolkits("", []))
    assert out["results"] == []
    assert any(a["toolkit_id"] == "planning" for a in out["available"])


def test_search_french_capability_finds_planning():
    # Token matching must bridge "planifier une séance" ↔ "créer… des séances"
    out = json.loads(_search_toolkits("planifier une séance", []))
    assert out["results"][0]["toolkit_id"] == "planning"


def test_load_returns_a_state_update_not_a_mutation():
    update = load_toolkit("planning")
    assert update["loaded_toolkits"] == ["planning"]
    assert json.loads(update["messages"][0].content)["loaded"] is True


def test_instructions_are_a_function_of_the_loaded_list():
    assert tool_instructions_suffix([]) == ""
    assert tool_instructions_suffix(["planning"]) == PLANNING_INSTRUCTIONS
    # An id no longer in the registry must not blow up the prompt.
    assert tool_instructions_suffix(["planning", "ghost"]) == PLANNING_INSTRUCTIONS


def test_load_unknown_toolkit_errors_without_touching_state():
    update = load_toolkit("nope")
    assert "loaded_toolkits" not in update
    assert "error" in json.loads(update["messages"][0].content)


def test_merge_loaded_dedups_parallel_loads():
    # Two load_toolkit calls in one turn must not pin the instructions twice.
    assert merge_loaded(["planning"], ["planning"]) == ["planning"]
    assert merge_loaded(["planning"], ["strength"]) == ["planning", "strength"]
    assert merge_loaded(None, None) == []


def test_loaded_toolkits_tolerates_a_state_without_the_key():
    assert loaded_toolkits({}) == []
    assert loaded_toolkits({"loaded_toolkits": None}) == []
    assert loaded_toolkits({"loaded_toolkits": ["planning"]}) == ["planning"]


def test_augment_tools_meta_always_present_and_deduped():
    out = _augment_tools([], [])
    names = [getattr(t, "name", "") for t in out]
    assert names.count("search_toolkits") == 1
    assert names.count("load_toolkit") == 1


def test_augment_tools_includes_loaded_toolkit_tools():
    out = _augment_tools([], ["planning"])
    names = {getattr(t, "name", "") for t in out}
    assert {"list_planned", "create_planned_session"} <= names


class _Request:
    """Minimal ModelRequest stand-in: the fields the middleware touches plus
    the immutable ``override`` contract it goes through."""

    def __init__(self, tools=None, system_message=None, state=None):
        self.tools = tools if tools is not None else []
        self.system_message = system_message
        self.state = state if state is not None else {}

    def override(self, **overrides):
        return _Request(
            tools=overrides.get("tools", self.tools),
            system_message=overrides.get("system_message", self.system_message),
            state=self.state,
        )


@pytest.mark.usefixtures("progressive_chat")
def test_toolkit_tools_not_in_primary_request_until_loaded():
    seen: list[list[str]] = []

    def capture(request):
        seen.append([getattr(t, "name", "") for t in request.tools])
        return "ok"

    ContextBuilderMiddleware().wrap_model_call(_Request(), capture)
    ContextBuilderMiddleware().wrap_model_call(
        _Request(state={"loaded_toolkits": ["planning"]}), capture
    )

    assert "create_planned_session" not in seen[0]
    assert "create_planned_session" in seen[1]
    # Meta-tools ride every request.
    assert "search_toolkits" in seen[0] and "load_toolkit" in seen[0]


def test_wrap_model_call_leaves_caller_request_untouched():
    # override() is the contract: the request the caller holds must not be
    # mutated (direct attribute assignment is deprecated in LangChain 1.x).
    request = _Request()
    ContextBuilderMiddleware().wrap_model_call(request, lambda r: "ok")
    assert request.tools == []


@pytest.mark.usefixtures("progressive_chat")
def test_two_interleaved_runs_keep_their_own_toolkits():
    """The reason the loaded set lives in graph state and not on the middleware.

    The compiled graph is process-wide (``get_agent`` is lru_cached) and two
    runs overlap easily — two tabs, or a /tips/daily refetch landing while the
    panel is mid-turn. With the set held on the middleware instance, one run's
    entry node wiped the other's toolkits between turns: the tool list and the
    pinned instructions silently shrank, and an already-emitted toolkit call
    fell through to the ToolNode ("not a valid tool") and burnt the turn
    budget on retries.

    One middleware instance, two states, interleaved: each must see only its
    own.
    """
    run_a = {"loaded_toolkits": ["planning"]}
    run_b: dict = {}
    seen: list[set[str]] = []

    def capture(request):
        seen.append({getattr(t, "name", "") for t in request.tools})
        return "ok"

    # A has planning, B starts bare, A takes another turn, B takes one.
    ContextBuilderMiddleware().wrap_model_call(_Request(state=run_a), capture)
    ContextBuilderMiddleware().wrap_model_call(_Request(state=run_b), capture)
    ContextBuilderMiddleware().wrap_model_call(_Request(state=run_a), capture)
    ContextBuilderMiddleware().wrap_model_call(_Request(state=run_b), capture)

    assert "create_planned_session" in seen[0]
    assert "create_planned_session" not in seen[1]
    # A kept its toolkit across B's turn — this is the assertion that fails
    # when the loaded set is instance state.
    assert "create_planned_session" in seen[2]
    assert "create_planned_session" not in seen[3]


@pytest.mark.usefixtures("progressive_chat")
def test_interleaved_runs_keep_their_own_instructions():
    seen: list[str] = []

    def capture(request):
        seen.append(request.system_message.text if request.system_message else "")
        return "ok"

    base = SystemMessage(content="Tu es le coach.")
    ContextBuilderMiddleware().wrap_model_call(
        _Request(system_message=base, state={"loaded_toolkits": ["planning"]}), capture
    )
    ContextBuilderMiddleware().wrap_model_call(
        _Request(system_message=base, state={}), capture
    )

    assert PLANNING_INSTRUCTIONS in seen[0]
    assert PLANNING_INSTRUCTIONS not in seen[1]


@pytest.mark.usefixtures("progressive_chat")
def test_pinned_instructions_reach_the_system_message_after_load():
    """The point of a toolkit: loading it must teach the model how to use it.

    Regression guard — carrying the loaded ids is not enough, the toolkit's
    instructions have to be appended to the system message of every later
    model call, without dropping the base prompt.
    """
    seen: list[str | None] = []

    def capture(request):
        seen.append(request.system_message.text if request.system_message else None)
        return "ok"

    base = SystemMessage(content="Tu es le coach.")
    ContextBuilderMiddleware().wrap_model_call(_Request(system_message=base), capture)
    ContextBuilderMiddleware().wrap_model_call(
        _Request(system_message=base, state={"loaded_toolkits": ["planning"]}), capture
    )

    # Before loading: base prompt + current catalog, no detailed instructions.
    assert seen[0].startswith("Tu es le coach.")
    assert "Skills disponibles" in seen[0]
    assert PLANNING_INSTRUCTIONS not in seen[0]
    # After: the base prompt is kept and the instructions appended, not replaced.
    assert seen[1].startswith("Tu es le coach.")
    assert PLANNING_INSTRUCTIONS in seen[1]


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

    from arete.agent.backends.memory import build_memory_filesystem
    from arete.agent.runtime.context import AgentContext
    from arete.agent.tools.pages import get_page_context

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
        middleware=[middleware, build_memory_filesystem(), ContextBuilderMiddleware()],
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
    """Dates here are relative and cleaned up on the way out.

    The suite shares one database. A row left behind on a hard-coded date is
    invisible until that day arrives, and then it breaks a test in another
    file — `test_summary_counts_only_due_sessions` counted it as due the
    morning of 2026-09-25.
    """
    from arete.agent.tools.planning import (
        create_planned_session,
        delete_planned_session,
        list_planned,
    )

    day = (date.today() + timedelta(days=400)).isoformat()
    out = json.loads(
        create_planned_session.invoke(
            {
                "date_str": day,
                "session_type": "tempo",
                "description": "6x3' au seuil",
                "sport": "running",
                "target_duration_min": 60,
            }
        )
    )
    try:
        assert out["created"] is True
        assert out["session"]["source"] == "coach"

        listing = json.loads(list_planned.invoke({"end_date": day}))
        assert listing["count"] >= 1
        assert any(s["id"] == out["session"]["id"] for s in listing["sessions"])
    finally:
        delete_planned_session.invoke({"session_id": out["session"]["id"]})


def test_create_planned_rejects_bad_type():
    from arete.agent.tools.planning import create_planned_session

    out = json.loads(
        create_planned_session.invoke(
            {"date_str": "2099-01-05", "session_type": "yoga_hot"}
        )
    )
    assert "error" in out


def test_update_and_delete_planned():
    from arete.agent.tools.planning import (
        create_planned_session,
        delete_planned_session,
        update_planned_status,
    )

    created = json.loads(
        create_planned_session.invoke(
            {"date_str": "2099-01-06", "session_type": "recovery"}
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
        t.name for t in CAPABILITIES["planning"].tools
    }


def test_full_graph_async_path_executes_toolkit_tools():
    """Same flow over astream/ainvoke — guards the sync-handler-in-async-chain
    coroutine bug ("Unsupported message type: <class 'coroutine'>")."""
    import asyncio

    from langchain.agents import create_agent
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage

    from arete.agent.backends.memory import build_memory_filesystem
    from arete.agent.middlewares.events import ToolEventMiddleware
    from arete.agent.runtime.context import AgentContext
    from arete.agent.tools.pages import get_page_context

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
                ContextBuilderMiddleware(),
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
