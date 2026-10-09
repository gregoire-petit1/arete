"""Assemble a graph from explicit dependencies; no business work or model routing."""

from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models import BaseChatModel

from arete.agent.middlewares.capabilities import ToolkitMiddleware
from arete.agent.middlewares.context import (
    ContextBudgetMiddleware,
    ContextBuilderMiddleware,
)
from arete.agent.middlewares.events import ToolEventMiddleware
from arete.agent.middlewares.limits import execution_limits
from arete.agent.middlewares.observability import ModelTelemetryMiddleware
from arete.agent.middlewares.policy import ProfilePolicyMiddleware
from arete.agent.profiles.models import AgentProfile
from arete.agent.prompts.coach import SYSTEM_SKILL
from arete.agent.runtime.context import AgentContext
from arete.agent.tools.journal import append_journal, remember_fact
from arete.agent.tools.pages import get_page_context
from arete.services.calendar import CalendarService


def build_agent(
    profile: AgentProfile,
    *,
    model: BaseChatModel,
    context_tokens: int,
    output_tokens: int,
    filesystem: AgentMiddleware[Any, Any, Any],
    calendar: CalendarService | None = None,
):
    middleware = [
        ProfilePolicyMiddleware(profile.id, profile=profile, calendar=calendar),
        *execution_limits(),
    ]
    if profile.page_context:
        middleware.append(ToolEventMiddleware())
    middleware.append(ToolkitMiddleware())
    if profile.journal_tools:
        middleware.append(filesystem)
    middleware.append(ContextBuilderMiddleware())
    middleware.append(
        ContextBudgetMiddleware(
            context_tokens=context_tokens, output_tokens=output_tokens
        )
    )
    middleware.append(ModelTelemetryMiddleware())
    return create_agent(
        model,
        tools=[
            *([get_page_context] if profile.page_context else []),
            *([append_journal, remember_fact] if profile.journal_tools else []),
        ],
        middleware=middleware,
        system_prompt=SYSTEM_SKILL,
        context_schema=AgentContext,
        name=profile.name,
    )
