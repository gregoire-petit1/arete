"""Server-selected capabilities shared by binding, context and authorization."""

from typing import Any

from langchain_core.tools import BaseTool

from arete.agent.capabilities.models import Toolkit
from arete.agent.capabilities.registry import CAPABILITIES
from arete.agent.runtime.context import AgentContext
from arete.agent.runtime.policy import ProfileSpec, resolve_policy


def _profile(runtime: Any) -> ProfileSpec:
    context = getattr(runtime, "context", None)
    return (
        (context.resolved_profile or context.profile)
        if isinstance(context, AgentContext)
        else "chat"
    )


def _registry(profile: ProfileSpec) -> dict[str, Toolkit]:
    policy = resolve_policy(profile)
    return {tid: CAPABILITIES[tid] for tid in policy.profile.capabilities}


def _available_tools(tk: Toolkit, profile: ProfileSpec) -> list[BaseTool]:
    policy = resolve_policy(profile)
    return [t for t in tk.tools if policy.can_execute(tk.id, t.name, tk.read_tools)]


def authorized_tools(profile: ProfileSpec) -> list[BaseTool]:
    return [
        tool
        for tk in _registry(profile).values()
        for tool in _available_tools(tk, profile)
    ]


def tool_instructions_suffix(profile: ProfileSpec) -> str:
    return "\n\n".join(tk.instructions for tk in _registry(profile).values())
