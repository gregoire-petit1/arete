"""Adapt the central context builder to model interception."""

from functools import partial

from anyio import to_thread
from langchain.agents.middleware import AgentMiddleware

from arete.agent.context.builder import build_context, validate_context


class ContextBuilderMiddleware(AgentMiddleware):
    def __init__(self, *, context_tokens: int | None = None, output_tokens: int = 4096):
        self.context_tokens = context_tokens
        self.output_tokens = output_tokens

    def wrap_model_call(self, request, handler):
        return handler(
            build_context(
                request,
                context_tokens=self.context_tokens,
                output_tokens=self.output_tokens,
            )
        )

    async def awrap_model_call(self, request, handler):
        built = await to_thread.run_sync(
            partial(
                build_context,
                request,
                context_tokens=self.context_tokens,
                output_tokens=self.output_tokens,
            )
        )
        return await handler(built)


class ContextBudgetMiddleware(AgentMiddleware):
    """Final preflight after all contributions."""

    def __init__(self, *, context_tokens: int, output_tokens: int):
        self.context_tokens = context_tokens
        self.output_tokens = output_tokens

    def _check(self, request):
        validate_context(
            request,
            context_tokens=self.context_tokens,
            output_tokens=self.output_tokens,
        )

    def wrap_model_call(self, request, handler):
        self._check(request)
        return handler(request)

    async def awrap_model_call(self, request, handler):
        self._check(request)
        return await handler(request)
