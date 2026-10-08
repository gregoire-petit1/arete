"""Capability discovery and request-local loaded sets, independent of hooks."""

import json
import unicodedata
from typing import Any

from langchain_core.tools import BaseTool

from arete.agent.capabilities.models import Toolkit
from arete.agent.capabilities.registry import CAPABILITIES
from arete.agent.runtime.context import AgentContext
from arete.agent.runtime.policy import resolve_policy


def _profile(runtime: Any) -> str:
    context = getattr(runtime, "context", None)
    return context.profile if isinstance(context, AgentContext) else "chat"


def _registry(profile: str) -> dict[str, Toolkit]:
    policy = resolve_policy(profile)
    return {tid: CAPABILITIES[tid] for tid in policy.profile.capabilities}


def _available_tools(tk: Toolkit, profile: str) -> list[BaseTool]:
    policy = resolve_policy(profile)
    return [t for t in tk.tools if policy.can_execute(tk.id, t.name, tk.read_tools)]


def _loaded(state: Any, profile: str) -> list[str]:
    # The briefing always needs analytics: avoid search/load model round trips.
    initial = list(resolve_policy(profile).profile.preloaded)
    return [
        tid
        for tid in dict.fromkeys(initial + loaded_toolkits(state))
        if tid in _registry(profile)
    ]


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
        CAPABILITIES[toolkit_id].instructions
        for toolkit_id in loaded
        if toolkit_id in CAPABILITIES
    )


def _catalog(hint: str, profile: str = "chat") -> str:
    """The whole catalog, for a query that matched nothing."""
    return json.dumps(
        {
            "results": [],
            "available": [
                {"toolkit_id": tid, "description": tk.description}
                for tid, tk in _registry(profile).items()
            ],
            "hint": hint,
        },
        ensure_ascii=False,
    )


def _fold(text: str) -> str:
    """Lowercased and stripped of accents.

    A query typed in a hurry, or transcribed from speech, rarely carries them:
    "enregistrer une seance" has to reach a toolkit described with "séance".
    """
    decomposed = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def _search_toolkits(query: str, loaded: list[str], profile: str = "chat") -> str:
    """Find toolkits matching a capability query.

    Token-based: every query token (>= 4 chars, stemmed-lite by stripping the
    final 's') must hit the id or description. More forgiving than substring,
    which misses "planifier une séance" vs "créer… des séances".
    """
    needle_tokens = [t.rstrip("s") for t in _fold(query).split() if len(t) >= 4]
    if not needle_tokens:
        # Empty/garbage query: return the catalog rather than everything-is-a-hit.
        return _catalog("Requête vide; voici les toolkits disponibles.", profile)

    hits = []
    for tid, tk in _registry(profile).items():
        haystack = _fold(tid + " " + tk.description)
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
        return _catalog(
            "Aucun toolkit pour cette requête; voici ceux qui existent.", profile
        )
    return json.dumps({"results": hits}, ensure_ascii=False)
