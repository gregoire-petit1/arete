"""Runtime configuration, read from environment variables.

Single place that knows the variable names and defaults. Values are read on
each access (no caching) so tests can patch ``os.environ`` freely.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _env(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    return value if value not in (None, "") else default


class Config:
    # --- storage -----------------------------------------------------------
    @property
    def db_path(self) -> Path:
        return Path(_env("ARETE_DB", "data/arete.duckdb") or "data/arete.duckdb")

    @property
    def garmin_tokens_dir(self) -> Path:
        return Path(_env("ARETE_GARMIN_TOKENS_DIR", "data/garmin_tokens") or "")

    # --- LLM (tips + coaching agent) ----------------------------------------
    @property
    def llm_provider(self) -> str:
        return (_env("LLM_PROVIDER", "ollama") or "ollama").lower().strip()

    @property
    def llm_model(self) -> str | None:
        return _env("LLM_MODEL")

    @property
    def llm_context_tokens(self) -> int:
        # Deployment contract: especially for routers/local servers, the model
        # name alone does not establish the actual configured context window.
        value = int(_env("LLM_CONTEXT_TOKENS", "65536") or 65536)
        if value < 8192:
            raise ValueError("LLM_CONTEXT_TOKENS must be at least 8192")
        return value

    @property
    def ollama_base_url(self) -> str:
        return _env("OLLAMA_BASE_URL", "http://localhost:11434/v1") or ""

    @property
    def openrouter_api_key(self) -> str:
        return _env("OPENROUTER_API_KEY", "") or ""

    @property
    def github_token(self) -> str:
        return _env("GITHUB_TOKEN", "") or ""

    # --- Agent tracing (independent of inference credentials) --------------
    @property
    def langsmith_tracing(self) -> bool:
        raw = (_env("LANGSMITH_TRACING", "false") or "false").lower().strip()
        if raw not in ("true", "false"):
            raise ValueError("LANGSMITH_TRACING must be true or false")
        return raw == "true"

    @property
    def langsmith_api_key(self) -> str:
        return (_env("LANGSMITH_API_KEY", "") or "").strip()

    @property
    def langsmith_project(self) -> str:
        return _env("LANGSMITH_PROJECT", "Arete") or "Arete"

    @property
    def langsmith_endpoint(self) -> str:
        return (
            _env("LANGSMITH_ENDPOINT", "https://api.smith.langchain.com") or ""
        ).rstrip("/")

    @property
    def langsmith_workspace_id(self) -> str | None:
        return _env("LANGSMITH_WORKSPACE_ID")

    # --- Speech to text (dictated sessions) --------------------------------
    @property
    def stt_provider(self) -> str:
        """``openrouter`` or ``none``; ``none`` disables dictation entirely."""
        return (_env("STT_PROVIDER", "openrouter") or "none").lower().strip()

    @property
    def stt_model(self) -> str:
        return _env("STT_MODEL", "openai/whisper-large-v3-turbo") or ""

    @property
    def stt_base_url(self) -> str:
        """OpenAI-compatible base URL; point it at a local server to go offline."""
        return (_env("STT_BASE_URL", "https://openrouter.ai/api/v1") or "").rstrip("/")

    @property
    def stt_api_key(self) -> str:
        """Dedicated key, falling back to the OpenRouter one used for tips."""
        return _env("STT_API_KEY") or self.openrouter_api_key

    @property
    def stt_timeout_s(self) -> int:
        return int(_env("STT_TIMEOUT_S", "60") or 60)

    @property
    def stt_max_audio_mb(self) -> int:
        return int(_env("STT_MAX_AUDIO_MB", "10") or 10)

    # --- Garmin ------------------------------------------------------------
    @property
    def garmin_email(self) -> str | None:
        return _env("GARMIN_EMAIL")

    @property
    def garmin_password(self) -> str | None:
        return _env("GARMIN_PASSWORD")

    # --- Strava ------------------------------------------------------------
    @property
    def strava_client_id(self) -> str:
        return _env("STRAVA_CLIENT_ID", "") or ""

    @property
    def strava_client_secret(self) -> str:
        return _env("STRAVA_CLIENT_SECRET", "") or ""

    @property
    def strava_redirect_uri(self) -> str:
        return (
            _env("STRAVA_REDIRECT_URI", "http://localhost:8000/strava/callback") or ""
        )

    @property
    def frontend_url(self) -> str:
        return _env("FRONTEND_URL", "http://localhost:3080") or ""

    # --- background jobs / logging -----------------------------------------
    @property
    def auto_sync_hour(self) -> int | None:
        """Local hour (0-23) of the daily Garmin/Strava sync; None disables it.

        Garmin publishes the night's HRV and sleep score at wake-up, so an hour
        before the athlete is up leaves the day without recovery data.
        """
        raw = _env("ARETE_AUTO_SYNC_HOUR")
        if raw is None:
            return None
        hour = int(raw)
        if not 0 <= hour <= 23:
            raise ValueError("ARETE_AUTO_SYNC_HOUR must be between 0 and 23")
        return hour

    @property
    def log_level(self) -> str:
        return (_env("ARETE_LOG_LEVEL", "INFO") or "INFO").upper()


config = Config()
