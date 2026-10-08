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
│   ├── context/             Ordered sections, request accounting and compaction policy
│   ├── models/              Deployment envelope, route selection, provider adapter
│   ├── capabilities/        One catalog, discovery and execution resolution
│   ├── tools/               Model schemas and domain-service adapters
│   ├── nodes/               Optional follow-up generation after an answer
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

`coaching.py` resolves configuration and supplies concrete models, memory adapter,
compactor and suggestion generator to the factory. Graph creation is serialized
on first access and cached once per profile. Only this composition root may
import the factory. The runtime receives an already-compiled graph; it never
compiles another agent. Briefing and feedback services receive typed callbacks
rather than reaching back into the factory.

The browser sends human/assistant history. `runtime/state.py` owns invocation
messages, loaded capabilities and suggestion results. `runtime/context.py` owns
server-selected profile, request metadata, deadline and concurrency gate. Clients,
semaphores and credentials do not enter conversation state.

Production sync entrypoints run in AnyIO workers and bridge model execution onto
the server event loop. This avoids sharing the SDK's cached async HTTP connections
across short-lived event loops. Async callers use `invoke_agent` directly.

The execution envelope is five minutes, 16 main graph model calls, 32 tool calls,
and four simultaneous tool executions per invocation. Framework recursion is a
separate 100-step backstop. SDK retries remain capped at four retries per model
call; tools and failed runs are never automatically replayed. Already-started
synchronous operations cannot be forcibly cancelled or rolled back.

## Capability and context ownership

The capability catalog owns tools, instructions and read-only classifications.
Discovery, binding, policy checks and structural tests consume the same catalog.
Tools call services; they do not import HTTP handlers. New tools are unavailable
to background missions until explicitly classified as read-only.

Chat can load analytics, planning and strength capabilities. Briefings preload
read-only analytics. Feedback receives session evidence and memory only. Both
background profiles can maintain the ledger but cannot mutate training data.
Model-generated loaded state and client page metadata cannot change these policies.

The context builder combines the harness/filesystem contribution, mission
instructions, the current date for chat, capability catalog, loaded instructions,
a bounded journal excerpt, history and untrusted page data. The journal is read
again for each model call, so writes within a turn are visible on the next call;
older entries remain accessible through filesystem tools. Contributions do not mutate stored messages. Compaction follows assembly;
a final guard counts messages, system text and tool schemas, reserves 4,096 output
tokens and a safety margin, and rejects requests that still exceed the envelope.

`LLM_CONTEXT_TOKENS` declares the deployment window (default 65,536, minimum 8,192).
Set it to the actual server/model limit. It is a configured constraint, not a claim
about a dynamically routed provider. Counting is approximate. The compaction
trigger is at most 40,000 tokens and shrinks with the configured window. Raw evicted
history remains in `data/agent/transcripts`; coaching memory stays in
`data/agent/memory`.

## Completion, transport and observability

`AutoSuggestionMiddleware` is a completion-hook adapter. Its injected generator
runs once after a successful chat answer, without tools: at most three French
questions, 120 characters each, 512 output tokens, eight seconds, zero retries.
It skips oversized exchanges and insufficient remaining time; errors are logged
without replacing the answer. Suggestions are optional, stored with the browser
message, and only become user intent when clicked.

Runtime tool/suggestion events are projected into the existing SSE protocol by
`api/agent_streaming.py`. The non-streaming endpoint adds an optional `suggestions`
list. Auxiliary generation cannot overwrite the main answer. Optional LangSmith tracing remains invocation-scoped, including stream
cancellation cleanup, dynamic tool spans and browser thread IDs. Provider usage logs
retain reported cache/input/output details and model timing without logging the
athlete's prompts. Opt-in LangSmith traces include full inputs, outputs and tool
results, as described in the README. Missing usage remains unknown, not zero.

These bounds are not a cumulative token/spend quota: SDK retries, compaction and
suggestions have their own limits and share the run deadline. Arete has no delegated
children or fallback chain to budget. No database or browser-store migration is
required.

## Enforcement

`tests/test_architecture.py` checks dependency direction, including function-local
imports, and validates profile/capability consistency. Graph tests cover policy
checks, load-before-execute, concurrent invocation isolation, call/deadline limits,
context schema accounting and completion events. Service/API tests cover domain
behavior and wire compatibility. Trace regression tests cover cancellation, parent spans, metadata and export
failures. Live model evaluations remain opt-in.
