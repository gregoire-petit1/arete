"""The scrubber must redact journal/memory content without touching the model's copy."""

from __future__ import annotations

import asyncio
import json
from datetime import date

from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langsmith import Client

from arete.observability import scrubbing
from arete.observability.scrubbing import (
    REDACTED_TRUNCATED,
    Sensitive,
    scrub,
    sensitive,
)
from arete.services.athlete_facts import FACTS_HEADING
from arete.services.journal import JOURNAL_HEADING

FIXTURE_SENTENCE = "Sharp pain in the left knee after the long run, mood is low."


def test_sensitive_marker_is_redacted_by_label():
    assert scrub({"note": sensitive("journal", "secret")}) == {
        "note": "[REDACTED:journal]"
    }


def test_sensitive_marker_leaves_the_wrapped_value_untouched():
    marker = sensitive("journal", FIXTURE_SENTENCE)
    assert marker.value == FIXTURE_SENTENCE
    assert isinstance(marker, Sensitive)


def test_system_prompt_is_cut_at_the_journal_heading():
    prompt = f"Tu es Chiron.\n\nInstructions stables.\n\n{JOURNAL_HEADING}\n{FIXTURE_SENTENCE}"
    scrubbed = scrub({"messages": [[SystemMessage(prompt)]]})
    content = scrubbed["messages"][0][0].content
    assert content.startswith("Tu es Chiron.\n\nInstructions stables.\n\n")
    assert FIXTURE_SENTENCE not in content
    assert JOURNAL_HEADING not in content


def test_system_prompt_is_cut_at_the_earliest_of_facts_or_journal_heading():
    prompt = (
        f"Stable.\n\n{FACTS_HEADING}\nfact\n\n{JOURNAL_HEADING}\n{FIXTURE_SENTENCE}"
    )
    scrubbed = scrub({"messages": [[SystemMessage(prompt)]]})
    content = scrubbed["messages"][0][0].content
    assert content == "Stable.\n\n[REDACTED:personal_context]"


def test_serialized_system_message_is_also_cut_at_the_journal_heading():
    payload = {
        "messages": [
            [
                {
                    "kwargs": {
                        "content": f"Stable.\n\n{JOURNAL_HEADING}\n{FIXTURE_SENTENCE}",
                        "type": "system",
                    }
                }
            ]
        ]
    }
    scrubbed = scrub(payload)
    content = scrubbed["messages"][0][0]["kwargs"]["content"]
    assert FIXTURE_SENTENCE not in content
    assert content.startswith("Stable.\n\n")


def test_prompt_without_personal_sections_is_left_untouched():
    prompt = "Tu es Chiron.\n\nInstructions stables."
    scrubbed = scrub({"messages": [[SystemMessage(prompt)]]})
    assert scrubbed["messages"][0][0].content == prompt


def test_key_name_net_redacts_known_journal_fields():
    payload = {"title": "knee pain", "body": FIXTURE_SENTENCE, "day": "2026-01-01"}
    assert scrub(payload) == {
        "title": "[REDACTED:title]",
        "body": "[REDACTED:body]",
        "day": "2026-01-01",
    }


def test_key_name_net_reaches_nested_structures():
    payload = {"fact": {"id": 1, "kind": "injury", "text": FIXTURE_SENTENCE}}
    assert scrub(payload) == {
        "fact": {"id": 1, "kind": "injury", "text": "[REDACTED:text]"}
    }


def test_tool_name_net_redacts_the_whole_args_of_a_requested_tool_call():
    payload = {
        "tool_calls": [
            {"name": "append_journal", "args": {"title": "t", "body": FIXTURE_SENTENCE}}
        ]
    }
    scrubbed = scrub(payload)
    assert scrubbed["tool_calls"][0]["args"] == "[REDACTED:append_journal]"


def test_key_name_net_still_redacts_unlisted_tool_calls_by_field_name():
    payload = {"tool_calls": [{"name": "some_other_tool", "args": {"title": "t"}}]}
    scrubbed = scrub(payload)
    assert scrubbed["tool_calls"][0]["args"] == {"title": "[REDACTED:title]"}


def test_sensitive_tool_name_redacts_a_live_tool_message():
    message = ToolMessage(content=FIXTURE_SENTENCE, name="read_file", tool_call_id="r1")
    scrubbed = scrub({"output": message})
    assert scrubbed["output"].content == "[REDACTED:read_file]"
    assert message.content == FIXTURE_SENTENCE  # The original is never mutated.


def test_live_ai_message_requesting_a_sensitive_tool_has_its_args_redacted():
    message = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "append_journal",
                "args": {"title": "t", "body": FIXTURE_SENTENCE},
                "id": "c1",
                "type": "tool_call",
            }
        ],
    )
    scrubbed = scrub({"output": message})
    assert scrubbed["output"].tool_calls[0]["args"] == "[REDACTED:append_journal]"
    assert message.tool_calls[0]["args"]["body"] == FIXTURE_SENTENCE  # Unmutated.


def test_serialized_raw_provider_function_call_arguments_are_redacted():
    """A provider's raw tool call (additional_kwargs) carries its args as a
    JSON-encoded string under "arguments", a different field name than the
    normalized tool_calls LangChain also attaches."""
    payload = {
        "additional_kwargs": {
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {
                        "name": "append_journal",
                        "arguments": json.dumps(
                            {"title": "t", "body": FIXTURE_SENTENCE}
                        ),
                    },
                }
            ]
        }
    }
    scrubbed = scrub(payload)
    function = scrubbed["additional_kwargs"]["tool_calls"][0]["function"]
    assert function["arguments"] == "[REDACTED:append_journal]"


