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

Docker and Vercel share one MotherDuck database (`ARETE_DB=md:arete`, token `MOTHERDUCK_TOKEN` from `vercel env pull`); files that are not the database (Garmin tokens, coach memory) stay in the repo's `./data`, bind-mounted at `/app/data`, and are mirrored into it (`dataio/mirror.py`). `make dev` keeps the local `data/arete.duckdb` file unless `ARETE_DB` says otherwise. The daily sync runs on Vercel Cron at 08:00 UTC (`GET /api/cron/daily-sync`, `CRON_SECRET`), after wake-up: Garmin only publishes the night's HRV and sleep score once the athlete is up. `ARETE_AUTO_SYNC_HOUR` still arms the in-process scheduler for a backend that stays up without Vercel. The compose file sets `FRONTEND_URL` for the 3080 frontend; with `restart: unless-stopped` the stack comes back whenever Docker starts. Ollama is expected on the Docker host (`host.docker.internal:11434`); uncomment the `ollama` service in `docker-compose.yml` to run it in Docker instead.

## Configuration

All settings come from environment variables (see `.env.example`):

| Variable | Purpose |
| --- | --- |
| `ARETE_DB` | DuckDB file path (default `data/arete.duckdb`), or `md:<database>` for MotherDuck |
| `ARETE_DATA_DIR` | Files beside the database (default: its directory, `/tmp/arete-data` on MotherDuck) |
| `CRON_SECRET` | Bearer token of `GET /cron/daily-sync`; unset = endpoint closed |
| `ARETE_LOG_LEVEL` | Backend log level (default `INFO`) |
| `ARETE_AUTO_SYNC_HOUR` | Local hour of the daily Garmin activities + health and Strava sync, best set after wake-up; unset = manual only |
| `LLM_CONTEXT_TOKENS` | Coaching deployment context window (default 65,536); set to your actual model/server limit |
| `LLM_PROVIDER`, `LLM_MODEL` | `ollama` \| `openrouter` \| `github`, and the model name |
| `OLLAMA_BASE_URL` / `OPENROUTER_API_KEY` / `GITHUB_TOKEN` | Credentials for the chosen provider |
| `STRAVA_CLIENT_ID`, `STRAVA_CLIENT_SECRET`, `STRAVA_REDIRECT_URI` | Strava OAuth app |
| `FRONTEND_URL` | Where the Strava callback redirects (default `http://localhost:3080`) |
| `GARMIN_EMAIL`, `GARMIN_PASSWORD` | Garmin Connect login (or log in from the Settings page) |
| `ARETE_GARMIN_TOKENS_DIR` | Where the Garmin session tokens are stored (default `data/garmin_tokens`) |

The agent reuses `LLM_PROVIDER` / `LLM_MODEL` and needs a tool-calling model; its memory ledger sits next to the database, in `data/agent/memory/`.

Open or hide the coach from the navigation bar. The **+** button starts a new
conversation; **History** restores earlier threads, with separate messages and
drafts. Threads are saved in this browser (up to 30), while the coach’s memory
ledger remains shared across conversations. Hiding the panel or switching threads
keeps the current response running in its original thread; one response runs at a time.

Completed answers can show up to three French follow-up suggestions. Clicking one
sends it as the next message; suggestions are stored with the browser thread and
are never sent as conversation history unless selected. `AutoSuggestionMiddleware`
uses one tool-free completion (512 output tokens, eight-second timeout, no retry).
If generation fails, the exchange is too large, or the run has insufficient time
remaining, the answer is kept without suggestions.

Chat, daily briefings and session feedback share a five-minute execution deadline,
16 main model calls and 32 tool calls per run, with at most four concurrent tools.
SDK retries remain separately bounded; summarization and suggestions are auxiliary
calls within the deadline, not part of the main-call count. These are execution
limits, not a cumulative token or spend cap. Cancellation cannot undo a committed
write or stop a synchronous tool already running in a worker thread; failed runs
are never automatically replayed.

