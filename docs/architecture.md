# Coaching stack: responsibilities and dependencies

Arete uses the Cortex ownership pattern with one coaching runtime and three
server-selected profiles. Browser-owned conversations, HTTP endpoints, tool names,
DuckDB tables and ledger paths remain compatible. There are no placeholder layers
for delegation, MCP, authentication or providers Arete does not use.

```text
arete/
├── coaching.py              Application composition for HTTP and scheduled work
├── agent/
│   ├── factory.py           Compile explicit dependencies into one graph
│   ├── runtime/             Invocation context, conversation state, policy, limits, events
│   ├── context/             Ordered sections, open-page data and request accounting
│   ├── models/              Deployment envelope, route selection, provider adapter
│   ├── capabilities/        One catalog, discovery and execution resolution
│   ├── tools/               Model schemas and domain-service adapters
│   ├── middlewares/         Framework interception/completion hooks
│   ├── backends/            Deep Agents memory filesystem adapter and permissions
│   ├── profiles/            Declarative chat, briefing and feedback configurations
│   └── prompts/             Versioned general/mission instructions
├── services/                Metrics, analytics, planning, settings, pages, coaching, memory
├── observability/           Provider usage and model-boundary timing
└── api/                     HTTP contracts and SSE projection
```

Existing `garmin/`, `strava/`, `strength/`, `features/` and `dataio/` remain domain
modules: moving them would not improve a dependency boundary. The services layer
reuses them. Business code imports neither the HTTP routes nor agent frameworks.

## Composition and execution

`coaching.py` resolves configuration and supplies the concrete model and memory
adapter to the factory. Graph creation is serialized
on first access and cached once per profile. Only this composition root may
import the factory. The runtime receives an already-compiled graph; it never
compiles another agent. Briefing and feedback services receive typed callbacks
rather than reaching back into the factory.

The browser sends human/assistant history. `runtime/state.py` owns invocation
messages and loaded capabilities. `runtime/context.py` owns
server-selected profile, request metadata, deadline and concurrency gate. Clients,
semaphores and credentials do not enter conversation state.

Production sync entrypoints run in AnyIO workers and bridge model execution onto
the server event loop. This avoids sharing the SDK's cached async HTTP connections
across short-lived event loops. Async callers use `invoke_agent` directly.

The execution envelope is five minutes, 8 main graph model calls, 32 tool calls,
and four simultaneous tool executions per invocation. Framework recursion is a
separate 100-step backstop. A model call gives up after 60 s, or 30 s without a
streamed chunk, with two SDK retries; on OpenRouter the request carries a
fallback list of at most three models. Tools and failed runs are never
automatically replayed. Already-started
synchronous operations cannot be forcibly cancelled or rolled back.

## Capability and context ownership

The capability catalog owns tools, instructions and read-only classifications.
Discovery, binding, policy checks and structural tests consume the same catalog.
Tools call services; they do not import HTTP handlers. New tools are unavailable
to background missions until explicitly classified as read-only.

Chat preloads analytics, planning, strength and Garmin capabilities: loading one cost a
model request per turn, and requests are the free tier's budget. The on-demand
loading machinery (catalog, `load_toolkit`, load-before-execute) stays for
profiles that do not preload. The briefing and the session feedback bind no tool:
`services/briefing.py` and `services/session_feedback.py` compute their facts
(load, form, recovery, today's plan, recent sessions, yesterday's briefing; or the
session's numbers, RPE and notes) and the model answers in one request. The
server files the feedback's ledger entry itself (`services/memory.append_entry`,
dated heading, never twice), so neither mission can mutate training data or
forget to write. Every profile receives the current date. Chat writes the
journal through one tool, `append_journal` (server-dated heading, deduplicated,
bounded); its filesystem middleware only reads (`read_file`).
Model-generated loaded state and client page metadata cannot change these policies.

The context builder combines the harness/filesystem contribution, mission
instructions, the current date for chat, the catalog of toolkits still loadable,
loaded instructions, a bounded journal excerpt and, for chat, the open page: its
data read by the server once per run (`context/sections.py`, through
`services/pages.py`) and its URL parameters labelled as untrusted client data. A
question about the screen therefore needs no tool call. The journal is read again
for each model call, so writes within a turn are visible on the next call; older
entries remain accessible through filesystem tools. Contributions do not mutate
stored messages. A final guard counts messages, system text and tool schemas,
reserves 4,096 output tokens and a safety margin, and rejects requests that still
exceed the envelope.

