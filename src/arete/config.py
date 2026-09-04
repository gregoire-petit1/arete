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

    # --- LLM (tips only) ---------------------------------------------------
    @property
    def llm_provider(self) -> str:
        return (_env("LLM_PROVIDER", "ollama") or "ollama").lower().strip()

    @property
    def llm_model(self) -> str | None:
        return _env("LLM_MODEL")

    @property
    def ollama_base_url(self) -> str:
        return _env("OLLAMA_BASE_URL", "http://localhost:11434/v1") or ""

    @property
    def openrouter_api_key(self) -> str:
        return _env("OPENROUTER_API_KEY", "") or ""

    @property
    def github_token(self) -> str:
        return _env("GITHUB_TOKEN", "") or ""

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
        """Local hour (0-23) of the nightly Garmin/Strava sync; None disables it."""
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
