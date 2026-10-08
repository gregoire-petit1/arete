"""Own the final request ordering: harness, profile, capabilities, history, page data."""

from datetime import timedelta
from typing import Any

from langchain.agents.middleware import ModelRequest
from langchain_core.messages import SystemMessage

from arete.agent.capabilities.discovery import (
    _available_tools,
    _loaded,
    _profile,
    _registry,
    tool_instructions_suffix,
)
from arete.agent.context.sections import ContextSection, _panel_context_message
from arete.agent.runtime.policy import resolve_policy
from arete.agent.tools.toolkits import META_TOOLS
from arete.services.journal import journal_block


def _augment_tools(
    tools: list[Any], loaded: list[str], profile: str = "chat"
) -> list[Any]:
    """Meta-tools + tools of already-loaded toolkits, deduped by name.

    These reach the MODEL (schemas in the request). Execution of toolkit tools
    is handled in ``wrap_tool_call`` — the ToolNode does not know them.
    """
    if profile == "feedback":
        return [
            t
            for t in tools
            if getattr(t, "name", "")
            not in {"search_toolkits", "load_toolkit", "get_page_context"}
        ]
    out: list[Any] = list(tools)
    existing = {getattr(t, "name", "") for t in out}
    for tool in META_TOOLS:
        if tool.name not in existing:
            out.append(tool)
            existing.add(tool.name)
    for toolkit_id in loaded:
        tk = _registry(profile).get(toolkit_id)
        if tk is None:
            continue
        for tool in _available_tools(tk, profile):
            if tool.name not in existing:
                out.append(tool)
                existing.add(tool.name)
    return out


def build_context(request: ModelRequest):
    """Build a new request; never accumulate injected context in graph state."""
    profile_id = _profile(getattr(request, "runtime", None))
    profile = resolve_policy(profile_id).profile
    loaded = _loaded(getattr(request, "state", {}), profile_id)
    tools = _augment_tools(getattr(request, "tools", []), loaded, profile_id)
    system = getattr(request, "system_message", None)
    catalog = (
        "Skills disponibles (charger leurs outils avec load_toolkit):\n"
        + "\n".join(
            f"- {tk.id}: {tk.description}" for tk in _registry(profile_id).values()
        )
    )
    instructions = profile.instructions
    context = getattr(getattr(request, "runtime", None), "context", None)
    if profile.page_context and context is not None:
        today = context.current_date
        tomorrow = today + timedelta(days=1)
        instructions += (
            f"\nDate actuelle : {today.isoformat()}. Demain : {tomorrow.isoformat()}. "
            "Résous les dates relatives à partir de cette date, même si "
            "l’historique contient d’anciennes dates."
        )
    sections = [
        ContextSection("harness", system.text if system else "", "server"),
        ContextSection("profile", instructions, "server"),
        ContextSection("catalog", catalog if profile.capabilities else "", "registry"),
        ContextSection("capabilities", tool_instructions_suffix(loaded), "registry"),
        ContextSection("journal", journal_block(), "ledger"),
    ]
    overrides: dict[str, Any] = {
        "tools": tools,
        "system_message": SystemMessage(
            "\n\n".join(s.text for s in sections if s.text)
        ),
    }
    page = _panel_context_message(request) if profile.page_context else None
    if page is not None:
        overrides["messages"] = [*request.messages, page]
    return request.override(**overrides)


class ContextBudgetExceeded(ValueError):
    """The complete model request cannot fit after compaction."""


def validate_context(
    request: ModelRequest, *, context_tokens: int, output_tokens: int
) -> int:
    """Conservative estimate of the complete request after compaction.

    Tokenization is provider-dependent. Keep a margin and fail explicitly if
    the kept tail/schemas still exceed the configured deployment envelope.
    """
    from langchain_core.messages.utils import count_tokens_approximately

    messages = list(request.messages)
    if request.system_message is not None:
        messages.insert(0, request.system_message)
    estimate = count_tokens_approximately(messages, tools=request.tools)
    margin = max(1024, context_tokens // 10)
    available = context_tokens - output_tokens - margin
    if estimate > available:
        raise ContextBudgetExceeded(
            f"Contexte trop volumineux après compaction ({estimate:.0f} tokens estimés, "
            f"budget {available}). Réduis la demande ou ouvre un nouveau fil."
        )
    return int(estimate)
