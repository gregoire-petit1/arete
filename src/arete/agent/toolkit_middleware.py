"""Toolkit middleware — progressive tool loading (Cortex pattern).

Tools of un-loaded toolkits never reach the model. Two meta-tools drive the
state machine:
- ``search_toolkits(query)``: find a toolkit by capability
- ``load_toolkit(toolkit_id)``: bind its tools + pin its instructions

Loaded toolkits live in ``ToolkitState.loaded_toolkits`` (graph state), so a
run's loading is invisible to any other run sharing the process-wide compiled
graph. ``load_toolkit`` is an ordinary tool returning a ``Command`` state
update — the ToolNode knows it statically (it is declared on
``middleware.tools``) and folds the update back into the graph.

Execution contract (LangChain 1.x, verified): tools added to
``request.tools`` in ``wrap_model_call`` reach the MODEL but not the ToolNode
— calling one fails with "not a valid tool". Toolkit tools are therefore
executed here: ``wrap_tool_call`` intercepts calls whose name belongs to a
registered toolkit and runs the tool directly.

Loading also pins the toolkit's instructions to the system message for the
rest of the run (``_append_system_text``, same append-don't-replace contract
as deepagents' filesystem middleware, so the two compose).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest
from langchain.tools import ToolRuntime
from langchain_core.messages import SystemMessage, ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from langgraph.types import Command
from pydantic import BaseModel, Field

from arete.agent.planning_tools import PLANNING_INSTRUCTIONS, PLANNING_TOOLS
from arete.agent.toolkits import Toolkit, ToolkitState

logger = logging.getLogger(__name__)

#: All registered toolkits. Registering a new one is one line here.
_TOOLKIT_REGISTRY: dict[str, Toolkit] = {
    "planning": Toolkit(
        id="planning",
        description=(
            "Planifier l'entraînement : créer, lister, modifier ou supprimer "
            "des séances prévues sur la page Planning."
        ),
        tools=PLANNING_TOOLS,
        instructions=PLANNING_INSTRUCTIONS,
    ),
}


class _SearchToolkitsInput(BaseModel):
    query: str = Field(description="Capacité recherchée, ex: 'planifier une séance'")


class _LoadToolkitInput(BaseModel):
    toolkit_id: str = Field(description="Id du toolkit à charger, ex: 'planning'")


def loaded_toolkits(state: Any) -> list[str]:
    """Toolkits loaded so far in this run, from the graph state.

    Tolerant of a state that does not carry the key yet: the channel is unset
    until the first ``load_toolkit``, and ``before_agent`` no longer seeds it.
    """
    if isinstance(state, dict):
        return list(state.get("loaded_toolkits") or [])
    return list(getattr(state, "loaded_toolkits", None) or [])


def tool_instructions_suffix(loaded: list[str]) -> str:
    """Pinned instructions of loaded toolkits, for the system prompt tail."""
    return "\n\n".join(
        _TOOLKIT_REGISTRY[toolkit_id].instructions
        for toolkit_id in loaded
        if toolkit_id in _TOOLKIT_REGISTRY
    )


def _catalog(hint: str) -> str:
    """The whole catalog, for a query that matched nothing."""
    return json.dumps(
        {
            "results": [],
            "available": [
                {"toolkit_id": tid, "description": tk.description}
                for tid, tk in _TOOLKIT_REGISTRY.items()
            ],
            "hint": hint,
        },
        ensure_ascii=False,
    )


def _search_toolkits(query: str, loaded: list[str]) -> str:
    """Find toolkits matching a capability query.

    Token-based: every query token (>= 4 chars, stemmed-lite by stripping the
    final 's') must hit the id or description. More forgiving than substring,
    which misses "planifier une séance" vs "créer… des séances".
    """
    needle_tokens = [
        t.rstrip("s") for t in query.strip().lower().split() if len(t) >= 4
    ]
    if not needle_tokens:
        # Empty/garbage query: return the catalog rather than everything-is-a-hit.
        return _catalog("Requête vide; voici les toolkits disponibles.")

    hits = []
    for tid, tk in _TOOLKIT_REGISTRY.items():
        haystack = (tid + " " + tk.description).lower()
        hay_tokens = {t.rstrip("s") for t in haystack.split()}
        if all(tok in haystack or tok in hay_tokens for tok in needle_tokens):
            hits.append(
                {
                    "toolkit_id": tid,
                    "description": tk.description,
                    "loaded": tid in loaded,
                }
            )
    if not hits:
        return _catalog("Aucun toolkit pour cette requête; voici ceux qui existent.")
    return json.dumps({"results": hits}, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Meta-tools. Module-level: they read and write the graph state through their
# injected ToolRuntime, so nothing needs to close over middleware instance
# state (the bug this replaced).
# ---------------------------------------------------------------------------


def _search(runtime: ToolRuntime, query: str) -> str:
    return _search_toolkits(query, loaded_toolkits(runtime.state))


async def _asearch(runtime: ToolRuntime, query: str) -> str:
    return _search(runtime, query)


def _load(runtime: ToolRuntime, toolkit_id: str) -> Command:
    """Load a toolkit: a state update, not a mutation."""
    tk = _TOOLKIT_REGISTRY.get(toolkit_id)
    if tk is None:
        error = json.dumps(
            {
                "error": f"Unknown toolkit '{toolkit_id}'. "
                f"Available: {list(_TOOLKIT_REGISTRY)}"
            }
        )
        return Command(
            update={"messages": [ToolMessage(error, tool_call_id=runtime.tool_call_id)]}
        )
    logger.info("Toolkit loaded: %s (tools=%d)", toolkit_id, len(tk.tools))
    payload = json.dumps(
        {"loaded": True, "toolkit_id": toolkit_id, "tools": [t.name for t in tk.tools]},
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
        "de la conversation."
    ),
    args_schema=_LoadToolkitInput,
    infer_schema=False,
)

META_TOOLS: list[BaseTool] = [SEARCH_TOOLKITS_TOOL, LOAD_TOOLKIT_TOOL]


def _augment_tools(tools: list[Any], loaded: list[str]) -> list[Any]:
    """Meta-tools + tools of already-loaded toolkits, deduped by name.

    These reach the MODEL (schemas in the request). Execution of toolkit tools
    is handled in ``wrap_tool_call`` — the ToolNode does not know them.
    """
    out: list[Any] = list(tools)
    existing = {getattr(t, "name", "") for t in out}
    for tool in META_TOOLS:
        if tool.name not in existing:
            out.append(tool)
            existing.add(tool.name)
    for toolkit_id in loaded:
        tk = _TOOLKIT_REGISTRY.get(toolkit_id)
        if tk is None:
            continue
        for tool in tk.tools:
            if tool.name not in existing:
                out.append(tool)
                existing.add(tool.name)
    return out


def _append_system_text(
    system_message: SystemMessage | None, text: str
) -> SystemMessage:
    """System message with ``text`` appended. Append, never replace: the
    filesystem middleware downstream appends its own block the same way."""
    existing = system_message.text if system_message is not None else ""
    return SystemMessage(content=f"{existing}\n\n{text}" if existing else text)


def _apply(request: ModelRequest):
    """Request carrying the augmented tool list + the pinned instructions.

    ``override`` (not attribute assignment, deprecated in LangChain 1.x)
    returns a new request, leaving the caller's untouched.
    """
    loaded = loaded_toolkits(request.state)
    overrides: dict[str, Any] = {"tools": _augment_tools(request.tools, loaded)}
    suffix = tool_instructions_suffix(loaded)
    if suffix:
        overrides["system_message"] = _append_system_text(
            request.system_message, suffix
        )
    return request.override(**overrides)


def _toolkit_tool(name: str, loaded: list[str]) -> BaseTool | None:
    """The toolkit tool called ``name``, or None when we do not own it.

    Loaded toolkits first. The fallback over the whole registry covers the
    same-turn case: a model that emits ``load_toolkit`` and one of its tools
    in one batch would otherwise hit the ToolNode, which does not know the
    tool ("not a valid tool") and burns turns on a retry. What the model may
    SEE is still gated by ``_augment_tools``; execution is permissive on
    purpose.
    """
    for toolkit_id in loaded:
        tk = _TOOLKIT_REGISTRY.get(toolkit_id)
        if tk is None:
            continue
        for tool in tk.tools:
            if tool.name == name:
                return tool
    for toolkit_id, tk in _TOOLKIT_REGISTRY.items():
        for tool in tk.tools:
            if tool.name == name:
                logger.info(
                    "Tool %s executed from toolkit %s before it was loaded",
                    name,
                    toolkit_id,
                )
                return tool
    return None


class ToolkitMiddleware(AgentMiddleware):
    """Progressive toolkit loading over ``ToolkitState.loaded_toolkits``."""

    state_schema = ToolkitState

    def __init__(self) -> None:
        super().__init__()
        # Meta-tools registered for EXECUTION (middleware.tools contract): the
        # ToolNode knows them statically and folds load_toolkit's Command into
        # the graph state.
        self.tools: list[BaseTool] = META_TOOLS

    def wrap_model_call(self, request: ModelRequest, handler):
        return handler(_apply(request))

    async def awrap_model_call(self, request: ModelRequest, handler):
        return await handler(_apply(request))

    async def _passthrough_async(self, request, handler):
        return await handler(request)

    def _execute_dynamic(self, request, handler, *, await_handler: bool):
        """Run toolkit tools this middleware owns; pass the rest through.

        ``await_handler`` matters for the passthrough branch: in the async
        tool chain the handler returns a coroutine — returning it un-awaited
        would land a coroutine in the messages channel ("Unsupported message
        type: <class 'coroutine'>").
        """
        name = str(request.tool_call.get("name", ""))
        tool = _toolkit_tool(name, loaded_toolkits(request.state))
        if tool is None:
            if await_handler:
                return self._passthrough_async(request, handler)
            return handler(request)
        result = tool.invoke(dict(request.tool_call.get("args") or {}))
        return ToolMessage(
            content=str(result),
            name=name,
            tool_call_id=str(request.tool_call.get("id", "")),
        )

    def wrap_tool_call(self, request, handler):
        return self._execute_dynamic(request, handler, await_handler=False)

    async def awrap_tool_call(self, request, handler):
        result = self._execute_dynamic(request, handler, await_handler=True)
        if asyncio.iscoroutine(result):
            return await result
        return result


def reset_registry_for_tests() -> None:  # pragma: no cover - test helper
    _TOOLKIT_REGISTRY.clear()
