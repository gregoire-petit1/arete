"""The page-source tool: data behind each frontend page, as plain functions.

``get_page_context(page)`` is the "get source" surface of the sidepanel: the
agent calls it with the page the user is viewing (stamped in panel_context)
and receives the same JSON the React page renders. Pure reads over the
existing repositories/features — no LLM, no writes.
"""

from __future__ import annotations

import json

from langchain.tools import tool

from arete.agent.runtime.budget import MAX_TOOL_OUTPUT_CHARS
from arete.agent.runtime.context import PANEL_PAGES
from arete.services.pages import get_page_data

#: Bound on one tool result. Shared with the analytics toolkit so the two
#: read surfaces degrade at the same size.


@tool
def get_page_context(page: str) -> str:
    """Read the data behind an Arete app page: dashboard, planning, analytics,
    log or settings. Returns the same JSON the page renders — call this before
    answering questions about the athlete's training, and again when the page
    changes. Read-only."""
    if page not in PANEL_PAGES:
        return json.dumps(
            {"error": f"Unknown page '{page}'. Valid pages: {sorted(PANEL_PAGES)}"}
        )
    try:
        payload = get_page_data(page)
    except Exception as exc:
        # Operating error (empty DB, missing data): report it to the model
        # instead of failing the run — same contract as Cortex's tool error
        # handler. Never swallow silently.
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})

    rendered = json.dumps(payload, ensure_ascii=False, default=str)
    if len(rendered) > MAX_TOOL_OUTPUT_CHARS:
        # Bound the tool output (doctrine: bound everything). Degrade to the
        # page summary key rather than truncating mid-JSON.
        return json.dumps(
            {
                "error": (
                    f"Page '{page}' payload too large for one read "
                    f"({len(rendered)} chars). Ask for narrower slices "
                    "(e.g. shorter periods) instead."
                )
            }
        )
    return rendered
