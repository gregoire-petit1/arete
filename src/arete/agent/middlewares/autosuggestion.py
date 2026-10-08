"""Completion-hook adapter for optional follow-up generation."""

from langchain.agents.middleware import AgentMiddleware
from langgraph.config import get_stream_writer

from arete.agent.nodes.suggestions import SuggestionGenerator
from arete.agent.runtime.events import FollowupsGenerated
from arete.agent.runtime.state import CoachState


class AutoSuggestionMiddleware(AgentMiddleware):
    state_schema = CoachState

    def __init__(self, generator: SuggestionGenerator):
        self.generator = generator

    def _publish(self, update: dict) -> dict:
        if update["suggestions"]:
            event: FollowupsGenerated = {
                "type": "suggestions",
                "suggestions": update["suggestions"],
            }
            get_stream_writer()(event)
        return update

    def after_agent(self, state, runtime):
        return self._publish(self.generator.generate(state, runtime))

    async def aafter_agent(self, state, runtime):
        return self._publish(await self.generator.agenerate(state, runtime))
