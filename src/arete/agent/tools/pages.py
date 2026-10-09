"""The page-source tool: data behind each frontend page, as plain functions.

The open page's data is already in the system prompt (``context.sections``);
``get_page_context(page)`` reads another page, through the same
``services.pages`` reads. Pure reads — no LLM, no writes.
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
    """Read the data behind an Arete app page other than the one open, whose
    data is already in the prompt: dashboard, planning, analytics, log or
    settings. Fixed windows; use the analytics tools for a chosen period.
    Read-only."""
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