def test_live_ai_message_raw_additional_kwargs_tool_call_is_redacted():
    message = AIMessage(
        content="",
        additional_kwargs={
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {
                        "name": "remember_fact",
                        "arguments": json.dumps({"text": FIXTURE_SENTENCE}),
                    },
                }
            ]
        },
    )
    scrubbed = scrub({"output": message})
    function = scrubbed["output"].additional_kwargs["tool_calls"][0]["function"]
    assert function["arguments"] == "[REDACTED:remember_fact]"
    original_function = message.additional_kwargs["tool_calls"][0]["function"]
    assert FIXTURE_SENTENCE in original_function["arguments"]  # Unmutated.


def test_sensitive_tool_name_redacts_a_serialized_tool_message():
    payload = {
        "messages": [
            {
                "lc": 1,
                "type": "constructor",
                "id": ["langchain", "schema", "messages", "ToolMessage"],
                "kwargs": {"content": FIXTURE_SENTENCE, "name": "read_file"},
            }
        ]
    }
    scrubbed = scrub(payload)
    assert scrubbed["messages"][0]["kwargs"]["content"] == "[REDACTED:read_file]"


def test_unrelated_tool_output_is_not_redacted():
    message = ToolMessage(
        content="12 sessions this week", name="get_workload", tool_call_id="r1"
    )
    scrubbed = scrub({"output": message})
    assert scrubbed["output"].content == "12 sessions this week"


def test_bound_reached_on_depth_redacts_instead_of_raising():
    nested: dict = {"leaf": FIXTURE_SENTENCE}
    for _ in range(scrubbing.WALK_DEPTH_MAX + 5):
        nested = {"child": nested}
    scrubbed = scrub(nested)
    found = scrubbed
    while isinstance(found, dict) and "child" in found:
        found = found["child"]
    assert found == REDACTED_TRUNCATED


def test_bound_reached_on_node_count_redacts_instead_of_raising():
    payload = {str(i): FIXTURE_SENTENCE for i in range(scrubbing.WALK_NODES_MAX + 50)}
    scrubbed = scrub(payload)
    assert REDACTED_TRUNCATED in scrubbed.values()


def test_non_dict_payload_passes_through():
    assert scrub("not a dict") == "not a dict"


# --- Capture test: the real tool path, against a fixture journal. ---


def tool_call(name, args, call_id):
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id, "type": "tool_call"}],
    )


class FakeCoach(GenericFakeChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


def test_read_file_tool_path_leaves_no_fixture_sentence_in_the_scrubbed_trace(
    monkeypatch, tmp_path
):
    """Run the real journal write and read_file tool, scrub what langsmith would
    have received, and confirm the fixture sentence never survives, while
    confirming the model's own history still carries it unredacted."""
    from arete import coaching as agent
    from arete.agent.runtime import execution
    from arete.agent.runtime.context import AgentContext
    from arete.services.memory import append_entry

    monkeypatch.setenv("ARETE_DB", str(tmp_path / "agent.duckdb"))
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_MODEL", "test-coach")
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    from arete.dataio.init_duckdb import main as init_db

    init_db()
    append_entry("notes.md", "knee check", FIXTURE_SENTENCE, when=date(2026, 1, 1))
    agent.get_agent.cache_clear()

    model = FakeCoach(
        messages=iter(
            [
                tool_call("read_file", {"file_path": "/notes.md"}, "r1"),
                AIMessage(content="Finished."),
            ]
        )
    )
    monkeypatch.setattr(agent, "build_chat_model", lambda **kw: model)

    runs: dict[str, dict] = {}

    class CapturingClient(Client):
        def __init__(self):
            super().__init__(api_key="test-key", auto_batch_tracing=False)

        def create_run(self, name, inputs, run_type, **kwargs):
            runs[str(kwargs["id"])] = {
                "name": name,
                "run_type": run_type,
                "inputs": inputs,
            }

        def update_run(self, run_id, **kwargs):
            runs[str(run_id)].update(kwargs)

    from arete.observability import tracing

    monkeypatch.setattr(tracing, "_client", CapturingClient())
    monkeypatch.setenv("LANGSMITH_TRACING", "true")
    monkeypatch.setenv("LANGSMITH_API_KEY", "test-key")

    result = asyncio.run(
        execution.invoke_agent(
            agent.get_agent(),
            {"messages": [HumanMessage("hello")]},
            context=AgentContext(),
        )
    )
    assert result["messages"][-1].content == "Finished."

    # The read_file tool run itself: what would be sent to LangSmith for it,
    # scrubbed, carries no fixture sentence in either its args or its result.
    read_file_run = next(r for r in runs.values() if r["name"] == "read_file")
    scrubbed = {
        "inputs": scrub(read_file_run["inputs"]),
        "outputs": scrub(read_file_run["outputs"]),
    }
    assert FIXTURE_SENTENCE not in json.dumps(scrubbed, default=str)

    # The model's own history kept the real content, untouched.
    tool_message = next(
        m
        for m in result["messages"]
        if isinstance(m, ToolMessage) and m.name == "read_file"
    )
    assert FIXTURE_SENTENCE in tool_message.content

    # The context builder injects the journal into every system prompt; the
    # LLM run's own inputs carry it too, and must be scrubbed the same way.
    llm_run = next(r for r in runs.values() if r["run_type"] == "llm")
    scrubbed_llm_inputs = scrub(llm_run["inputs"])
    assert FIXTURE_SENTENCE not in json.dumps(scrubbed_llm_inputs, default=str)
