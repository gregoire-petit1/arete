"""Provider defaults and the configured model envelope; no network discovery."""

from dataclasses import dataclass

from pydantic import SecretStr

#: Named bounds, per TigerStyle: no silent SDK defaults on the agent loop.
AGENT_TEMPERATURE = 0.3
AGENT_MAX_TOKENS = 4096
#: A free model that hangs is not coming back: give up on the attempt after a
#: minute, or 30 s without a streamed chunk, and let the fallback list (or one
#: SDK retry) take over instead of burning the whole run deadline.
AGENT_TIMEOUT_SEC = 60
#: Free-tier providers (OpenRouter :free pool) 429 often; the SDK retries
#: 429/5xx with backoff, and OpenRouter tries the next model of the list.
AGENT_MAX_RETRIES = 2
AGENT_STREAM_CHUNK_TIMEOUT_SEC = 30

#: Free, tool-calling models, measured on 2026-10-09: both Nemotrons answered
#: a tool call in 1.3 s (Gemma 4 was rate-limited upstream). `openrouter/free`
#: (a random free model per request) closes the list. Free availability
#: changes weekly: LLM_MODEL and LLM_MODEL_FALLBACKS override both.
DEFAULT_OPENROUTER_MODEL = "nvidia/nemotron-3.5-lightning:free"
DEFAULT_OPENROUTER_FALLBACKS = (
    "nvidia/nemotron-3-super-120b-a12b:free",
    "openrouter/free",
)
#: OpenRouter rejects a longer `models` list with HTTP 400.
MAX_OPENROUTER_MODELS = 3

#: Default GitHub Models model: free tier, tool-calling capable.
DEFAULT_GITHUB_MODEL = "Meta-Llama-3.1-8B-Instruct"


@dataclass(frozen=True)
class ModelRoute:
    model: str
    base_url: str
    api_key: SecretStr
    context_tokens: int
    #: Tried in order by OpenRouter when the model above errors, is rate
    #: limited or down. Empty everywhere else.
    fallbacks: tuple[str, ...] = ()
