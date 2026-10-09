"""One optional, bounded completion; failures never invalidate the coach answer."""

import asyncio
import logging
from time import monotonic

from langchain.agents.middleware import ModelResponse
from langchain_core.language_models import BaseChatModel
from langchain_core.runnables import RunnableConfig
from openai import APIError

from arete.agent.context.builder import build_suggestion_context
from arete.agent.models.registry import SUGGESTION_TIMEOUT_SEC
from arete.agent.runtime.context import AgentContext
from arete.agent.runtime.events import MAX_SUGGESTION_CHARS
from arete.observability.agent import record_model_call, served_models

logger = logging.getLogger(__name__)


async def suggest_reply(
    messages,
    *,
    model: BaseChatModel,
    context_tokens: int,
    context: AgentContext,
    config: RunnableConfig,
) -> str | None:
    # Leave time for stream closure instead of risking the already-written answer
    # at the run deadline. The auxiliary request never retries.
    if (
        context.deadline is not None
        and context.deadline - monotonic() <= SUGGESTION_TIMEOUT_SEC + 1
    ):
        logger.info("Coach autosuggestion skipped: run deadline approaching")
        return None
    try:
        prompt = build_suggestion_context(
            messages, model=model, context_tokens=context_tokens
        )
    except ValueError as exc:
        logger.warning("Coach autosuggestion skipped: %s", exc)
        return None
    if prompt is None:
        return None
    assert context.stats.suggestion_calls == 0, "Only one suggestion per invocation"
    context.stats.suggestion_calls += 1
    context.stats.model_calls += 1
    started = monotonic()
    response = None
    error = None
    try:
        async with asyncio.timeout(SUGGESTION_TIMEOUT_SEC):
            answer = await model.ainvoke(
                prompt, config={**config, "run_name": "coach_autosuggestion"}
            )
        response = ModelResponse(result=[answer])
        text = answer.text.strip()
        if (
            answer.tool_calls
            or not text
            or len(text) > MAX_SUGGESTION_CHARS
            or "\n" in text
            or answer.response_metadata.get("finish_reason") == "length"
        ):
            logger.warning(
                "Coach autosuggestion rejected: finish_reason=%s chars=%d multiline=%s tool_calls=%d usage=%s",
                answer.response_metadata.get("finish_reason"),
                len(text),
                "\n" in text,
                len(answer.tool_calls),
                answer.usage_metadata,
            )
            raise ValueError("Expected one complete, short next-message draft")
        return text
    except (APIError, TimeoutError, ConnectionError, ValueError) as exc:
        error = type(exc).__name__
        logger.warning("Coach autosuggestion unavailable: %s", error)
        return None
    except BaseException as exc:
        error = type(exc).__name__
        raise
    finally:
        elapsed_ms = round((monotonic() - started) * 1000)
        context.stats.model_ms += elapsed_ms
        context.stats.served_models.extend(served_models(response))
        record_model_call(
            model=getattr(model, "model_name", "unknown"),
            elapsed_ms=elapsed_ms,
            response=response,
            error=error,
        )
