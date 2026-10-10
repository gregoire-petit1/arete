"""Validate each provider attempt inside the existing fallback boundary."""

from langchain.agents.middleware import AgentMiddleware

from arete.agent.models.responses import validate_model_response


class ModelResponseMiddleware(AgentMiddleware):
    def wrap_model_call(self, request, handler):
        response = handler(request)
        validate_model_response(response)
        return response

    async def awrap_model_call(self, request, handler):
        response = await handler(request)
        validate_model_response(response)
        return response
