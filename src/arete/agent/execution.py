"""One execution policy for every coach caller, including streaming and evals."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import aclosing
from threading import Lock
from typing import Any

from langchain_core.runnables import RunnableConfig

from arete.agent.agent import AGENT_RECURSION_LIMIT, get_agent
from arete.agent.context import AgentContext, AgentTask
from arete.agent.model import configured_model_name
from arete.agent.tracing import agent_tracing
from arete.config import config

TASK_RECURSION_LIMITS: dict[AgentTask, int] = {
    "chat": AGENT_RECURSION_LIMIT,
    "briefing": 40,
    "session_feedback": 20,
}

# lru_cache alone can build twice on concurrent first access. Only creation
# needs serialization; executions use independent graph state and may overlap.
_graph_lock = Lock()


def _graph():
    with _graph_lock:
        return get_agent()


def _run_config(context: AgentContext) -> RunnableConfig:
    run_config: RunnableConfig = {
        "recursion_limit": TASK_RECURSION_LIMITS[context.task],
        "run_name": "arete_coach",
        "metadata": {
            "task": context.task,
            "provider": config.llm_provider,
            "model": configured_model_name(),
        },
    }
    if context.thread_id is not None:
        run_config["metadata"]["thread_id"] = context.thread_id
        run_config["configurable"] = {"thread_id": context.thread_id}
    return run_config


def invoke_agent(state: dict[str, Any], *, context: AgentContext) -> dict[str, Any]:
    with agent_tracing():
        result: dict[str, Any] = _graph().invoke(
            state, context=context, config=_run_config(context)
        )
        return result


async def stream_agent(
    state: dict[str, Any], *, context: AgentContext
) -> AsyncGenerator[dict[str, Any], None]:
    with agent_tracing():
        stream = _graph().astream(
            state,
            context=context,
            config=_run_config(context),
            stream_mode=["messages", "updates", "custom"],
            version="v2",
        )
        # A disconnect must finish the underlying graph while its tracing
        # context is still active, rather than waiting for async-generator GC.
        async with aclosing(stream):
            async for part in stream:
                yield part
