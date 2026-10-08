"""Shared execution bounds for chat and unattended coaching.

Use the async graph even from synchronous workers so the total deadline can
cancel provider waits, including SDK retries. Cancellation cannot roll back
an already committed write or kill a synchronous tool running in a thread;
never replay a failed run automatically.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator
from contextlib import aclosing
from functools import partial
from time import monotonic
from typing import Any, cast

from anyio import from_thread
from langchain.agents.middleware.model_call_limit import ModelCallLimitExceededError
from langchain.agents.middleware.tool_call_limit import ToolCallLimitExceededError

from arete.agent.models.routing import configured_model_name
from arete.agent.runtime.budget import (
    MAX_GRAPH_STEPS,
    MAX_RUN_SECONDS,
    MAX_TOOL_CONCURRENCY,
)
from arete.agent.runtime.context import AgentContext
from arete.config import config
from arete.observability.tracing import agent_tracing

RUN_LIMIT_ERRORS = (ModelCallLimitExceededError, ToolCallLimitExceededError)
LIMIT_MESSAGE = (
    "Le coach a atteint sa limite d'appels. Le travail est incomplet ; "
    "les modifications déjà effectuées sont conservées. Consulte les résultats "
    "avant de poursuivre avec une demande plus ciblée."
)
TIMEOUT_MESSAGE = (
    "Le coach a dépassé le délai de 5 minutes. Le travail est incomplet ; "
    "vérifie les modifications déjà effectuées avant de réessayer."
)


def run_config(
    recursion_limit: int = MAX_GRAPH_STEPS, *, context: AgentContext | None = None
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "recursion_limit": recursion_limit,
        "max_concurrency": MAX_TOOL_CONCURRENCY,
        "run_name": "arete_coach",
        "metadata": {
            "task": "session_feedback"
            if context and context.profile == "feedback"
            else context.profile
            if context
            else "chat",
            "provider": config.llm_provider,
            "model": configured_model_name(),
        },
    }
    if context and context.thread_id is not None:
        result["metadata"]["thread_id"] = context.thread_id
        result["configurable"] = {"thread_id": context.thread_id}
    return result


async def invoke_agent(graph: Any, state: dict, *, context: AgentContext) -> dict:
    context.deadline = monotonic() + MAX_RUN_SECONDS
    with agent_tracing():
        async with asyncio.timeout(MAX_RUN_SECONDS):
            return cast(
                dict,
                await graph.ainvoke(
                    state, context=context, config=run_config(context=context)
                ),
            )


def invoke_agent_sync(graph: Any, state: dict, *, context: AgentContext) -> dict:
    """Bridge AnyIO workers back to the server loop that owns the HTTP pool.

    A fresh asyncio.run() per job would reuse cached async HTTP clients across
    closed loops. Both FastAPI sync routes and the scheduler use AnyIO workers.
    Call invoke_agent directly from async callers.
    """
    return from_thread.run(partial(invoke_agent, graph, state, context=context))


async def stream_agent(
    graph: Any, state: dict, *, context: AgentContext
) -> AsyncGenerator[dict, None]:
    context.deadline = monotonic() + MAX_RUN_SECONDS
    with agent_tracing():
        async with asyncio.timeout(MAX_RUN_SECONDS):
            stream = graph.astream(
                state,
                context=context,
                config=run_config(context=context),
                stream_mode=["messages", "updates", "custom"],
                version="v2",
            )
            async with aclosing(stream):
                async for part in stream:
                    yield part