`LLM_CONTEXT_TOKENS` declares the deployment window (default 65,536, minimum 8,192).
Set it to the actual server/model limit. It is a configured constraint, not a claim
about a dynamically routed provider. Counting is approximate. There is no
server-side compaction: the browser sends the last 30 messages of a thread (it
keeps the whole thread locally) and the journal in `data/agent/memory` is the
long-term memory. Summarizing per request cost a model request on every turn of a
long thread, since nothing persists the summary between requests.

## Completion, transport and observability

Follow-up suggestions are the browser's: fixed, page-aware lists
(`frontend/src/lib/coachPrompts.ts`), so `done` follows the last token and no
auxiliary model request runs after an answer. Generating them cost one request
per turn and held `done` for up to eight seconds.

Runtime tool events are projected into the existing SSE protocol by
`api/agent_streaming.py`. Workout events carry session ID/revision, tool call,
thread and durable operation state. The domain service publishes through an injected
callback; the runtime supplies correlation and the API projects `workout_update`.
Cards consume these events before `done`, independently of truncated tool previews.
Optional LangSmith tracing remains invocation-scoped, including stream
cancellation cleanup, dynamic tool spans and browser thread IDs. Provider usage logs
retain reported cache/input/output details and model timing without logging the
athlete's prompts. Opt-in LangSmith traces include full inputs, outputs and tool
results, as described in the README. Missing usage remains unknown, not zero.
Each invocation also logs one `Agent run:` line (`RunStats` on the run context):
model calls, tool calls, model time, time to first token and served models.

These bounds are not a cumulative token/spend quota: SDK retries have their own
limit and share the run deadline. Arete has no delegated
children to budget; a provider-side fallback stays within one model call. No database or browser-store migration is
required.

## Enforcement

`tests/test_architecture.py` checks dependency direction, including function-local
imports, and validates profile/capability consistency. Graph tests cover policy
checks, load-before-execute, concurrent invocation isolation, call/deadline limits,
context schema accounting and completion events. Service/API tests cover domain
behavior and wire compatibility. Trace regression tests cover cancellation, parent spans, metadata and export
failures. Live model evaluations remain opt-in.

## Document imports and outbound workouts

Conversation messages remain browser-owned. Document originals, extracted blocks,
import drafts and outbound Garmin operation records are deliberately durable in
DuckDB/MotherDuck (migration 13). `services/documents.py` and `services/imports.py`
own these lifecycles. API chat hydration builds an invocation-local StateBackend
view at `/attachments/`; the context builder receives only a bounded manifest.
The readonly filesystem composes that view with the existing ledger backend.
The model can propose a draft but has no confirmation tool; pending imports block
ordinary coach planning writes. Human confirmation commits selected sessions once.

`services/prescriptions.py` owns versioned steps and provenance. Garmin conversion
lives in `garmin/workouts.py`; `services/garmin_export.py` owns both interactive
and daily export, reconciliation and removal with durable reservations and no
ambiguous write replay. Chat can create coach prescriptions without a document;
explicit prescriptions remain excluded from automatic daily adaptation/export.
Legacy sessions use deterministic conversion, and existing Garmin identifiers must
be verified before adoption. Updates require the current revision and mark the
export dirty without transmitting it. See [conversational workouts](conversational-workouts.md)
for UI, limits and verification.
Only `GarminClient` touches the remote service. See [document imports](document-imports.md)
for resource bounds, frontend worker assets, unsupported conversions and acceptance.

## Identity

`api/auth.py` owns who is calling: a pure ASGI middleware (like the mirror's,
so the coach's stream is not buffered) and the `/auth/config` and `/auth/me`
routes. Off by default; with `ARETE_AUTH=clerk` every non-public request
carries a Clerk session token or the instance's API key, verified in a worker
thread. `services/users.py` owns the accounts table and the one rule that
attaches an account to the athlete: its e-mail is one of the owner's. Services never import
`arete.api.auth`; the athlete's data stays `user_id = 1`, so nothing below the
boundary changed. `services/google_tokens.py` reads the signed-in user's Google
token from Clerk for integrations that need it (Calendar), and
`services/oauth_state.py` signs the Strava OAuth state the callback demands.
