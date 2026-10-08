"""Per-invocation conversation state; browser history remains authoritative."""

from typing import Annotated, NotRequired

from langchain.agents.middleware import AgentState


def merge_loaded(left: list[str] | None, right: list[str] | None) -> list[str]:
    """Reducer for ``loaded_toolkits``: union, in load order, deduplicated.

    Deliberately not ``operator.add``: a model can emit two ``load_toolkit``
    calls for the same toolkit in one turn (parallel tool calls), and a
    duplicate entry would pin the same instructions block twice.
    """
    merged = list(left or [])
    for toolkit_id in right or []:
        if toolkit_id not in merged:
            merged.append(toolkit_id)
    return merged


class CoachState(AgentState):
    """Agent state plus the toolkits loaded during THIS run."""

    loaded_toolkits: NotRequired[Annotated[list[str], merge_loaded]]

    suggestions: NotRequired[list[str]]
