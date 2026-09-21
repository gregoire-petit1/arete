"""Toolkit middleware — progressive tool loading (Cortex pattern).

Tools of un-loaded toolkits never reach the model. Two meta-tools drive the
state machine:
- ``search_toolkits(query)``: find a toolkit by capability
- ``load_toolkit(toolkit_id)``: bind its tools + pin its instructions

Execution contract (LangChain 1.x, verified): tools added to
``request.tools`` in ``wrap_model_call`` reach the MODEL but not the ToolNode
— calling one fails with "not a valid tool". Toolkit tools are therefore
executed here: ``wrap_tool_call`` intercepts calls whose name belongs to a
loaded toolkit and runs the tool directly (``request.override(tool=...)``
pattern from the factory docs). Meta-tools are declared on ``self.tools`` so
the ToolNode knows them statically.

Loaded toolkits stay bound for the rest of the run. The stateless API resets
the set per request (``before_agent``): each chat call starts from primary
tools + meta-tools only, and loading is always an explicit, visible act.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from langchain.agents.middleware import AgentMiddleware, ModelRequest
from langchain_core.messages import ToolMessage
from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from arete.agent.planning_tools import PLANNING_INSTRUCTIONS, PLANNING_TOOLS
from arete.agent.toolkits import Toolkit, _ToolkitRuntimeState

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


def _search_toolkits(query: str, state: _ToolkitRuntimeState) -> str:
    """Find toolkits matching a capability query.

    Token-based: every query token (>= 4 chars, stemmed-lite by stripping the
    final 's') must hit the id or description. More forgiving than substring,
    which misses "planifier une séance" vs "créer… des séances".
    """
    needle_tokens = [
        t.rstrip("s") for t in query.strip().lower().split() if len(t) >= 4
    ]
    hits = []
    for tid, tk in _TOOLKIT_REGISTRY.items():
        haystack = (tid + " " + tk.description).lower()
        hay_tokens = {t.rstrip("s") for t in haystack.split()}
        if not needle_tokens or all(
            tok in haystack or tok in hay_tokens for tok in needle_tokens
        ):
            hits.append(
                {
                    "toolkit_id": tid,
                    "description": tk.description,
                    "loaded": tid in state.loaded,
                }
            )
    if not needle_tokens:
        # Empty/garbage query: return the catalog rather than everything-is-a-hit.
        return json.dumps(
            {
                "results": [],
                "available": [
                    {"toolkit_id": tid, "description": tk.description}
                    for tid, tk in _TOOLKIT_REGISTRY.items()
                ],
                "hint": "Requête vide; voici les toolkits disponibles.",
            },
            ensure_ascii=False,
        )
    if not hits:
        return json.dumps(
            {
                "results": [],
                "available": [
                    {"toolkit_id": tid, "description": tk.description}
                    for tid, tk in _TOOLKIT_REGISTRY.items()
                ],
                "hint": "Aucun toolkit pour cette requête; voici ceux qui existent.",
            },
            ensure_ascii=False,
        )
    return json.dumps({"results": hits}, ensure_ascii=False)


def _load_toolkit(toolkit_id: str, state: _ToolkitRuntimeState) -> str:
    tk = _TOOLKIT_REGISTRY.get(toolkit_id)
    if tk is None:
        return json.dumps(
            {
                "error": f"Unknown toolkit '{toolkit_id}'. Available: {list(_TOOLKIT_REGISTRY)}"
            }
        )
    state.loaded.add(toolkit_id)
    if tk.instructions not in state.pinned_instructions:
        state.pinned_instructions.append(tk.instructions)
    logger.info("Toolkit loaded: %s (tools=%d)", toolkit_id, len(tk.tools))
    return json.dumps(
        {"loaded": True, "toolkit_id": toolkit_id, "tools": [t.name for t in tk.tools]},
        ensure_ascii=False,
    )


def _make_meta_tools(state: _ToolkitRuntimeState) -> list[BaseTool]:
    """Meta-tools closed over the current run state."""

    def search(query: str) -> str:
        return _search_toolkits(query, state)

    def load(toolkit_id: str) -> str:
        return _load_toolkit(toolkit_id, state)

    return [
        StructuredTool.from_function(
            func=search,
            name="search_toolkits",
            description=(
                "Cherche un toolkit par capacité (ex: 'planifier une séance'). "
                "À appeler avant load_toolkit si l'id exact n'est pas connu."
            ),
            args_schema=_SearchToolkitsInput,
        ),
        StructuredTool.from_function(
            func=load,
            name="load_toolkit",
            description=(
                "Charge un toolkit et rend ses outils disponibles pour le reste "
                "de la conversation."
            ),
            args_schema=_LoadToolkitInput,
        ),
    ]


def _augment_tools(
    tools: list[Any], meta_tools: list[BaseTool], state: _ToolkitRuntimeState
) -> list[Any]:
    """Meta-tools + tools of already-loaded toolkits, deduped by name.

    These reach the MODEL (schemas in the request). Execution of toolkit tools
    is handled in ``wrap_tool_call`` — the ToolNode does not know them.
    ``meta_tools`` are the SAME closures as ``middleware.tools`` (one state).
    """
    out: list[Any] = list(tools)
    existing = {getattr(t, "name", "") for t in out}
    for tool in meta_tools:
        if tool.name not in existing:
            out.append(tool)
            existing.add(tool.name)
    for tk_id in state.loaded:
        tk = _TOOLKIT_REGISTRY.get(tk_id)
        if tk is None:
            continue
        for tool in tk.tools:
            if tool.name not in existing:
                out.append(tool)
                existing.add(tool.name)
    return out


class ToolkitMiddleware(AgentMiddleware):
    """Progressive toolkit loading over a per-run ``_ToolkitRuntimeState``."""

    def __init__(self) -> None:
        self._state = _ToolkitRuntimeState()
        # Meta-tools registered for EXECUTION (middleware.tools contract,
        # factory.py:1037). They close over self._state — the SAME object the
        # load state machine mutates (two state objects would silently split
        # "loaded" from "bound", the bug this replaced).
        self.tools: list[BaseTool] = _make_meta_tools(self._state)

    def wrap_model_call(self, request: ModelRequest, handler):
        request.tools = _augment_tools(request.tools, self.tools, self._state)
        return handler(request)

    async def awrap_model_call(self, request: ModelRequest, handler):
        request.tools = _augment_tools(request.tools, self.tools, self._state)
        return await handler(request)

    def _tool_for(self, name: str) -> BaseTool | None:
        """Find a loaded toolkit tool by name (also matches meta-tools)."""
        for tool in self.tools:
            if tool.name == name:
                return tool
        for tk_id in self._state.loaded:
            tk = _TOOLKIT_REGISTRY.get(tk_id)
            if tk is None:
                continue
            for tool in tk.tools:
                if tool.name == name:
                    return tool
        return None

    async def _passthrough_async(self, request, handler):
        return await handler(request)

    def _execute_dynamic(self, request, handler, *, await_handler: bool):
        """Run toolkit/meta tools this middleware owns; pass the rest through.

        ``await_handler`` matters for the passthrough branch: in the async
        tool chain the handler returns a coroutine — returning it un-awaited
        would land a coroutine in the messages channel ("Unsupported message
        type: <class 'coroutine'>").
        """
        name = str(request.tool_call.get("name", ""))
        tool = self._tool_for(name)
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
        result = self._execute_dynamic(request, handler, await_handler=False)
        return result

    async def awrap_tool_call(self, request, handler):
        result = self._execute_dynamic(request, handler, await_handler=True)
        if asyncio.iscoroutine(result):
            return await result
        return result

    def before_agent(self, state):
        # Fresh chat request (stateless API): reset the loaded set so each
        # request starts from primary tools + meta-tools only. Mutate IN
        # PLACE — the meta-tools close over this exact object; replacing it
        # would orphan their state (the "loaded but not bound" bug).
        self._state.loaded.clear()
        self._state.pinned_instructions.clear()
        return None


def tool_instructions_suffix(state: _ToolkitRuntimeState) -> str:
    """Pinned instructions of loaded toolkits, for the system prompt tail."""
    return "\n\n".join(state.pinned_instructions)


def reset_registry_for_tests() -> None:  # pragma: no cover - test helper
    _TOOLKIT_REGISTRY.clear()