Background briefings receive read-only analytics already loaded. Session feedback
uses supplied facts and the memory ledger only. Both can maintain coaching memory,
but neither can change the training plan or log workouts. The server checks these
permissions at execution as well as filtering tool schemas. Chat retains direct
training writes after the corresponding toolkit has been loaded.

To trace the coach, set `LANGSMITH_TRACING=true` and `LANGSMITH_API_KEY` in the
backend `.env`, then restart. This key is separate from inference credentials.
`LANGSMITH_PROJECT` defaults to `Arete` and must be the exact project name.
Before the first live run, verify that name against
[the intended project](https://smith.langchain.com/o/22f0221c-5eef-4f4d-8b2e-f0313a7017fc/projects/p/3aef9b7c-d687-4a57-9ac7-d36dd2c905ae).
`LANGSMITH_ENDPOINT` defaults to `https://api.smith.langchain.com`; use your
region's endpoint when different. Set `LANGSMITH_WORKSPACE_ID` only when required
by the key; the organization ID in the URL is not a workspace ID.

Tracing exports complete agent inputs/outputs and tool results, including training
data and memory reads. Each invocation has one `arete_coach` root with `task`,
`provider`, and `model` metadata and nested model/tool/middleware spans; model
usage is recorded when supplied by the provider. Tracing defaults off, uses a
background exporter, and adds no inference calls. Export failures are logged
without replacing the coach's answer. Shutdown waits at most five seconds for
queued traces; an interrupted process or export failure can leave incomplete traces.

Chat requests include the persisted conversation UUID as `thread_id`. Each turn
still creates its own trace, with that ID propagated to all spans so LangSmith
groups turns into one thread. API clients may omit it for standalone requests.
The coach receives the backend's current date on each chat invocation, and the
UI refreshes session data after successful coach writes.

For free hosted inference, set `LLM_PROVIDER=openrouter` and `OPENROUTER_API_KEY`,
and leave `LLM_MODEL` unset (or set it to `openrouter/free`). The
[Free Models Router](https://openrouter.ai/openrouter/free) selects an available
free model supporting the request's tools. Rate limits, latency and model quality
can vary. Set `LLM_MODEL` to pin a specific model; Arete sends no fallback list.

## Project layout

```
src/arete/
├── config.py   All environment variables in one place; scheduler.py: optional daily sync
├── coaching.py Application composition for chat and background coaching
├── agent/      Runtime, context builder, model routes, capability catalog, tools, profiles, prompts and hooks
├── services/   Domain operations shared by HTTP routes, tools and scheduled work
├── observability/ Model usage and timing
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

The coaching dependency boundaries and execution envelope are documented in
[Architecture](docs/architecture.md) and enforced by structural tests.

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

Start coding sessions with [AGENTS.md](AGENTS.md) (shared instructions) or
[CLAUDE.md](CLAUDE.md) (Claude entrypoint). The [architecture guide](docs/architecture.md)
explains ownership, allowed dependencies, profiles and runtime limits. Changes to
these boundaries must update the guide and the dependency tests together.

```bash
uv run ruff check src tests && uv run ruff format --check src tests
uv run mypy src/arete
uv run pytest                     # ~330 tests, a few seconds
cd frontend && npm run lint && npm test && npm run build
```

Tests run against a temporary DuckDB (`tests/conftest.py` sets `ARETE_DB`), and every external call (LLM, Strava, Garmin) is mocked.

`tests/test_agent_evals.py` is the exception: it asks a real model real questions and asserts on which tools it reaches for, since nothing else can tell whether the agent still picks them well. Skipped by default, never in CI, and worth a run before changing a system prompt or a tool description:

```bash
ARETE_EVAL=1 ARETE_EVAL_DB=/path/to/a/copy.duckdb uv run pytest tests/test_agent_evals.py
```

Point it at a copy: the agent writes to the memory ledger beside whichever database it is given.

## License

See [LICENSE](LICENSE).
