"""Single cached coach graph for chat, daily briefing, and session feedback."""

from __future__ import annotations

import logging
from functools import lru_cache

from langchain.agents import create_agent

from arete.agent.context import AgentContext
from arete.agent.filesystem import build_memory_filesystem
from arete.agent.journal_memory import JournalMemoryMiddleware
from arete.agent.middlewares import (
    RuntimeContextMiddleware,
    TaskInstructionsMiddleware,
    ToolEventMiddleware,
)
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
            TaskInstructionsMiddleware(),
            RuntimeContextMiddleware(),
            ToolEventMiddleware(),
            ToolkitMiddleware(),
            # After the task instructions and the toolkits, so the journal
            # ends the system prompt and what comes before it keeps the same
            # prefix from call to call. One graph serves chat, briefing and
            # session feedback, so all three get it from here.
            JournalMemoryMiddleware(),
            build_memory_filesystem(),
            # After the filesystem, the order deepagents uses itself. Chat
            # only: the briefing and the session feedback are single-turn and
            # bounded by their recursion limit, so there is nothing to
            # summarize and a model call to save.
            build_summarization(model),
        ],
        system_prompt=SYSTEM_SKILL,
        context_schema=AgentContext,
        name="arete_coach",
    )
    logger.info(
        "Coaching agent initialized: model=%s", getattr(model, "model_name", "?")
    )
    return graph
