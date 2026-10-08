"""Graph factory for the coaching deepagent.

Minimal port of Cortex's ``cortex_agent.py`` (ADR-0030): ``create_agent`` with
a context schema, one page-source tool, and two middlewares — runtime context
(panel page at the request tail) and the deepagents filesystem scoped to the
memory ledger. The full Cortex middleware stack (retry, budget, toolkits,
spawn) is deliberately out of scope for this first integration.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware

from arete.agent.context import AgentContext
from arete.agent.filesystem import build_memory_filesystem
from arete.agent.middlewares import RuntimeContextMiddleware, ToolEventMiddleware
from arete.agent.model import build_chat_model
from arete.agent.summarization import build_summarization
from arete.agent.system_skill import SYSTEM_SKILL
from arete.agent.toolkit_middleware import ToolkitMiddleware
from arete.agent.tools import get_page_context

logger = logging.getLogger(__name__)

#: Named bound on agent turns per run (tool-call loops included).
#:
#: Was 25 when the agent had one toolkit. With three, a single honest turn
#: runs page context, the ledger in, a toolkit search and load, three or four
#: reads, a second toolkit, its tool, then the ledger out — fifteen calls
#: before anything goes wrong. The evals hit the ceiling mid-answer twice,
#: which the athlete sees as an error rather than as a slow reply. Same budget
#: as the unattended briefing now.
AGENT_RECURSION_LIMIT = 40


@lru_cache(maxsize=1)
def get_agent():
    """Build (once) and return the compiled agent graph.

    The graph is process-wide: single user, single athlete. Raises ValueError
    from ``build_chat_model`` on misconfiguration — callers map it to a 500.
    """
    model = build_chat_model()
    graph = create_agent(
        model,
        tools=[get_page_context],
        middleware=[
            RuntimeContextMiddleware(),
            ToolEventMiddleware(),
            ToolkitMiddleware(),
            build_memory_filesystem(),
            # After the filesystem, the order deepagents uses itself. Chat
            # only: the briefing and the session feedback are single-turn and
            # bounded by their recursion limit, so there is nothing to
            # summarize and a model call to save.
            build_summarization(),
        ],
        system_prompt=SYSTEM_SKILL,
        context_schema=AgentContext,
        name="arete_coach",
    )
    logger.info(
        "Coaching agent initialized: model=%s", getattr(model, "model_name", "?")
    )
    return graph


@lru_cache(maxsize=4)
def build_unattended_agent(system_prompt: str, name: str):
    """A graph for work nobody is watching: the briefing, session feedback.

    Same tools and memory as the chat agent, two middlewares dropped on
    purpose: no RuntimeContextMiddleware (there is no open page) and no
    ToolEventMiddleware (there is no timeline to draw). Cached per prompt:
    one athlete, one process, a handful of unattended jobs.
    """
    model = build_chat_model()
    # Annotated: the list's inferred element type is the first entry's,
    # which is narrower than what create_agent accepts.
    middleware: list[AgentMiddleware[Any, Any, Any]] = [
        ToolkitMiddleware(),
        build_memory_filesystem(),
    ]
    graph = create_agent(
        model,
        tools=[get_page_context],
        middleware=middleware,
        system_prompt=f"{SYSTEM_SKILL}\n\nMission spécifique:\n{system_prompt}",
        context_schema=AgentContext,
        name=name,
    )
    logger.info(
        "Unattended agent %s initialized: model=%s",
        name,
        getattr(model, "model_name", "?"),
    )
    return graph


def build_briefing_agent():
    """The graph behind the daily briefing."""
    from arete.coach.briefing import BRIEFING_PROMPT

    return build_unattended_agent(BRIEFING_PROMPT, "arete_briefing")
