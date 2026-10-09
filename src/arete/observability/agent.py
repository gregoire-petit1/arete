"""Normalize provider usage for structured logs, without claiming missing usage is zero."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def served_models(response: Any) -> list[str]:
    """Models the provider actually used; a router or fallback list may differ
    from the configured name."""
    return [
        name
        for m in getattr(response, "result", [])
        if (name := (getattr(m, "response_metadata", None) or {}).get("model_name"))
    ]


def record_model_call(
    *, model: str, elapsed_ms: int, response: Any = None, error: str | None = None
) -> None:
    usages = [
        m.usage_metadata
        for m in getattr(response, "result", [])
        if getattr(m, "usage_metadata", None)
    ]
    logger.info(
        "Agent model call: model=%s served=%s elapsed_ms=%d usage=%s error=%s",
        model,
        served_models(response) or None,
        elapsed_ms,
        usages or None,
        error,
    )


def record_run(
    *, profile: str, stats: Any, total_ms: int, error: str | None = None
) -> None:
    """One line per run: what a turn, a briefing or a feedback really cost."""
    logger.info(
        "Agent run: profile=%s calls=%d tools=%d model_ms=%d ttft_ms=%s "
        "total_ms=%d models=%s error=%s",
        profile,
        stats.model_calls,
        stats.tool_calls,
        stats.model_ms,
        stats.first_token_ms,
        total_ms,
        sorted(set(stats.served_models)) or None,
        error,
    )
