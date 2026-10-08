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
from datetime import timedelta
from time import monotonic

from langchain.agents.middleware import AgentMiddleware, ModelRequest
from langchain_core.messages import HumanMessage, SystemMessage

from arete.agent.context import MAX_PANEL_CONTEXT_CHARS, PANEL_CONTEXT_KEY
from arete.agent.prompts import TASK_INSTRUCTIONS
from arete.agent.tool_events import preview, tool_result_event

logger = logging.getLogger(__name__)


def is_chat_request(request) -> bool:
    context = getattr(getattr(request, "runtime", None), "context", None)
    return getattr(context, "task", "chat") == "chat"


class TaskInstructionsMiddleware(AgentMiddleware):
    """Select instructions per request; never store a task on the shared graph."""

    def _apply(self, request):
        task = request.runtime.context.task
        common = request.system_message.text if request.system_message else ""
        instructions = TASK_INSTRUCTIONS[task]
        if task == "chat":
            today = request.runtime.context.current_date
            tomorrow = today + timedelta(days=1)
            instructions += (
                f"\nDate actuelle : {today.isoformat()}. Demain : {tomorrow.isoformat()}. "
                "Résous les dates relatives à partir de cette date, même si "
                "l'historique contient d'anciennes dates."
            )
        return request.override(
            system_message=SystemMessage(content=f"{common}\n\n{instructions}")
        )

    def wrap_model_call(self, request, handler):
        return handler(self._apply(request))

    async def awrap_model_call(self, request, handler):
        return await handler(self._apply(request))


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
    """Stamp ``context.source.panel_context`` at the tail of each request.

    For the request only. ``request.messages`` IS the state's message list, so
    appending to it in place left a copy of the block behind on every model
    call: a three-turn run carried three identical stamps, sent back to the
    model on every later turn, returned to the client, and growing with the
    conversation. ``override`` builds a new list and leaves the state alone.
    """

    def wrap_model_call(self, request, handler):
        message = _panel_context_message(request)
        if message is None:
            return handler(request)
        return handler(request.override(messages=[*request.messages, message]))

    async def awrap_model_call(self, request, handler):
        # Async twin required by astream(); the logic is pure, no awaits.
        message = _panel_context_message(request)
        if message is None:
            return await handler(request)
        return await handler(request.override(messages=[*request.messages, message]))


def _panel_context_message(request: ModelRequest) -> HumanMessage | None:
    """Render the open page at the request tail, or None to skip injection."""
    if not is_chat_request(request):
        return None
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
    """Track calls by ID, including parallel calls to the same tool.

    A failed or cancelled tool must never leave a green success tick behind.
    The UI receives bounded previews, not the entire analytics payload.
    """

    @staticmethod
    def _start(request, writer):
        call = request.tool_call
        call_id, name = call["id"], call["name"]
        writer(
            {
                "type": "tool_start",
                "id": call_id,
                "name": name,
                "args": preview(call.get("args", {})),
            }
        )
        return call_id, name, monotonic()

    @staticmethod
    def _failure(writer, call_id, name, started, exc):
        writer(
            {
                "type": "tool_end",
                "id": call_id,
                "name": name,
                "status": "error",
                "output": preview(str(exc)),
                "elapsed_ms": round((monotonic() - started) * 1000),
            }
        )

    def wrap_tool_call(self, request, handler):
        if not is_chat_request(request):
            return handler(request)
        from langgraph.config import get_stream_writer

        writer = get_stream_writer()
        call_id, name, started = self._start(request, writer)
        try:
            result = handler(request)
        except Exception as exc:
            self._failure(writer, call_id, name, started, exc)
            raise
        writer(
            tool_result_event(
                result,
                call_id=call_id,
                name=name,
                elapsed_ms=round((monotonic() - started) * 1000),
            )
        )
        return result

    async def awrap_tool_call(self, request, handler):
        if not is_chat_request(request):
            return await handler(request)
        from langgraph.config import get_stream_writer

        writer = get_stream_writer()
        call_id, name, started = self._start(request, writer)
        try:
            result = await handler(request)
        except Exception as exc:
            self._failure(writer, call_id, name, started, exc)
            raise
        writer(
            tool_result_event(
                result,
                call_id=call_id,
                name=name,
                elapsed_ms=round((monotonic() - started) * 1000),
            )
        )
        return result
