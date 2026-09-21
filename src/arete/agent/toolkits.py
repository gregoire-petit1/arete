"""Toolkits — Cortex-style progressive tool loading for the coaching agent.

Port of Cortex's ``ToolkitMiddleware`` pattern, reduced to what Arete needs:
toolkits are registered on the graph but their tools stay OUT of the model
request until the agent calls ``load_toolkit(toolkit_id)``. Loading binds the
toolkit's tools natively (full schemas) and pins its instructions for the rest
of the run. ``search_toolkits(query)`` finds the right toolkit when only the
capability is known.

Why progressive: every bound tool costs schema tokens on every turn and
dilutes tool selection. A planning write-tool the agent only needs one turn
out of ten should not sit on the primary list.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from langchain_core.tools import BaseTool


@dataclass(frozen=True)
class Toolkit:
    """A named bundle of tools + the instructions to use them well."""

    id: str
    description: str
    tools: list[BaseTool]
    instructions: str


@dataclass
class _ToolkitRuntimeState:
    """Mutable per-run state: which toolkits are loaded this run."""

    loaded: set[str] = field(default_factory=set)
    #: Instructions of loaded toolkits, in load order (dedup'd).
    pinned_instructions: list[str] = field(default_factory=list)
