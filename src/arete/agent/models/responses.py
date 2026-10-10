"""Reject completions that cannot advance a text-and-tool conversation."""

from langchain.agents.middleware.types import ModelResponse
from langchain_core.messages import AIMessage


class EmptyModelResponseError(RuntimeError):
    def __init__(self, response: ModelResponse):
        # Keep usage available to telemetry even when a provider spends its
        # entire output allowance on reasoning without answering.
        self.response = response
        super().__init__("Le modèle n'a produit ni réponse ni appel d'outil.")


def validate_model_response(response: ModelResponse) -> None:
    if not any(
        isinstance(message, AIMessage) and (message.text.strip() or message.tool_calls)
        for message in response.result
    ):
        # Do not rely on finish_reason: providers can return empty `stop`
        # completions, and streaming can concatenate metadata (lengthlength).
        raise EmptyModelResponseError(response)
