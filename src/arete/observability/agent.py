"""Normalize provider usage for structured logs, without claiming missing usage is zero."""

import logging
from typing import Any

logger = logging.getLogger(__name__)


def record_model_call(
    *, model: str, elapsed_ms: int, response: Any = None, error: str | None = None
) -> None:
    usages = [
        m.usage_metadata
        for m in getattr(response, "result", [])
        if getattr(m, "usage_metadata", None)
    ]
    logger.info(
        "Agent model call: model=%s elapsed_ms=%d usage=%s error=%s",
        model,
        elapsed_ms,
        usages or None,
        error,
    )
