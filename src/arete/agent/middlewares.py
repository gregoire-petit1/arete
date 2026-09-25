"""Runtime context + tool-event middlewares.

- ``RuntimeContextMiddleware``: inject the open page at the request tail
  (port of Cortex's ``RuntimeContextMiddleware._panel_context_message``,
  INTAI-1589). Malformed or over-budget payloads are SKIPPED with a warning,
  never truncated.
- ``ToolEventMiddleware``: emit ``tool_start`` / ``tool_end`` custom stream
  events (``langgraph.config.get_stream_writer``) so the UI can show live
  tool progress; consumed with ``stream_mode="custom"``.
"""

from __future__ import annotations

import json
import logging

from langchain.agents.middleware import AgentMiddleware, ModelRequest
from langchain_core.messages import HumanMessage

from arete.agent.context import MAX_PANEL_CONTEXT_CHARS, PANEL_CONTEXT_KEY

logger = logging.getLogger(__name__)

_PANEL_CONTEXT_PREFIX = (
    "System-provided page context: the user is currently viewing {label} of "
    "the Arete app while talking to you. Use it to ground your answers; call "
    "get_page_context for the underlying data."
)

_PAGE_LABELS = {
    "dashboard": "the Dashboard",
    "planning": "the Planning page",
    "analytics": "the Analytics page",
    "log": "the Log page",
    "settings": "the Settings page",
}
_FALLBACK_LABEL = "an unknown page"


class RuntimeContextMiddleware(AgentMiddleware):
    """Stamp ``context.source.panel_context`` as a HumanMessage every turn."""

    def wrap_model_call(self, request, handler):
        message = _panel_context_message(request)
        if message is None:
            return handler(request)
        request.messages.append(message)
        return handler(request)

    async def awrap_model_call(self, request, handler):
        # Async twin required by astream(); the logic is pure, no awaits.
        message = _panel_context_message(request)
        if message is None:
            return await handler(request)
        request.messages.append(message)
        return await handler(request)


def _panel_context_message(request: ModelRequest) -> HumanMessage | None:
    """Render the open page at the request tail, or None to skip injection."""
    runtime = getattr(request, "runtime", None)
    context = getattr(runtime, "context", None)
    if context is None:
        return None
    source = getattr(context, "source", None)
    if not isinstance(source, dict):
        return None

    raw = source.get(PANEL_CONTEXT_KEY)
    if not isinstance(raw, str) or not raw:
        return None
    if len(raw) > MAX_PANEL_CONTEXT_CHARS:
        logger.warning(
            "Panel context payload over budget; skipping injection",
            extra={"chars": len(raw), "budget": MAX_PANEL_CONTEXT_CHARS},
        )
        return None
    try:
        payload = json.loads(raw)
    except ValueError:
        logger.warning("Panel context payload is not JSON; skipping injection")
        return None
    if not isinstance(payload, dict):
        logger.warning("Panel context payload is not an object; skipping injection")
        return None

    page = payload.get("page")
    label = (
        _PAGE_LABELS.get(page, _FALLBACK_LABEL)
        if isinstance(page, str)
        else _FALLBACK_LABEL
    )
    return HumanMessage(content=f"{_PANEL_CONTEXT_PREFIX.format(label=label)}\n\n{raw}")


class ToolEventMiddleware(AgentMiddleware):
    """Emit tool_start/tool_end custom events for live UI progress.

    Payloads stay tiny: the tool NAME plus, for the page-source tool, the
    page argument — never the tool output (the UI has no use for 30kB of
    analytics JSON).
    """

    def wrap_tool_call(self, request, handler):
        from langgraph.config import get_stream_writer

        writer = get_stream_writer()
        tool_call = request.tool_call
        name = str(tool_call.get("name", "unknown"))
        args_preview = ""
        if name == "get_page_context":
            page = tool_call.get("args", {}).get("page", "")
            args_preview = str(page)[:40]
        writer({"type": "tool_start", "name": name, "args": args_preview})
        try:
            return handler(request)
        finally:
            writer({"type": "tool_end", "name": name})

    async def awrap_tool_call(self, request, handler):
        from langgraph.config import get_stream_writer

        writer = get_stream_writer()
        tool_call = request.tool_call
        name = str(tool_call.get("name", "unknown"))
        args_preview = ""
        if name == "get_page_context":
            page = tool_call.get("args", {}).get("page", "")
            args_preview = str(page)[:40]
        writer({"type": "tool_start", "name": name, "args": args_preview})
        try:
            return await handler(request)
        finally:
            writer({"type": "tool_end", "name": name})
