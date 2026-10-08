# Arete — coding-session instructions

Arete is a self-hosted, single-athlete training assistant: FastAPI + DuckDB,
React + Vite, Garmin/Strava sync, planning, strength logging and coaching.
Read [docs/architecture.md](docs/architecture.md) before changing the coaching stack.

## Architecture: give every behavior one owner

- `src/arete/coaching.py` is the application composition root. It resolves profiles
  and model configuration, supplies concrete dependencies to the factory, and
  connects API/scheduled work to domain services through callbacks.
- `agent/factory.py` only assembles and compiles. Lower layers must never import it
  or the composition root. Do not create agents inside tools, services or middleware.
- `agent/runtime/` owns invocation context, conversation state, policy, budgets and
  events. Keep clients, credentials, deadlines and concurrency primitives out of
  conversation state. Browser threads remain authoritative; do not introduce server
  persistence implicitly.
- `agent/context/` owns final request ordering, typed contributions, compaction and
  complete-request token accounting. Contribute context here instead of appending
  prompts independently in another middleware. Preserve the current objective and
  raw history; never silently truncate a request to fit.
- `agent/models/` owns model routes, configured limits and provider clients. Construct
  clients through the composition root; no network discovery at import time. Name
  model/output/temperature/timeout/retry settings explicitly.
- `agent/capabilities/` declares tools, instructions and execution metadata once.
  Discovery, model binding, authorization and structural tests use this catalog.
  Capability instructions stay beside their declaration. Loading is not authorization.
- `agent/tools/` validates/adapts model arguments and calls domain services. It must
  not import HTTP handlers, select models or implement domain workflows.
- `agent/nodes/` contains program-imposed steps, including follow-up generation.
  `agent/middlewares/` only adapts framework interception/completion hooks to the
  actual policy or operation. Do not hide a second runtime in middleware.
- `agent/backends/` adapts Deep Agents filesystem permissions and operations.
  Reusable ledger I/O belongs in `services/memory.py`.
- `agent/profiles/` is declarative server configuration; `agent/prompts/` contains
  versioned general/mission instructions. A client-supplied profile or page payload
  cannot grant permissions.
- `services/` owns shared domain operations and their contracts. It may use the
  existing `features/`, `dataio/`, `garmin/`, `strava/` and `strength/` modules. It
  must not import FastAPI, LangChain, LangGraph, Deep Agents or agent composition.
- `api/` owns HTTP schemas and SSE projection; `observability/` owns measurements.
  Put schemas beside their owner. Avoid global `schemas/` or catch-all `shared/`.

Add a directory only when it removes an ambiguous dependency or gives an existing
responsibility a testable owner. Do not create empty architectural scaffolding.
`tests/test_architecture.py` enforces the dependency direction, including local imports.

## Runtime contracts to preserve

- Chat may write training data after loading the appropriate toolkit. Briefings
  preload read-only analytics; feedback uses supplied facts and memory. Background
  jobs can maintain the ledger but cannot alter training plans or log workouts.
- Each invocation has named call, concurrency and time limits. SDK retries and
  auxiliary calls must remain bounded. Never automatically replay a failed write
  or an entire run with an ambiguous outcome.
- `LLM_CONTEXT_TOKENS` is the deployment's configured window, not a guarantee from
  a provider router. Budget system text, schemas, history, page data and output.
- Async model clients belong to the server event loop. Sync API/scheduler work uses
  AnyIO workers and `invoke_agent_sync`; never add a fresh `asyncio.run()` per job.
- `AutoSuggestionMiddleware` delegates optional completion work to its injected
  generator. Failure must preserve the answer. Suggestions are metadata, not user
  intent, until clicked. Keep the HTTP, SSE, parser and browser-storage contracts
  aligned when adding event fields.
- Preserve optional LangSmith tracing across async invocation and stream closure.
  Forward callbacks to dynamically executed tools and retain thread metadata. The
  context builder owns bounded journal injection and the current chat date.
- Keep state local to the invocation. Compiled graphs are cached and multiple tabs
  or scheduled jobs may overlap. Cancellation cannot undo a committed write or
  forcibly stop a synchronous tool already running in a thread.

## Commands and verification

| Need | Command |
|---|---|
| Complete CI-equivalent checks | `make check` |
| Backend tests | `make test` |
| Local API + frontend | `make dev` |
| Docker stack | `make docker` |
| Dependencies and git hooks | `make install` |

Run `make check` before declaring implementation complete. It runs lint, formatting
checks, mypy, backend/frontend tests and the frontend build. Mock external I/O in
normal tests. Add behavior tests for changed boundaries, failures and concurrency;
do not add tests that merely repeat an implementation. Live model evaluations in
`tests/test_agent_evals.py` are opt-in and must use a database copy.

## Data, workflow and conventions

- **Never `git add -A` or `git add .`.** Stage named paths; embedded workspaces and
  personal data must not be swept into a commit.
- Do not commit or push until the user has tested locally and explicitly authorized
  shipping. Each push needs its own authorization. Never rename the current branch
  unless requested. PRs target `main`; no automatic merge.
- Use Conventional Commits with an English subject and a body explaining why.
- DuckDB allows one writer. Do not open the real database from a local script while
  the Docker backend is running; use its HTTP API instead.
- `data/`, Garmin tokens, FIT files, `PROG_*.md` and `.context/` stay untracked.
  Secrets live in `.env`; use `.env.example` to discover configuration names.
- UI text is French. Code, comments and commit messages are English.
- Workout parsing uses the Lark grammars, not an LLM. A new spoken phrase needs a
  grammar change and an example in `tests/data/dictations.jsonl`.
- Heart-rate zones come from the athlete's threshold refreshed by Garmin sync.
  Reuse `features/hr_zones.py` and `garmin/threshold.py`.
- Be critical and concise. Verify claims against code or runs, reuse existing domain
  logic, and explain trade-offs. Bound new loops/retries/fan-out; assert programmer
  invariants and report operating errors explicitly.
