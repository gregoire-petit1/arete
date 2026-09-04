# Arete

[![CI](https://github.com/gregoire-petit1/arete/actions/workflows/ci.yml/badge.svg)](https://github.com/gregoire-petit1/arete/actions/workflows/ci.yml)

> **Arete (ἀρετή)** — an ancient Greek concept meaning _excellence_ or _virtue_,
> achieved when one fulfills their highest potential through discipline, balance, and mastery.

Self-hosted, single-user training assistant:

- **Garmin Connect & Strava sync** of activities (FIT parsing, HR zones, best efforts) and daily health metrics (HRV, sleep, body battery, readiness score).
- **Analytics**: volume, CTL/ATL/TSB (Banister model with personalized coefficients), pace trends, HR drift / aerobic decoupling, cardiac efficiency.
- **Strength log** with a free-text workout parser (regex first, LLM fallback), muscle-volume heatmap and Garmin activity linking.
- **Planning**: planned sessions matched against actual activities, adherence dashboard.
- **LLM coaching tips** (daily + post-session) through any OpenAI-compatible provider: Ollama, OpenRouter or GitHub Models.

## Stack

- **Backend**: Python 3.11, FastAPI + Pydantic v2, DuckDB, `garth` (Garmin), `fitparse`, `openai` SDK (provider-agnostic).
- **Frontend**: React 19 + Vite, Tailwind 4, TanStack Query, recharts, PWA (see `frontend/README.md`).
- **Tooling**: uv, ruff, mypy, pytest; Docker Compose (backend + nginx-served frontend).

## Quickstart (local)

```bash
git clone https://github.com/gregoire-petit1/arete.git && cd arete
cp .env.example .env            # edit as needed
uv sync --extra dev
uv run python -c "from arete.dataio.init_duckdb import main; main()"
uv run uvicorn arete.api.main:app --reload --app-dir src   # http://localhost:8000/docs

cd frontend && npm ci && npm run dev                        # http://localhost:5173
```

The Vite dev server proxies `/api/*` to the backend on port 8000. The schema is (re)initialized on every backend start, so the init command is only needed for scripts that run without the API.

## Docker

```bash
cp .env.example .env    # required: docker-compose reads env_file .env
docker compose up --build
# frontend: http://localhost:3080   backend: http://localhost:8000
```

Data (DuckDB file, Garmin tokens, FIT files) lives in the `arete-data` volume mounted at `/app/data`. Ollama is expected on the Docker host (`host.docker.internal:11434`); uncomment the `ollama` service in `docker-compose.yml` to run it in Docker instead.

## Configuration

All settings come from environment variables (see `.env.example`):

| Variable | Purpose |
| --- | --- |
| `ARETE_DB` | DuckDB file path (default `data/arete.duckdb`) |
| `LLM_PROVIDER`, `LLM_MODEL` | `ollama` \| `openrouter` \| `github`, and the model name |
| `OLLAMA_BASE_URL` / `OPENROUTER_API_KEY` / `GITHUB_TOKEN` | Credentials for the chosen provider |
| `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_REDIRECT_URI` | Strava OAuth app |
| `FRONTEND_URL` | Where the Strava callback redirects (default `http://localhost:3080`) |
| `GARMIN_EMAIL`, `GARMIN_PASSWORD` | Garmin Connect login (or log in from the Settings page) |
| `ARETE_GARMIN_TOKENS_DIR` | Where garth stores Garmin OAuth tokens |
| `RUNALYZE_TOKEN` | Optional Runalyze backup |

## Project layout

```
src/arete/
├── api/        FastAPI routers: analytics, garmin, garmin_health, strength, strava, ai_tips, metrics, settings; main.py wires them
├── dataio/     DuckDB connection (db.py), schema + migrations (init_duckdb.py), user settings repository
├── features/   Training science: workload (ACWR), cardio (TRIMP, zones), fitness (CTL/ATL/TSB), strength (1RM, INOL), banister fit, recommendations
├── garmin/     FIT parser, time-series metrics, planned/actual matching, Garmin Connect sync, health sync + readiness, LLM analyzer, Runalyze backup
├── strength/   Strength models + repository (exercises, sessions, sets, PRs)
├── strava/     Strava API client and activity mapping
├── llm/        Provider abstraction, workout text parser, token budget manager
└── data/       Exercise catalog
frontend/       React app (pages: Dashboard, Planning, Analytics, Log, Settings)
scripts/        fit_banister.py (fit personal CTL/ATL coefficients), garmin_login.py (one-time token bootstrap), import_strava_history.py (full history backfill)
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
| `/garmin` | `planned` CRUD, `upload-fit`, `actual`, manual match/unmatch, `summary`, `unmatched`, `actual/{id}/analyze` (LLM), `sync/{status,login,logout,activities,user}`, `backup/runalyze` |
| `/garmin/health` | `sync` (POST), `daily`, `range`, `status` |
| `/strength` | `exercises` CRUD + `/{id}/prs`, `sessions` CRUD, `sessions/parse` (free-text → structured, optional save), Garmin linking, `stats/volume-by-muscle` |
| `/strava` | `authorize`, `callback`, `status`, `sync` (POST), `disconnect` |
| `/tips` | `daily` (GET), `post-session` (POST) |

## Development

```bash
uv run ruff check src tests && uv run ruff format --check src tests
uv run mypy src/arete
uv run pytest                     # ~330 tests, a few seconds
cd frontend && npm run lint && npm run build
```

Tests run against a temporary DuckDB (`tests/conftest.py` sets `ARETE_DB`), and every external call (LLM, Strava, Garmin) is mocked.

## License

See [LICENSE](LICENSE).
