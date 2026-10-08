"""Optional follow-up suggestions after a successful chat answer.

One small, tool-free completion; its errors never replace the coach's answer.
Suggestions stay out of message history so they cannot become user intent.
"""

from __future__ import annotations

import asyncio
import logging
from time import monotonic

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field, field_validator

from arete.agent.prompts.suggestions import SUGGESTION_PROMPT
from arete.agent.runtime.context import AgentContext

logger = logging.getLogger(__name__)
MAX_SUGGESTIONS = 3
MAX_SUGGESTION_CHARS = 120
MAX_SUGGESTION_CONTEXT_CHARS = 8_000
SUGGESTION_MAX_TOKENS = 512
SUGGESTION_TIMEOUT_SECONDS = 8


class Suggestions(BaseModel):
    suggestions: list[str] = Field(max_length=MAX_SUGGESTIONS)

    @field_validator("suggestions")
    @classmethod
    def validate_suggestions(cls, values: list[str]) -> list[str]:
        cleaned = [v.strip() for v in values]
        if any(not v or len(v) > MAX_SUGGESTION_CHARS for v in cleaned):
            raise ValueError("Suggestion outside size bounds")
        if len({v.casefold() for v in cleaned}) != len(cleaned):
            raise ValueError("Duplicate suggestions")
        return cleaned


class SuggestionGenerator:
    def __init__(self, model):
        self.model = model

    def _messages(self, state, runtime):
        context = runtime.context
        if not isinstance(context, AgentContext) or context.profile != "chat":
            return None
        if (
            context.deadline is not None
            and context.deadline - monotonic() < SUGGESTION_TIMEOUT_SECONDS + 1
        ):
            logger.info("Suggestions skipped: insufficient run time remaining")
            return None
        messages = state["messages"]
        final = messages[-1]
        user = next(
            (m for m in reversed(messages) if isinstance(m, HumanMessage)), None
        )
        if (
            not isinstance(final, AIMessage)
            or final.tool_calls
            or not final.text
            or user is None
        ):
            return None
        text = (
            f"Question de l'athlète :\n{user.text}\n\nRéponse du coach :\n{final.text}"
        )
        if len(text) > MAX_SUGGESTION_CONTEXT_CHARS:
            logger.info("Suggestions skipped: exchange exceeds context bound")
            return None
        return [SystemMessage(SUGGESTION_PROMPT), HumanMessage(text)]

    def _model(self):
        return self.model

    def _publish(self, response):
        suggestions = Suggestions.model_validate_json(response.text).suggestions
        logger.info(
            "Auto-suggestions completed: count=%d usage=%s",
            len(suggestions),
            response.usage_metadata,
        )
        return {"suggestions": suggestions}

    def generate(self, state, runtime):
        messages = self._messages(state, runtime)
        if messages is None:
            return {"suggestions": []}
        try:
            return self._publish(self._model().invoke(messages))
        except Exception:
            logger.warning(
                "Auto-suggestions failed; preserving the answer", exc_info=True
            )
            return {"suggestions": []}

    async def agenerate(self, state, runtime):
        messages = self._messages(state, runtime)
        if messages is None:
            return {"suggestions": []}
        try:
            async with asyncio.timeout(SUGGESTION_TIMEOUT_SECONDS):
                return self._publish(await self._model().ainvoke(messages))
        except Exception:
            logger.warning(
                "Auto-suggestions failed; preserving the answer", exc_info=True
            )
            return {"suggestions": []}
