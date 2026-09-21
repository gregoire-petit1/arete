"""Analytics toolkit: narrow reads over the existing metrics/analytics routes.

The routes carry their bounds in FastAPI ``Query`` metadata, which does
nothing when the function is called directly — so the tools must validate
their own arguments, and these tests are what say they do.
"""

from __future__ import annotations

import json

from arete.agent.analytics_tools import (
    ANALYTICS_INSTRUCTIONS,
    ANALYTICS_TOOLS,
    get_fitness,
    get_personal_records,
    get_training_advice,
    get_workload,
    list_recent_sessions,
)
from arete.agent.toolkit_middleware import _TOOLKIT_REGISTRY

# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def test_analytics_toolkit_registered():
    tk = _TOOLKIT_REGISTRY["analytics"]
    assert {t.name for t in tk.tools} == {
        "get_workload",
        "get_fitness",
        "get_training_advice",
        "get_personal_records",
        "list_recent_sessions",
    }
    assert tk.instructions == ANALYTICS_INSTRUCTIONS


def test_tool_names_match_the_registry():
    assert {t.name for t in ANALYTICS_TOOLS} == {
        t.name for t in _TOOLKIT_REGISTRY["analytics"].tools
    }


def test_every_tool_documents_itself():
    # The description is the only thing the model sees when picking a tool.
    for tool in ANALYTICS_TOOLS:
        assert tool.description and len(tool.description) > 40, tool.name


# ---------------------------------------------------------------------------
# Reads against the (empty) test database — they must answer, not raise
# ---------------------------------------------------------------------------


def test_workload_reads_the_default_window():
    out = json.loads(get_workload.invoke({}))
    assert "acwr" in out and "days_analyzed" in out


def test_fitness_reads_the_default_window():
    out = json.loads(get_fitness.invoke({}))
    assert {"ctl", "atl", "tsb", "form_zone"} <= set(out)


def test_two_windows_are_comparable():
    # The point of the toolkit: the same metric over two periods, which the
    # fixed 30-day page dump cannot give.
    short = json.loads(get_workload.invoke({"days": 7}))
    long = json.loads(get_workload.invoke({"days": 90}))
    assert "acwr" in short and "acwr" in long


def test_advice_answers_even_without_data():
    out = json.loads(get_training_advice.invoke({}))
    assert "risk_level" in out and isinstance(out["recommendations"], list)


def test_records_answer_shape():
    out = json.loads(get_personal_records.invoke({}))
    assert isinstance(out, dict)


def test_recent_sessions_answer_shape():
    out = json.loads(list_recent_sessions.invoke({"limit": 5}))
    assert isinstance(out["sessions"], list)


# ---------------------------------------------------------------------------
# Bounds — the routes' Query metadata does not apply to a direct call
# ---------------------------------------------------------------------------


def test_workload_rejects_a_window_outside_the_route_bounds():
    assert "error" in json.loads(get_workload.invoke({"days": 5}))
    assert "error" in json.loads(get_workload.invoke({"days": 400}))


def test_fitness_rejects_a_window_outside_the_route_bounds():
    assert "error" in json.loads(get_fitness.invoke({"days": 3}))
    assert "error" in json.loads(get_fitness.invoke({"days": 500}))


def test_advice_rejects_an_unknown_sport_type():
    out = json.loads(get_training_advice.invoke({"sport_type": "yoga"}))
    assert "error" in out


def test_recent_sessions_rejects_bad_paging():
    assert "error" in json.loads(list_recent_sessions.invoke({"limit": 0}))
    assert "error" in json.loads(list_recent_sessions.invoke({"limit": 5000}))
    assert "error" in json.loads(list_recent_sessions.invoke({"offset": -1}))


def test_errors_never_raise_out_of_a_tool():
    # A failing read must reach the model as an error payload, not kill the run.
    import arete.api.metrics as metrics

    original = metrics.get_workload_metrics
    metrics.get_workload_metrics = lambda days: (_ for _ in ()).throw(
        RuntimeError("duckdb is away")
    )
    try:
        out = json.loads(get_workload.invoke({"days": 28}))
    finally:
        metrics.get_workload_metrics = original
    assert out["error"].startswith("RuntimeError")


def test_oversized_result_degrades_to_an_error_not_a_truncation():
    import arete.agent.analytics_tools as mod

    original = mod.MAX_TOOL_OUTPUT_CHARS
    mod.MAX_TOOL_OUTPUT_CHARS = 10
    try:
        out = json.loads(get_workload.invoke({"days": 28}))
    finally:
        mod.MAX_TOOL_OUTPUT_CHARS = original
    assert "too large" in out["error"]


# ---------------------------------------------------------------------------
# Through the graph: search -> load -> use, on the async path the panel uses
# ---------------------------------------------------------------------------


def test_full_graph_search_load_then_read():
    from langchain.agents import create_agent
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage

    from arete.agent.context import AgentContext
    from arete.agent.toolkit_middleware import ToolkitMiddleware
    from arete.agent.tools import get_page_context

    class FakeToolModel(GenericFakeChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    def call(name, args, call_id):
        return AIMessage(
            content="",
            tool_calls=[
                {"name": name, "args": args, "id": call_id, "type": "tool_call"}
            ],
        )

    messages = iter(
        [
            call("search_toolkits", {"query": "analyser la charge"}, "1"),
            call("load_toolkit", {"toolkit_id": "analytics"}, "2"),
            call("get_workload", {"days": 14}, "3"),
            AIMessage(content="Ta charge est stable."),
        ]
    )
    graph = create_agent(
        FakeToolModel(messages=messages),
        tools=[get_page_context],
        middleware=[ToolkitMiddleware()],
        system_prompt="t",
        context_schema=AgentContext,
    )
    result = graph.invoke(
        {"messages": [{"role": "user", "content": "ma charge ?"}]},
        context=AgentContext(source={}),
        config={"recursion_limit": 12},
    )

    assert result["loaded_toolkits"] == ["analytics"]
    contents = [m.content for m in result["messages"] if m.type == "tool"]
    assert json.loads(contents[0])["results"][0]["toolkit_id"] == "analytics"
    assert json.loads(contents[1])["loaded"] is True
    # The toolkit tool ran: the ToolNode does not know it, the middleware does.
    assert "acwr" in json.loads(contents[2])


def test_loading_analytics_leaves_planning_out_of_the_request():
    # Progressive loading still holds with two toolkits registered.
    from arete.agent.toolkit_middleware import _augment_tools

    names = {getattr(t, "name", "") for t in _augment_tools([], ["analytics"])}
    assert "get_workload" in names
    assert "create_planned_session" not in names
