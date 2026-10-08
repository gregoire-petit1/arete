"""Agent run context and panel-context budget constants.

Port of ``cortex_ai/agents/shared/contexts.py``, reduced to what Arete needs:
the panel carries the page the user is looking at (route + query params), not
an editable draft, so there is no live-draft machinery here.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import date
from typing import Any, Literal

from arete.agent.runtime.budget import MAX_TOOL_CONCURRENCY

#: Key under which the API layer stamps the open-page payload in the source
#: dict. The middleware in ``middlewares.py`` is the reader; ``api/agent.py``
#: is the only writer (same single-writer contract as Cortex's
#: ``agent-run-context.ts``).
PANEL_CONTEXT_KEY = "panel_context"

#: Budget for one serialized panel-context payload. Over it the injection is
#: SKIPPED, never truncated — half a JSON payload parses as a different page.
MAX_PANEL_CONTEXT_CHARS = 64_000

#: Route names the frontend can send. Anything else is rejected at the API
#: boundary so ``get_page_context`` can never be called with junk.
PANEL_PAGES = frozenset({"dashboard", "planning", "analytics", "log", "settings"})


@dataclass
class AgentContext:
    """Per-run context handed to ``create_agent(context_schema=...)``.

    ``source`` mirrors Cortex's ``BaseAgentContext.source``: a plain dict the
    API layer stamps before invoking the graph. Only ``PANEL_CONTEXT_KEY``
    inside it is read by the middleware.
    """

    source: dict[str, Any] = field(default_factory=dict)
    # Selected by the server entrypoint, never from panel_context or messages.
    profile: Literal["chat", "briefing", "feedback"] = "chat"
    thread_id: str | None = None
    current_date: date = field(default_factory=date.today)
    deadline: float | None = field(default=None, init=False)
    # Async ToolNode uses gather(), ignoring RunnableConfig concurrency.
    tool_slots: asyncio.Semaphore = field(
        default_factory=lambda: asyncio.Semaphore(MAX_TOOL_CONCURRENCY),
        init=False,
        repr=False,
    )

    @property
    def panel_context(self) -> dict[str, Any] | None:
        """Parsed ``source.panel_context`` payload, or None."""
        raw = self.source.get(PANEL_CONTEXT_KEY)
        if isinstance(raw, str) and raw:
            import json

            try:
                payload = json.loads(raw)
            except ValueError:
                return None
            return payload if isinstance(payload, dict) else None
        if isinstance(raw, dict):
            return raw
        return None
