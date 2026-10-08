"""Provider defaults and the configured model envelope; no network discovery."""

from dataclasses import dataclass

from pydantic import SecretStr

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


@dataclass(frozen=True)
class ModelRoute:
    model: str
    base_url: str
    api_key: SecretStr
    context_tokens: int
