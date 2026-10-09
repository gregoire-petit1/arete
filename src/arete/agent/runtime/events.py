"""Small, correlated UI events; full tool results stay in the agent state."""

from __future__ import annotations

import json
from typing import Any, Literal, TypedDict

from langchain_core.messages import ToolMessage
from langgraph.types import Command

MAX_TOOL_PREVIEW_CHARS = 2_000


class Preview(TypedDict):
    text: str
    truncated: bool


class ToolStarted(TypedDict):
    type: Literal["tool_start"]
    id: str
    name: str
    args: Preview


class ToolCompleted(TypedDict):
    type: Literal["tool_end"]
    id: str
    name: str
    status: Literal["done", "error"]
    output: Preview
    elapsed_ms: int


def preview(value: Any) -> Preview:
    text = (
        value
        if isinstance(value, str)
        else json.dumps(value, ensure_ascii=False, default=str)
    )
    return {
        "text": text[:MAX_TOOL_PREVIEW_CHARS],
        "truncated": len(text) > MAX_TOOL_PREVIEW_CHARS,
    }


def tool_result_event(
    result: Any, *, call_id: str, name: str, elapsed_ms: int
) -> ToolCompleted:
    """Handle both normal ToolMessages and state-changing toolkit Commands."""
    messages = (
        result.update.get("messages", [])
        if isinstance(result, Command) and isinstance(result.update, dict)
        else [result]
    )
    message = next(
        (
            m
            for m in messages
            if isinstance(m, ToolMessage) and m.tool_call_id == call_id
        ),
        None,
    )
    content = message.content if message is not None else str(result)
    failed = message is not None and message.status == "error"
    if isinstance(content, str):
        try:
            payload = json.loads(content)
        except ValueError:
            payload = None  # Plain-text tool results are valid, not parse failures.
        if isinstance(payload, dict) and payload.get("error"):
            failed = True
        if content.startswith("Error:"):
            failed = True
    return {
        "type": "tool_end",
        "id": call_id,
        "name": name,
        "status": "error" if failed else "done",
        "output": preview(content),
        "elapsed_ms": elapsed_ms,
    }
