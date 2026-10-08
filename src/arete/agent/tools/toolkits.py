"""Tools for capability discovery and loading."""

import json
import logging

from langchain.tools import ToolRuntime
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.types import Command
from pydantic import BaseModel, Field

from arete.agent.capabilities.discovery import (
    _available_tools,
    _loaded,
    _profile,
    _registry,
    _search_toolkits,
)

logger = logging.getLogger(__name__)


class _SearchToolkitsInput(BaseModel):
    query: str = Field(description="Capacité recherchée, ex: 'planifier une séance'")


class _LoadToolkitInput(BaseModel):
    toolkit_id: str = Field(description="Id du toolkit à charger, ex: 'planning'")


def _search(runtime: ToolRuntime, query: str) -> str:
    profile = _profile(runtime)
    return _search_toolkits(query, _loaded(runtime.state, profile), profile)


async def _asearch(runtime: ToolRuntime, query: str) -> str:
    return _search(runtime, query)


def _load(runtime: ToolRuntime, toolkit_id: str) -> Command:
    """Load a toolkit: a state update, not a mutation."""
    profile = _profile(runtime)
    tk = _registry(profile).get(toolkit_id)
    if tk is None:
        error = json.dumps(
            {
                "error": f"Unknown toolkit '{toolkit_id}'. "
                f"Available: {list(_registry(profile))}"
            }
        )
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        error, tool_call_id=runtime.tool_call_id, status="error"
                    )
                ]
            }
        )
    logger.info("Toolkit loaded: %s (tools=%d)", toolkit_id, len(tk.tools))
    payload = json.dumps(
        {
            "loaded": True,
            "toolkit_id": toolkit_id,
            "tools": [t.name for t in _available_tools(tk, profile)],
        },
        ensure_ascii=False,
    )
    return Command(
        update={
            "loaded_toolkits": [toolkit_id],
            "messages": [ToolMessage(payload, tool_call_id=runtime.tool_call_id)],
        }
    )


async def _aload(runtime: ToolRuntime, toolkit_id: str) -> Command:
    return _load(runtime, toolkit_id)


SEARCH_TOOLKITS_TOOL = StructuredTool.from_function(
    func=_search,
    coroutine=_asearch,
    name="search_toolkits",
    description=(
        "Cherche un toolkit par capacité (ex: 'planifier une séance'). "
        "À appeler avant load_toolkit si l'id exact n'est pas connu."
    ),
    args_schema=_SearchToolkitsInput,
    infer_schema=False,
)

LOAD_TOOLKIT_TOOL = StructuredTool.from_function(
    func=_load,
    coroutine=_aload,
    name="load_toolkit",
    description=(
        "Charge un toolkit et rend ses outils disponibles pour le reste "
        "de cette exécution."
    ),
    args_schema=_LoadToolkitInput,
    infer_schema=False,
)

META_TOOLS: list[BaseTool] = [SEARCH_TOOLKITS_TOOL, LOAD_TOOLKIT_TOOL]
