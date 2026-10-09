"""Application composition for chat, API cards and scheduled coaching.

Only this composition root imports the agent factory. Domain producers receive
plain callbacks, so they remain usable and testable without an agent framework.
"""

from dataclasses import replace
from datetime import date
from functools import lru_cache, wraps
from threading import Lock
from typing import Literal

from arete.agent.backends.memory import build_memory_filesystem
from arete.agent.factory import build_agent
from arete.agent.models.providers import build_chat_model
from arete.agent.models.registry import (
    AGENT_MAX_TOKENS,
    SUGGESTION_MAX_TOKENS,
    SUGGESTION_TEMPERATURE,
    SUGGESTION_TIMEOUT_SEC,
)
from arete.agent.models.routing import resolve_route
from arete.agent.profiles.catalog import get_profile
from arete.agent.runtime.budget import MAX_GRAPH_STEPS
from arete.agent.runtime.context import AgentContext
from arete.agent.runtime.execution import invoke_agent_sync
from arete.calendar import get_calendar_service
from arete.config import config
from arete.services import briefing, session_feedback, weekly_review
from arete.services.coaching_repository import Briefing

AGENT_RECURSION_LIMIT = MAX_GRAPH_STEPS


_graph_lock = Lock()


def _serialized(factory):
    # lru_cache allows duplicate construction during concurrent first access.
    @wraps(factory)
    def get():
        with _graph_lock:
            return factory()

    get.cache_clear = factory.cache_clear
    return get


def _assemble(profile_id: str):
    profile = get_profile(profile_id)
    calendar = None
    if profile_id == "chat" and config.google_calendar_configured:
        calendar = get_calendar_service()
        profile = replace(
            profile,
            capabilities=(*profile.capabilities, "calendar"),
            preloaded=(*profile.preloaded, "calendar"),
        )
    route = resolve_route()
    model = build_chat_model(route=route)
    suggestion_model = None
    if profile.id == "chat":
        suggestion_model = build_chat_model(
            route=route,
            max_tokens=SUGGESTION_MAX_TOKENS,
            timeout=SUGGESTION_TIMEOUT_SEC,
            max_retries=0,
            temperature=SUGGESTION_TEMPERATURE,
            # Reasoning shares the output budget and can consume all 512 tokens
            # before producing any visible text for this simple drafting task.
            openrouter_reasoning=False,
        )
        # Keep auxiliary tokens out of the coach's answer stream. LangChain
        # still records the provider request as a child LLM span.
        suggestion_model = suggestion_model.model_copy(
            update={"disable_streaming": True}
        )
    return build_agent(
        profile,
        model=model,
        context_tokens=route.context_tokens,
        output_tokens=AGENT_MAX_TOKENS,
        filesystem=build_memory_filesystem(),
        calendar=calendar,
        suggestion_model=suggestion_model,
    )


@_serialized
@lru_cache(maxsize=1)
def get_agent():
    return _assemble("chat")


@_serialized
@lru_cache(maxsize=1)
def build_briefing_agent():
    return _assemble("briefing")


@_serialized
@lru_cache(maxsize=1)
def build_feedback_agent():
    return _assemble("feedback")


@_serialized
@lru_cache(maxsize=1)
def build_review_agent():
    return _assemble("review")


def _run_mission(graph, profile: str, message: str, max_chars: int) -> str:
    result = invoke_agent_sync(
        graph,
        {"messages": [{"role": "user", "content": message}]},
        context=AgentContext(profile=profile),  # type: ignore[arg-type]
    )
    messages = result.get("messages", [])
    if not messages:
        raise RuntimeError("Agent returned no messages")
    text = (messages[-1].text or "").strip()
    if not text:
        raise RuntimeError("Agent returned an empty answer")
    if len(text) > max_chars:
        raise RuntimeError(
            f"Answer too long for the {profile} card ({len(text)} chars)"
        )
    return text


def run_briefing(facts: str) -> str:
    return _run_mission(
        build_briefing_agent(), "briefing", facts, briefing.MAX_BRIEFING_CHARS
    )


def run_feedback(facts: str) -> str:
    return _run_mission(
        build_feedback_agent(), "feedback", facts, session_feedback.MAX_FEEDBACK_CHARS
    )


def run_review(facts: str) -> str:
    return _run_mission(
        build_review_agent(), "review", facts, weekly_review.MAX_REVIEW_CHARS
    )


def generate_weekly_review(*, refresh: bool = False) -> weekly_review.Review:
    return weekly_review.generate_review(run_review, refresh=refresh)


def generate_briefing(
    *, trigger: str = "api", target_date: date | None = None, user_id: int = 1
) -> Briefing:
    return briefing.generate_briefing(
        produce=run_briefing, trigger=trigger, target_date=target_date, user_id=user_id
    )


def get_or_create_briefing(
    *, trigger: str = "api", target_date: date | None = None, user_id: int = 1
) -> Briefing:
    return briefing.get_or_create_briefing(
        produce=run_briefing, trigger=trigger, target_date=target_date, user_id=user_id
    )


def enrich_session_feedback(
    rule_feedback: str,
    highlights: list[str],
    evidence: session_feedback.SessionEvidence | None = None,
) -> tuple[str, Literal["agent", "rules"]]:
    return session_feedback.enrich_session_feedback(
        rule_feedback, highlights, produce=run_feedback, evidence=evidence
    )
