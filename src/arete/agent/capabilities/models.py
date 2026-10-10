"""Toolkits — progressive tool loading for the coaching agent.

Toolkits are registered on the graph but their tools stay OUT of the model
request until the agent calls ``load_toolkit(toolkit_id)``. Loading binds the
toolkit's tools natively (full schemas) and pins its instructions for the rest
of the run. ``search_toolkits(query)`` finds the right toolkit when only the
capability is known.

Why progressive: every bound tool costs schema tokens on every turn and
dilutes tool selection. A planning write-tool the agent only needs one turn
out of ten should not sit on the primary list.

Which toolkits are loaded lives in the GRAPH STATE, not on the middleware
instance: the compiled graph is process-wide (``agent.get_agent`` is
lru_cached) and two runs overlap easily — two tabs, or a ``/tips/daily``
refetch landing while the panel is mid-turn. Instance state let one run wipe
the other's toolkits between turns; graph state is per-run by construction.
"""

from __future__ import annotations

from dataclasses import dataclass

from langchain_core.tools import BaseTool


@dataclass(frozen=True)
class Toolkit:
    """A named bundle of tools + the instructions to use them well."""

    id: str
    description: str
    tools: list[BaseTool]
    instructions: str
    # Explicit allowlist: a newly added tool is unavailable to background jobs
    # until its read-only behavior has been reviewed.
    read_tools: frozenset[str]
    # Only explicit workout actions may create interactive chat cards.
    workout_actions: frozenset[str] = frozenset()
