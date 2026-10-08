# Arete

[![CI](https://github.com/gregoire-petit1/arete/actions/workflows/ci.yml/badge.svg)](https://github.com/gregoire-petit1/arete/actions/workflows/ci.yml)

> **Arete (ἀρετή)** — an ancient Greek concept meaning _excellence_ or _virtue_,
> achieved when one fulfills their highest potential through discipline, balance, and mastery.

Self-hosted, single-user training assistant:

- **Garmin Connect & Strava sync** of activities (FIT parsing, HR zones, best efforts) and daily health metrics (HRV, sleep, body battery, readiness score).
- **Analytics**: volume, CTL/ATL/TSB (Banister model with personalized coefficients), pace trends, HR drift / aerobic decoupling, cardiac efficiency.
- **Strength log** with a free-text workout parser (Lark grammar + fuzzy catalog matching, no LLM), muscle-volume heatmap and Garmin activity linking.
- **Planning**: planned sessions matched against actual activities, adherence dashboard.
- **Coaching agent** (side panel, daily briefing, session feedback) with a markdown memory ledger, through any OpenAI-compatible provider: Ollama, OpenRouter or GitHub Models ([design](docs/plans/2026-09-21-coaching-agent-design.md)). A rule engine is the fallback whenever the model is unavailable.

## Stack

- **Backend**: Python 3.11, FastAPI + Pydantic v2, DuckDB, `garminconnect` (Garmin Connect, unofficial API), `fitparse`, `lark` (workout grammar), LangChain + `deepagents`, `openai` SDK (agent, speech-to-text).
- **Frontend**: React 19 + Vite, Tailwind 4, TanStack Query, recharts, PWA (see `frontend/README.md`).
- **Tooling**: uv, ruff, mypy, pytest; Docker Compose (backend + nginx-served frontend).

## Quickstart (local)

```bash
git clone https://github.com/gregoire-petit1/arete.git && cd arete
make dev        # http://localhost:5173 (app), http://127.0.0.1:8000/docs (API)
```

`make dev` installs what is missing (`uv sync`, `npm ci`, `.env` copied from `.env.example`; edit it as needed), then runs the API with auto-reload and the Vite dev server with hot module replacement. Ctrl-C stops both; if either exits, the other is stopped too. Ports: `make dev BACKEND_PORT=8002 FRONTEND_PORT=5174`. `make backend` / `make frontend` run one side alone, `make check` runs what CI runs, `make` lists every target.

The Vite dev server proxies `/api/*` to the backend. The schema is (re)initialized on every backend start; scripts that run without the API need `uv run python -c "from arete.dataio.init_duckdb import main; main()"` first.

## Docker

```bash
make docker    # copies .env.example to .env if missing (compose reads env_file .env), then docker compose up --build
# frontend: http://localhost:3080   backend: http://localhost:8001 (8000 is often taken)
```

Data (DuckDB file, Garmin tokens, FIT files) is the repo's `./data` directory, bind-mounted at `/app/data`, so Docker and `uv run uvicorn` share the same database (never run both backends at once: DuckDB allows a single writer). The compose file enables the daily sync (`TZ=Europe/Paris` + `ARETE_AUTO_SYNC_HOUR=9`, after wake-up: Garmin only publishes the night's HRV and sleep score once the athlete is up; the scheduler checks the wall clock every five minutes and catches up a run missed while the machine slept) and sets `FRONTEND_URL` for the 3080 frontend; with `restart: unless-stopped` the stack comes back whenever Docker starts. Ollama is expected on the Docker host (`host.docker.internal:11434`); uncomment the `ollama` service in `docker-compose.yml` to run it in Docker instead.

## Configuration

All settings come from environment variables (see `.env.example`):

| Variable | Purpose |
| --- | --- |
| `ARETE_DB` | DuckDB file path (default `data/arete.duckdb`) |
| `ARETE_LOG_LEVEL` | Backend log level (default `INFO`) |
| `ARETE_AUTO_SYNC_HOUR` | Local hour of the daily Garmin activities + health and Strava sync, best set after wake-up; unset = manual only |
| `LLM_PROVIDER`, `LLM_MODEL` | `ollama` \| `openrouter` \| `github`, and the model name |
| `OLLAMA_BASE_URL` / `OPENROUTER_API_KEY` / `GITHUB_TOKEN` | Credentials for the chosen provider |
| `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_REDIRECT_URI` | Strava OAuth app |
| `FRONTEND_URL` | Where the Strava callback redirects (default `http://localhost:3080`) |
| `GARMIN_EMAIL`, `GARMIN_PASSWORD` | Garmin Connect login (or log in from the Settings page) |
| `ARETE_GARMIN_TOKENS_DIR` | Where the Garmin session tokens are stored (default `data/garmin_tokens`) |

The agent reuses `LLM_PROVIDER` / `LLM_MODEL` and needs a tool-calling model; its memory ledger sits next to the database, in `data/agent/memory/`.

For free hosted inference, set `LLM_PROVIDER=openrouter` and `OPENROUTER_API_KEY`,
and leave `LLM_MODEL` unset (or set it to `openrouter/free`). The
[Free Models Router](https://openrouter.ai/openrouter/free) selects an available
free model supporting the request's tools. Rate limits, latency and model quality
can vary. Set `LLM_MODEL` to pin a specific model; Arete sends no fallback list.

## Project layout

```
src/arete/
├── config.py   All environment variables in one place; scheduler.py: optional daily sync
├── agent/      Coaching agent: graph + model, page-context tool, toolkits (progressive loading), markdown memory ledger, /agent routes
├── api/        FastAPI routers: analytics, garmin (sessions/FIT), garmin_sync, garmin_health, strength, strava, ai_tips, metrics, settings; main.py wires them
├── dataio/     DuckDB connection (db.py), schema + versioned migrations (init_duckdb.py), shared queries, user settings
├── features/   Training science: workload (ACWR), cardio (TRIMP, zones), fitness (CTL/ATL/TSB), strength (1RM, INOL), banister fit, hr_drift, recommendations
├── garmin/     FIT parser, time-series metrics, planned/actual matching, Garmin Connect client + activity/health sync, readiness
├── strength/   Strength models + repository (exercises, sessions, sets, PRs)
├── strava/     Strava API client and activity mapping
├── llm/        Workout grammar + text parser (no LLM), speech-to-text for dictated sessions
└── data/       Exercise catalog
frontend/       React app (pages: Dashboard, Planning, Analytics, Log, Settings)
scripts/        fit_banister.py (fit personal CTL/ATL coefficients), garmin_login.py (one-time token bootstrap)
tests/          pytest suite (isolated temp DuckDB via ARETE_DB, no network)
docs/plans/     Design documents
```

## API overview

Interactive docs at `/docs`. Routers and their prefixes:

| Prefix | Highlights |
| --- | --- |
| `/health`, `/settings` | Health check; user settings GET/PUT |
| `/analytics` | `volume`, `training-load`, `pace`, `hr-zones`, `sport-distribution`, `best-efforts`, `cardiac-efficiency`, `hr-pace-scatter`, `hr-drift`, `sessions` (GET, PATCH `/{id}`) |
| `/metrics` | `workload`, `fitness`, `player-stats`, `recommendations`; calculators `cardio/trimp`, `strength/1rm`, `strength/inol` (POST) |
| `/garmin` | `planned` (list/create/delete), `upload-fit`, `actual`, `summary`, `sync/{status,login,logout,activities}` |
| `/garmin/health` | `sync` (POST), `daily`, `range`, `status` |
| `/strength` | `exercises` CRUD + `/{id}/prs`, `sessions` CRUD, `sessions/parse` (free-text → structured, optional save), Garmin linking, `stats/volume-by-muscle` |
| `/strava` | `authorize`, `callback`, `status`, `sync` (POST, `days` or `full: true` for the whole history), `disconnect` |
| `/tips` | `daily` (GET), `post-session` (POST) |
| `/agent` | `chat` (POST), `chat/stream` (POST, SSE), `memory` (GET, the coach's ledger) |

## Single-user by design

Arete assumes one athlete: `user_id = 1` everywhere, no authentication on the API, Strava tokens stored in DuckDB and Garmin session tokens on disk in clear text. Run it on your own machine or behind something that authenticates (VPN, reverse proxy with auth). Do not expose port 8000 to the internet as is.

## Development

```bash
uv run ruff check src tests && uv run ruff format --check src tests
uv run mypy src/arete
uv run pytest                     # ~330 tests, a few seconds
cd frontend && npm run lint && npm run build
```

Tests run against a temporary DuckDB (`tests/conftest.py` sets `ARETE_DB`), and every external call (LLM, Strava, Garmin) is mocked.

`tests/test_agent_evals.py` is the exception: it asks a real model real questions and asserts on which tools it reaches for, since nothing else can tell whether the agent still picks them well. Skipped by default, never in CI, and worth a run before changing a system prompt or a tool description:

```bash
ARETE_EVAL=1 ARETE_EVAL_DB=/path/to/a/copy.duckdb uv run pytest tests/test_agent_evals.py
```

Point it at a copy: the agent writes to the memory ledger beside whichever database it is given.

## License

See [LICENSE](LICENSE).
