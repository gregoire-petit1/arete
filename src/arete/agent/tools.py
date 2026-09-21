"""The page-source tool: data behind each frontend page, as plain functions.

``get_page_context(page)`` is the "get source" surface of the sidepanel: the
agent calls it with the page the user is viewing (stamped in panel_context)
and receives the same JSON the React page renders. Pure reads over the
existing repositories/features — no LLM, no writes.
"""

from __future__ import annotations

import json
from typing import Any

from langchain.tools import tool

from arete.agent.context import PANEL_PAGES

_MAX_TOOL_OUTPUT_CHARS = 32_000


def _dashboard() -> dict[str, Any]:
    from arete.api.metrics import get_player_stats

    return {"player_stats": get_player_stats().model_dump(mode="json")}


def _analytics() -> dict[str, Any]:
    from arete.api.analytics import get_overview

    return {"overview": get_overview(period="30d")}


def _planning() -> dict[str, Any]:
    from arete.api.garmin import list_planned_sessions

    # API default params are FastAPI Query objects; call with plain values.
    return {
        "planned_sessions": [
            s.model_dump(mode="json")
            for s in list_planned_sessions(start_date=None, end_date=None, status=None, limit=200)
        ]
    }


def _log() -> dict[str, Any]:
    from arete.api.analytics import list_sessions

    return {"recent_sessions": list_sessions(limit=20, offset=0)}


def _settings() -> dict[str, Any]:
    from arete.api.settings import get_settings

    return {"settings": get_settings()}


_PAGE_FETCHERS = {
    "dashboard": _dashboard,
    "analytics": _analytics,
    "planning": _planning,
    "log": _log,
    "settings": _settings,
}


@tool
def get_page_context(page: str) -> str:
    """Read the data behind an Arete app page: dashboard, planning, analytics,
    log or settings. Returns the same JSON the page renders — call this before
    answering questions about the athlete's training, and again when the page
    changes. Read-only."""
    fetcher = _PAGE_FETCHERS.get(page)
    if fetcher is None:
        return json.dumps(
            {"error": f"Unknown page '{page}'. Valid pages: {sorted(PANEL_PAGES)}"}
        )
    try:
        payload = fetcher()
    except Exception as exc:
        # Operating error (empty DB, missing data): report it to the model
        # instead of failing the run — same contract as Cortex's tool error
        # handler. Never swallow silently.
        return json.dumps({"error": f"{type(exc).__name__}: {exc}"})

    rendered = json.dumps(payload, ensure_ascii=False, default=str)
    if len(rendered) > _MAX_TOOL_OUTPUT_CHARS:
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
