"""Adapt graph completion to a next-message draft and a custom stream event."""

from langchain.agents.middleware import AgentMiddleware
from langchain_core.language_models import BaseChatModel
from langgraph.config import get_config

from arete.agent.runtime.autosuggestion import suggest_reply
from arete.agent.runtime.state import CoachState


class AutoSuggestionMiddleware(AgentMiddleware):
    state_schema = CoachState

    def __init__(self, *, model: BaseChatModel, context_tokens: int):
        self.model = model
        self.context_tokens = context_tokens

    def after_agent(self, state, runtime):
        # Production runs are async, including scheduled work bridged by AnyIO.
        assert not getattr(runtime.context, "suggest_reply", False), (
            "Suggestions require async invocation"
        )
        return None

    async def aafter_agent(self, state, runtime):
        context = runtime.context
        if context is None or context.profile != "chat" or not context.suggest_reply:
            return None
        text = await suggest_reply(
            state["messages"],
            model=self.model,
            context_tokens=self.context_tokens,
            context=context,
            config=get_config(),
        )
        if text is None:
            return None
        runtime.stream_writer({"type": "suggestion", "text": text})
        return {"suggestion": text}
