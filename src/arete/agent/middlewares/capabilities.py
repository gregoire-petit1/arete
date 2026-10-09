"""Framework hooks for capability execution; declarations live in the catalog."""

import asyncio
import logging
from time import time_ns

from langchain.agents.middleware import AgentMiddleware
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool
from langgraph.config import get_stream_writer

from arete.agent.capabilities.execution import _resolve_tool
from arete.agent.capabilities.registry import validate_registry
from arete.agent.middlewares.observability import run_stats
from arete.agent.runtime.events import workout_updates
from arete.agent.runtime.state import CoachState
from arete.agent.tools.toolkits import META_TOOLS

logger = logging.getLogger(__name__)


class ToolkitMiddleware(AgentMiddleware):
    """Progressive toolkit loading over ``CoachState.loaded_toolkits``."""

    state_schema = CoachState

    def __init__(self) -> None:
        super().__init__()
        validate_registry()
        # Meta-tools registered for EXECUTION (middleware.tools contract): the
        # ToolNode knows them statically and folds load_toolkit's Command into
        # the graph state.
        self.tools: list[BaseTool] = META_TOOLS

    @staticmethod
    def _count(request) -> None:
        stats = run_stats(request)
        if stats is not None:
            stats.tool_calls += 1

    @staticmethod
    def _config(request, *, loop=None):
        config = dict(getattr(request.runtime, "config", None) or {})
        context = getattr(request.runtime, "context", None)
        # Capture the writer on the graph loop. Synchronous services execute in workers.
        try:
            writer = get_stream_writer()
        except RuntimeError:
            writer = None  # Unit calls outside a graph have no stream consumer.

        def progress(value):
            if writer is None:
                return
            session = {k: v for k, v in value["session"].items() if k != "prescription"}
            event = {
                "type": "workout_update",
                "id": request.tool_call["id"],
                "thread_id": getattr(context, "thread_id", None),
                "sequence": time_ns() // 1_000,
                "session": session,
                "export": value.get("export"),
            }
            if loop:
                if loop.is_closed():
                    logger.info(
                        "Workout progress retained in database after stream closure"
                    )
                    return
                try:
                    loop.call_soon_threadsafe(writer, event)
                except RuntimeError:
                    if not loop.is_closed():
                        raise
                    logger.info("Workout progress retained after event loop closure")
            else:
                writer(event)

        config["configurable"] = {
            **config.get("configurable", {}),
            "workout_progress": progress,
            "workout_deadline": getattr(context, "deadline", None),
            # Dependencies and deadlines belong to invocation context, never model args.
            "arete_context": context,
        }
        return config, progress

    def wrap_tool_call(self, request, handler):
        self._count(request)
        name = str(request.tool_call.get("name", ""))
        tool = _resolve_tool(request)
        if isinstance(tool, ToolMessage):
            return tool
        if tool is None:
            return handler(request)
        config, progress = self._config(request)
        result = tool.invoke(
            dict(request.tool_call.get("args") or {}),
            config=config,
        )
        for update in workout_updates(result):
            progress(update)
        return ToolMessage(
            content=str(result), name=name, tool_call_id=request.tool_call["id"]
        )

    async def awrap_tool_call(self, request, handler):
        self._count(request)
        name = str(request.tool_call.get("name", ""))
        tool = _resolve_tool(request)
        if isinstance(tool, ToolMessage):
            return tool
        if tool is None:
            return await handler(request)
        # ainvoke runs sync database tools off the event loop, allowing live
        # progress and concurrent requests to keep flowing during execution.
        config, progress = self._config(request, loop=asyncio.get_running_loop())
        result = await tool.ainvoke(
            dict(request.tool_call.get("args") or {}),
            config=config,
        )
        for update in workout_updates(result):
            progress(update)
        return ToolMessage(
            content=str(result), name=name, tool_call_id=request.tool_call["id"]
        )
