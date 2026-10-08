"""Measure the model boundary after context assembly and compaction."""

from time import monotonic

from langchain.agents.middleware import AgentMiddleware

from arete.observability.agent import record_model_call


class ModelTelemetryMiddleware(AgentMiddleware):
    def _record(self, request, started, response=None, error=None):
        record_model_call(
            model=getattr(request.model, "model_name", "unknown"),
            elapsed_ms=round((monotonic() - started) * 1000),
            response=response,
            error=error,
        )

    def wrap_model_call(self, request, handler):
        started = monotonic()
        try:
            response = handler(request)
        except Exception as exc:
            self._record(request, started, error=type(exc).__name__)
            raise
        self._record(request, started, response=response)
        return response

    async def awrap_model_call(self, request, handler):
        started = monotonic()
        try:
            response = await handler(request)
        except Exception as exc:
            self._record(request, started, error=type(exc).__name__)
            raise
        self._record(request, started, response=response)
        return response
