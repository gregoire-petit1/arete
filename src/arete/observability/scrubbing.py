"""Bounded redaction of journal/memory content before it leaves to LangSmith.

LangSmith stores run inputs, outputs and tool results server-side once tracing
is opted in. The coaching ledger (injuries, sleep, mood) must never reach that
third party in clear. This module is pure: no agent, API or HTTP imports.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.messages import BaseMessage

from arete.services.athlete_facts import FACTS_HEADING
from arete.services.journal import JOURNAL_HEADING

# Both headings mark where per-athlete data starts in the system prompt; the
# complete-request guard lets the context builder append sections after
# either one (attachments, page, surface, retrieved memory passages), so
# redacting from the earliest heading onward catches all of them too.
PROMPT_SENSITIVE_HEADINGS = (FACTS_HEADING, JOURNAL_HEADING)

# A structure deeper or larger than this is unexpected for a coaching run;
# redact it wholesale rather than walk it unscrubbed.
WALK_DEPTH_MAX = 20
WALK_NODES_MAX = 2_000

# Field names that only ever carry journal/memory free text, wherever they
# appear in a tool call's arguments or return value.
SENSITIVE_KEYS = frozenset(
    {"title", "body", "text", "old_string", "new_string", "source_ref"}
)

# Tools whose result always carries ledger content. LangSmith records a tool
# result as a flat "content" string, so the key-name net above cannot reach
# inside it; gate on the tool name instead. read_file/grep/edit_file/delete/ls
# are shared with the attachments and system-skills routes of the same
# filesystem middleware, so this also redacts those non-journal reads: the
# backend has no cheaper way to tell them apart from the traced payload alone.
SENSITIVE_TOOL_NAMES = frozenset(
    {
        "append_journal",
        "remember_fact",
        "read_file",
        "grep",
        "edit_file",
        "delete",
        "ls",
    }
)

REDACTED_TRUNCATED = "[REDACTED:truncated]"


@dataclass(frozen=True)
class Sensitive:
    """Carries a value that must reach the model unchanged but never a trace.

    Scrubbing happens on a copy of the traced payload; the wrapped value is
    returned to the caller untouched. Useless once a value has already been
    serialized to a flat string (json.dumps erases the wrapper), so mark the
    value at the point it is still a structured Python object.
    """

    label: str
    value: Any


def sensitive(label: str, value: Any) -> Sensitive:
    return Sensitive(label, value)


def _redacted(label: str) -> str:
    return f"[REDACTED:{label}]"


def _redact_tool_call(call: dict) -> dict:
    name = call.get("name")
    if isinstance(name, str) and name in SENSITIVE_TOOL_NAMES and call.get("args"):
        return {**call, "args": _redacted(name)}
    return call


def _redact_prompt_sections(text: str) -> str:
    """Cut a system prompt at its earliest per-athlete section, if any.

    The context builder appends facts, journal, attachments, page, surface
    and retrieved memory passages after whichever of these headings comes
    first, in that fixed order, so cutting there also drops everything after.
    """
    starts = [i for i in (text.find(h) for h in PROMPT_SENSITIVE_HEADINGS) if i != -1]
    if not starts:
        return text
    return text[: min(starts)] + _redacted("personal_context")


def _scrubbed_message(
    value: Any, *, depth: int, nodes_left: list[int]
) -> BaseMessage | None:
    """A redacted copy of a live message, or None if it needs no change.

    Covers a ToolMessage result (content keyed by the tool's own name), an
    AIMessage requesting a sensitive tool through its normalized tool_calls
    or a provider's raw additional_kwargs, and a system/human message whose
    content carries the injected prompt sections above.
    """
    if not isinstance(value, BaseMessage):
        return None
    if value.name in SENSITIVE_TOOL_NAMES:
        return value.model_copy(update={"content": _redacted(value.name)})

    updates: dict[str, Any] = {}
    tool_calls = getattr(value, "tool_calls", None) or []
    redacted_calls = [_redact_tool_call(call) for call in tool_calls]
    if redacted_calls != tool_calls:
        updates["tool_calls"] = redacted_calls
    redacted_kwargs = _walk(
        value.additional_kwargs, depth=depth + 1, nodes_left=nodes_left
    )
    if redacted_kwargs != value.additional_kwargs:
        updates["additional_kwargs"] = redacted_kwargs
    if isinstance(value.content, str):
        redacted_content = _redact_prompt_sections(value.content)
        if redacted_content != value.content:
            updates["content"] = redacted_content
    return value.model_copy(update=updates) if updates else None


def _walk(value: Any, *, depth: int, nodes_left: list[int]) -> Any:
    assert depth >= 0
    assert nodes_left[0] >= 0
    if depth > WALK_DEPTH_MAX or nodes_left[0] == 0:
        return REDACTED_TRUNCATED
    nodes_left[0] -= 1

    if isinstance(value, Sensitive):
        return _redacted(value.label)
    if isinstance(value, BaseMessage):
        return _scrubbed_message(value, depth=depth, nodes_left=nodes_left) or value
    if isinstance(value, dict):
        name = value.get("name")
        if isinstance(name, str) and name in SENSITIVE_TOOL_NAMES:
            # A normalized tool_call dict carries its payload under "args"; a
            # raw provider function-call dict (additional_kwargs) carries it
            # as a JSON-encoded string under "arguments"; a ToolMessage dump
            # carries it under "content". Redact whichever is present,
            # wholesale: relying on SENSITIVE_KEYS alone would miss a field
            # name it does not list.
            value = {
                key: _redacted(name)
                if key in ("content", "args", "arguments")
                else child
                for key, child in value.items()
            }
        return {
            key: _redacted(key)
            if key in SENSITIVE_KEYS
            else _walk(child, depth=depth + 1, nodes_left=nodes_left)
            for key, child in value.items()
        }
    if isinstance(value, (list, tuple)):
        return type(value)(
            _walk(item, depth=depth + 1, nodes_left=nodes_left) for item in value
        )
    if isinstance(value, str):
        return _redact_prompt_sections(value)
    return value


def scrub(payload: dict) -> dict:
    """Redact a LangSmith run's inputs or outputs dict; bounded, never raises.

    Safe to pass directly as `langsmith.Client(hide_inputs=scrub, hide_outputs=scrub)`.
    """
    if not isinstance(payload, dict):
        return payload
    nodes_left = [WALK_NODES_MAX]
    scrubbed = _walk(payload, depth=0, nodes_left=nodes_left)
    assert isinstance(scrubbed, dict)
    return scrubbed


def redact_sensitive_tool_run(name: str) -> str:
    """The traced result of a known-sensitive tool run, whatever shape it had.

    `scrub()` can only see a run's own inputs or outputs dict, never its
    name, so it cannot redact a tool result that reaches LangSmith as a bare
    string (no "name" key to gate on, unlike a ToolMessage or a tool_call
    dict). A caller with the run's name in hand (the tracer, not the client)
    should replace the whole result with this instead of calling `scrub()`.
    """
    assert isinstance(name, str) and name
    return _redacted(name)
