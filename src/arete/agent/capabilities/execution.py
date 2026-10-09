"""Execution resolution shared by synchronous and asynchronous hooks."""

import json

from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool

from arete.agent.capabilities.discovery import (
    _available_tools,
    _loaded,
    _profile,
    _registry,
)
from arete.agent.capabilities.registry import CAPABILITIES


def _toolkit_tool(name: str) -> tuple[str, BaseTool] | None:
    for tid, tk in CAPABILITIES.items():
        for tool in tk.tools:
            if tool.name == name:
                return tid, tool
    return None


def _resolve_tool(request) -> BaseTool | ToolMessage | None:
    name = request.tool_call["name"]
    profile = _profile(getattr(request, "runtime", None))
    found = _toolkit_tool(name)
    reason = None
    if found is not None:
        tid, tool = found
        tk = _registry(profile).get(tid)
        if tk is None or tool not in _available_tools(tk, profile):
            reason = "Tool unavailable for this mission."
        elif tid not in _loaded(request.state, profile):
            reason = f"Load toolkit '{tid}' before calling '{name}' in a later turn."
        else:
            return tool
    if reason:
        return ToolMessage(
            content=json.dumps({"error": reason}),
            name=name,
            tool_call_id=request.tool_call["id"],
            status="error",
        )
    return None
