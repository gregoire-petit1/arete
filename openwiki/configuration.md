---
type: concept
title: Configuration Management
description: Environment variables, configuration sources, and runtime settings for the Arete application.
tags: [configuration, environment variables, settings]
verified:
  - by: openwiki/0.7.1
    at: 2026-10-09T21:28:29.291Z
sources:
  - id: openwiki-source-b465357f807c83adb7d1fddf
    resource: repo://src/arete/config.py
generated: { by: "openwiki/0.7.1", at: "2026-10-09T21:28:29.291Z" }
---

# Configuration Management

The Arete application uses environment variables for configuration, managed by a central `Config` class in `src/arete/config.py`. Configuration values are read from the environment on each access (no caching) to allow tests to patch `os.environ` freely.

## Claims

### Claim 1: Environment variable primary source
**Statement**: The central `Config` class in `src/arete/config.py` reads all configuration from environment variables, using `os.getenv()` as the primary source, with `python-dotenv` loaded values as fallback, and explicit defaults for every property.

**Evidence**: 
- `src/arete/config.py` line 17-19: `_env()` function uses `os.getenv(name)` 
- Line 14: `load_dotenv()` loads `.env` file values into the environment
- Each `Config` property (e.g., lines 24-25, 54-56, 98, 121-125, etc.) calls `_env(name, default)` to read environment variables

### Claim 2: No caching of configuration values
**Statement**: Configuration values are read on every property access (no caching), ensuring that tests can patch `os.environ` freely and see updated values without restarting the process.

**Evidence**: 
- `src/arete/config.py` line 3-5: "read on each access (no caching) so tests can patch ``os.environ`` freely"
- Each property is a `@property` that calls `_env()` on every access (e.g., lines 24-25, 54-56, 98, etc.)

### Claim 3: Default values for all configuration properties
**Statement**: Every configuration property in the `Config` class has an explicit default value that is used when the corresponding environment variable is not set or is empty.

**Evidence**: 
- `src/arete/config.py` throughout: Each property has a default in the `_env()` call (e.g., `"ollama"` at line 98, `"data/arete.duckdb"` at line 56, `65536` at line 114, `"http://localhost:11434/v1"` at line 121, `""` at lines 125/129, `"false"` at line 134, `"openrouter"` at line 161, `"openai/whisper-large-v3-turbo"` at line 165, `60` at line 179, `10` at line 183, `"http://localhost:8000/strava/callback"` at line 206, `"http://localhost:3080"` at line 211, `""` at lines 232-237, `"INFO"` at line 251)

### Claim 4: Validation of configuration values
**Statement**: Some configuration properties include runtime validation and raise `ValueError` when input is invalid (e.g., numeric range checks, allowed string values).

**Evidence**: 
- `src/arete/config.py` line 115-116: `LLM_CONTEXT_TOKENS` raises `ValueError` if value < 8192
- Line 225-226: `auto_sync_hour` raises `ValueError` if hour not in 0-23

### Claim 5: Database configuration supports local and remote modes
**Statement**: The `Config` class distinguishes between local DuckDB databases and remote MotherDuck databases via the `is_remote_db` property, which checks if `ARETE_DB` starts with `md:`.

**Evidence**: 
- `src/arete/config.py` lines 54-61: `db_target` property returns the `ARETE_DB` value; `is_remote_db` checks `self.db_target.startswith("md:")`

### Claim 6: Data directory adapts to database mode
**Statement**: The `data_dir` property adapts its base path depending on whether the database is local or remote: locally it uses the database file's parent directory, while remotely it defaults to `/tmp/arete-data`.

**Evidence**: 
- `src/arete/config.py` lines 69-81: `data_dir` property has conditional logic for `is_remote_db`

## Sources of Configuration

- **Environment variables**: Primary source, loaded via `python-dotenv` from a `.env` file (if present) and the process environment.
- **Defaults**: Each configuration property defines a fallback value if the environment variable is not set or is empty.
- **Validation**: Some properties include validation (e.g., numeric ranges, allowed strings) and raise `ValueError` on invalid input.

## Key Configuration Areas

The configuration is organized into logical sections:

