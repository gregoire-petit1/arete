"""LLM provider abstraction layer.

Supports multiple backends via OpenAI-compatible SDK:
- Ollama (local, free)
- OpenRouter (cloud, pay-per-token)
- GitHub Models (cloud, included in Copilot Enterprise)

Configuration via environment variables:
    LLM_PROVIDER: ollama | openrouter | github (default: ollama)
    LLM_MODEL: model name (default depends on provider)
    OLLAMA_BASE_URL: Ollama API URL (default: http://localhost:11434/v1)
    OPENROUTER_API_KEY: OpenRouter API key
    GITHUB_TOKEN: GitHub personal access token
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

from arete.config import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Provider configuration
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProviderConfig:
    """Configuration for an LLM provider."""

    name: str
    base_url: str
    api_key: str
    default_model: str
    supports_json_mode: bool = True


# Default models per provider
_DEFAULT_MODELS: dict[str, str] = {
    "ollama": "llama3.1:8b",
    "openrouter": "meta-llama/llama-3.1-8b-instruct:free",
    "github": "Meta-Llama-3.1-8B-Instruct",
}


def _resolve_provider_config() -> ProviderConfig:
    """Build provider config from environment variables.

    Returns:
        ProviderConfig ready to use with OpenAI SDK.

    Raises:
        ValueError: If required env vars are missing for the chosen provider.
    """
    provider = config.llm_provider
    model_override = config.llm_model

    if provider == "ollama":
        base_url = config.ollama_base_url
        return ProviderConfig(
            name="ollama",
            base_url=base_url,
            api_key="ollama",  # Ollama ignores the key but SDK requires one
            default_model=model_override or _DEFAULT_MODELS["ollama"],
        )

    if provider == "openrouter":
        api_key = config.openrouter_api_key
        if not api_key:
            raise ValueError(
                "OPENROUTER_API_KEY env var required for openrouter provider"
            )
        return ProviderConfig(
            name="openrouter",
            base_url="https://openrouter.ai/api/v1",
            api_key=api_key,
            default_model=model_override or _DEFAULT_MODELS["openrouter"],
        )

    if provider == "github":
        api_key = config.github_token
        if not api_key:
            raise ValueError("GITHUB_TOKEN env var required for github provider")
        return ProviderConfig(
            name="github",
            base_url="https://models.inference.ai.azure.com",
            api_key=api_key,
            default_model=model_override or _DEFAULT_MODELS["github"],
        )

    raise ValueError(
        f"Unknown LLM_PROVIDER '{provider}'. Supported: ollama, openrouter, github"
    )


# ---------------------------------------------------------------------------
# Client factory (singleton)
# ---------------------------------------------------------------------------

_client: OpenAI | None = None
_config: ProviderConfig | None = None


def get_provider_config() -> ProviderConfig | None:
    """Return the current provider config, or None if not yet resolved."""
    global _config
    if _config is None:
        try:
            _config = _resolve_provider_config()
        except ValueError as exc:
            logger.warning("LLM provider not configured: %s", exc)
            return None
    return _config


def get_llm_client() -> OpenAI | None:
    """Get or create the LLM client singleton.

    Returns None if the provider is not configured.
    """
    global _client, _config

    if _client is not None:
        return _client

    cfg = get_provider_config()
    if cfg is None:
        return None

    _client = OpenAI(
        api_key=cfg.api_key,
        base_url=cfg.base_url,
        # Without this the SDK waits 600 s: a hung Ollama would hold a request.
        timeout=config.llm_timeout_s,
        max_retries=1,
    )
    logger.info(
        "LLM client initialized: provider=%s, model=%s", cfg.name, cfg.default_model
    )
    return _client


def get_default_model() -> str:
    """Return the default model for the configured provider."""
    cfg = get_provider_config()
    if cfg is None:
        return _DEFAULT_MODELS["ollama"]
    return cfg.default_model


def reset_client() -> None:
    """Reset the singleton client (useful for testing)."""
    global _client, _config
    _client = None
    _config = None


# ---------------------------------------------------------------------------
# High-level generate helper
# ---------------------------------------------------------------------------


def generate(
    system_prompt: str,
    user_prompt: str,
    *,
    model: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 800,
    json_mode: bool = False,
) -> str | None:
    """Generate a completion using the configured provider.

    Args:
        system_prompt: System-level instructions.
        user_prompt: User message.
        model: Override model name (uses default if None).
        temperature: Sampling temperature.
        max_tokens: Maximum completion tokens.
        json_mode: Request JSON output format.

    Returns:
        Generated text, or None if LLM is unavailable.
    """
    client = get_llm_client()
    if client is None:
        return None

    cfg = get_provider_config()
    if cfg is None:
        return None

    use_model = model or cfg.default_model

    kwargs: dict[str, Any] = {
        "model": use_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }

    if json_mode and cfg.supports_json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    try:
        response = client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content
        return content if content else None

    except Exception:
        logger.exception(
            "LLM generation failed (provider=%s, model=%s)", cfg.name, use_model
        )
        return None
