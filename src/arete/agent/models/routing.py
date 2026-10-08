"""Resolve server configuration before constructing a provider client."""

from pydantic import SecretStr

from arete.agent.models.registry import (
    DEFAULT_GITHUB_MODEL,
    DEFAULT_OPENROUTER_MODEL,
    ModelRoute,
)
from arete.config import config


def configured_model_name() -> str:
    defaults = {
        "ollama": "llama3.1:8b",
        "openrouter": DEFAULT_OPENROUTER_MODEL,
        "github": DEFAULT_GITHUB_MODEL,
    }
    return config.llm_model or defaults.get(config.llm_provider, "unknown")


def resolve_route() -> ModelRoute:
    provider = config.llm_provider
    if provider == "ollama":
        url, key = config.ollama_base_url, "ollama"
    elif provider == "openrouter":
        url, key = (
            "https://openrouter.ai/api/v1",
            config.openrouter_api_key,
        )
        if not key:
            raise ValueError(
                "OPENROUTER_API_KEY env var required for openrouter provider"
            )
    elif provider == "github":
        url, key = (
            "https://models.inference.ai.azure.com",
            config.github_token,
        )
        if not key:
            raise ValueError("GITHUB_TOKEN env var required for github provider")
    else:
        raise ValueError(
            f"Unknown LLM_PROVIDER '{provider}' for the agent. Supported: ollama, openrouter, github"
        )
    return ModelRoute(
        configured_model_name(), url, SecretStr(key), config.llm_context_tokens
    )