### Database
- `ARETE_DB`: Path to the local DuckDB file or MotherDuck URI (e.g., `md:<database>`). Default: `data/arete.duckdb`.
- Derived properties:
  - `is_remote_db`: True when using MotherDuck.
  - `db_path`: Path object for the database (local only).
  - `data_dir`: Directory for non-database data (defaults to database's parent directory, or `/tmp/arete-data` for remote databases).

### Backend and Services
- `ARETE_LOG_LEVEL`: Logging level (default: `INFO`).
- `ARETE_AUTO_SYNC_HOUR`: Local hour (0-23) for daily Garmin/Strava sync; `None` disables it.
- `FRONTEND_URL`: Browser origin used for OAuth callbacks (e.g., `http://localhost:3080`).
- `CRON_SECRET`: Bearer token for Vercel Cron endpoint; empty disables the endpoint.

### LLM Provider (for tips and coaching agent)
- `LLM_PROVIDER`: One of `ollama`, `openrouter`, `github` (default: `ollama`).
- `LLM_MODEL`: Optional model override; if unset, uses provider-specific defaults.
- `LLM_MODEL_FALLBACKS`: Comma-separated list of OpenRouter model IDs to try after `LLM_MODEL`.
- `LLM_CONTEXT_TOKENS`: Configured context window size (minimum 8192, default 65536).
- `OLLAMA_BASE_URL`: Base URL for Ollama API (default: `http://localhost:11434/v1`).
- `OPENROUTER_API_KEY`: API key for OpenRouter.
- `GITHUB_TOKEN`: Personal access token for GitHub Models.

### Agent Tracing (LangSmith)
- `LANGSMITH_TRACING`: Enable/disable tracing (`true`/`false`, default: `false`).
- `LANGSMITH_API_KEY`: API key for LangSmith.
- `LANGSMITH_PROJECT`: Project name (default: `Arete`).
- `LANGSMITH_ENDPOINT`: API endpoint (default: `https://api.smith.langchain.com`).
- `LANGSMITH_WORKSPACE_ID`: Optional workspace ID for multi-workspace keys.

### Speech-to-Text (Dictated Sessions)
- `STT_PROVIDER`: `openrouter` or `none` (default: `none`; `none` disables dictation).
- `STT_MODEL`: Model identifier (default: `openai/whisper-large-v3-turbo`).
- `STT_BASE_URL`: Base URL for STT API (default: `https://openrouter.ai/api/v1`).
- `STT_API_KEY`: Dedicated API key; falls back to `OPENROUTER_API_KEY` if unset.
- `STT_TIMEOUT_S`: Request timeout in seconds (default: 60).
- `STT_MAX_AUDIO_MB`: Maximum audio file size in MB (default: 10).

### Garmin Connect
- `GARMIN_EMAIL`: Email for Garmin Connect login.
- `GARMIN_PASSWORD`: Password for Garmin Connect login.
- `ARETE_GARMIN_TOKENS_DIR`: Directory to store Garmin session tokens (default: `<data_dir>/garmin_tokens`).

### Strava
- `STRAVA_CLIENT_ID`: OAuth client ID from Strava.
- `STRAVA_CLIENT_SECRET`: OAuth client secret from Strava.
- `STRAVA_REDIRECT_URI`: OAuth redirect URI (default: `http://localhost:8000/strava/callback`).

### Web Push Notifications
- `WEB_PUSH_VAPID_PUBLIC_KEY`: VAPID public key (base64url) for browser subscription.
- `WEB_PUSH_VAPID_PRIVATE_KEY`: VAPID private key (base64url or PEM file path) for signing pushes.
- `WEB_PUSH_SUBJECT`: Contact URL for push services (default: `mailto:admin@localhost`).

## Usage in Code

Configuration is accessed via the global `config` instance imported from `src.arete.config`:

```python
from arete.config import config

# Example: get the database target
db_target = config.db_target
# Example: check if Google Calendar is configured
if config.google_calendar_configured:
    # ...
```

Each property is implemented as a `@property` that reads the environment variable on every access, ensuring up-to-date values and testability.

## Example Environment File

See [`.env.example`](repo:///.env.example) for a commented template of all supported environment variables.
