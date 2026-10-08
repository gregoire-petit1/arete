"""Assert that invocation policy matches the server-selected compiled profile."""

from langchain.agents.middleware import AgentMiddleware

from arete.agent.runtime.context import AgentContext


class ProfilePolicyMiddleware(AgentMiddleware):
    def __init__(self, profile_id: str):
        self.profile_id = profile_id

    def before_agent(self, state, runtime):
        context = runtime.context
        assert isinstance(context, AgentContext), "Server invocation context required"
        assert context.profile == self.profile_id, (
            "Invocation profile differs from compiled policy"
        )
        return None

    async def abefore_agent(self, state, runtime):
        return self.before_agent(state, runtime)
