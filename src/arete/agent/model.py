"""Provider mapping: existing LLM_* env vars → LangChain chat model.

Reuses ``arete.config`` verbatim — zero new env vars. ``ollama`` is the
generic OpenAI-compatible bucket (Ollama and LM Studio both speak that
protocol); the base URL decides which one actually answers.
"""

from __future__ import annotations

from langchain_openai import ChatOpenAI
from pydantic import SecretStr

from arete.config import config

#: Named bounds, per TigerStyle: no silent SDK defaults on the agent loop.
AGENT_TEMPERATURE = 0.3
AGENT_MAX_TOKENS = 4096
AGENT_TIMEOUT_SEC = 300
#: Free-tier providers (OpenRouter :free pool) 429 often and hang sometimes;
#: the SDK retries 429/5xx with backoff, the stream watchdog bounds hangs.
AGENT_MAX_RETRIES = 4
AGENT_STREAM_CHUNK_TIMEOUT_SEC = 300

#: Let OpenRouter select a free model supporting the request's tools, so we
#: do not maintain a fallback pool. LLM_MODEL can pin any OpenRouter model id.
DEFAULT_OPENROUTER_MODEL = "openrouter/free"

#: Default GitHub Models model: free tier, tool-calling capable.
DEFAULT_GITHUB_MODEL = "Meta-Llama-3.1-8B-Instruct"


def configured_model_name() -> str:
    """Shared by inference and trace metadata so their defaults cannot drift."""
    defaults = {
        "ollama": "llama3.1:8b",
        "openrouter": DEFAULT_OPENROUTER_MODEL,
        "github": DEFAULT_GITHUB_MODEL,
    }
    return config.llm_model or defaults.get(config.llm_provider, "unknown")


def build_chat_model() -> ChatOpenAI:
    """ChatOpenAI pointed at the configured provider.

    Raises ValueError on an unknown provider or missing credentials — the API
    layer surfaces it as a 500 with an actionable message instead of a silent
    degraded agent.
    """
    provider = config.llm_provider

    if provider == "ollama":
        # Generic OpenAI-compatible local server: Ollama or LM Studio.
        return ChatOpenAI(
            model=configured_model_name(),
            base_url=config.ollama_base_url,
            api_key=SecretStr(
                "ollama"
            ),  # local servers ignore the key; SDK requires one
            temperature=AGENT_TEMPERATURE,
            max_completion_tokens=AGENT_MAX_TOKENS,
            timeout=AGENT_TIMEOUT_SEC,
            max_retries=AGENT_MAX_RETRIES,
            stream_chunk_timeout=AGENT_STREAM_CHUNK_TIMEOUT_SEC,
        )

    if provider == "openrouter":
        api_key = config.openrouter_api_key
        if not api_key:
            raise ValueError(
                "OPENROUTER_API_KEY env var required for openrouter provider"
            )
        return ChatOpenAI(
            model=configured_model_name(),
            base_url="https://openrouter.ai/api/v1",
            api_key=SecretStr(api_key),
            temperature=AGENT_TEMPERATURE,
            max_completion_tokens=AGENT_MAX_TOKENS,
            timeout=AGENT_TIMEOUT_SEC,
            max_retries=AGENT_MAX_RETRIES,
            stream_chunk_timeout=AGENT_STREAM_CHUNK_TIMEOUT_SEC,
        )

    if provider == "github":
        api_key = config.github_token
        if not api_key:
            raise ValueError("GITHUB_TOKEN env var required for github provider")
        # GitHub Models speaks the OpenAI protocol behind its own base URL.
        return ChatOpenAI(
            model=configured_model_name(),
            base_url="https://models.inference.ai.azure.com",
            api_key=SecretStr(api_key),
            temperature=AGENT_TEMPERATURE,
            max_completion_tokens=AGENT_MAX_TOKENS,
            timeout=AGENT_TIMEOUT_SEC,
            max_retries=AGENT_MAX_RETRIES,
            stream_chunk_timeout=AGENT_STREAM_CHUNK_TIMEOUT_SEC,
        )

    raise ValueError(
        f"Unknown LLM_PROVIDER '{provider}' for the agent. "
        "Supported: ollama, openrouter, github"
    )
