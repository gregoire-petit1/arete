# Coaching Agent (side panel)

## Motivation

`/tips` already asks an LLM for a daily and a post-session tip, but it is a one-shot
prompt: no questions back, no access to anything the prompt builder did not already
paste in, and no memory of what was said yesterday. Everything the athlete actually
wants to ask — "why is my TSB negative after an easy week?", "move Thursday's tempo
to Friday" — needs a conversation with tool access.

This adds a coaching agent reachable from every page, grounded in the page the
athlete is looking at, able to write to the planning repository, and keeping notes
between conversations.

## Design

### Graph

`create_agent` (LangChain 1.x) built once per process (`lru_cache`) — single user,
single athlete. One primary tool, four middlewares, a French system prompt, and a
`recursion_limit` of 25 turns.

```
RuntimeContextMiddleware   page the athlete is on → request tail, every turn
ToolEventMiddleware        tool_start / tool_end → custom stream events for the UI
ToolkitMiddleware          progressive tool loading (search_toolkits / load_toolkit)
FilesystemMiddleware       deepagents, scoped to data/agent/memory/
```

Provider comes from the existing `LLM_PROVIDER` / `LLM_MODEL` — no new environment
variables. `ollama` is the generic OpenAI-compatible bucket (Ollama, LM Studio);
`openrouter` defaults to `openrouter/free`, which selects a free model supporting
the request's tools. Model selection lives in OpenRouter; Arete maintains no
fallback list. `LLM_MODEL` can still pin a specific model.

### Page context

The panel is not a chatbot in a vacuum: it knows which route is open. The frontend
stamps `{page, path, param_*}` into `panel_context` on every request; the API layer
is the single writer of that key (mirrors Cortex's `agent-run-context.ts`), and
`RuntimeContextMiddleware` renders it as a `HumanMessage` at the request tail on
every model call.

Over budget (64k chars) or malformed, the injection is **skipped, never truncated**:
half a JSON payload parses as a different page, which is worse than no page at all.

`get_page_context(page)` then returns the same JSON the React page renders, so the
agent reads real numbers instead of guessing them. Read-only, bounded at 32k chars;
over that it returns an error telling the model to ask for a narrower slice.

### Toolkits (progressive loading)

Every bound tool costs schema tokens on every turn and dilutes tool selection. A
planning write-tool needed one turn in ten should not sit on the primary list.

So toolkits are registered on the graph but stay out of the model request until the
agent calls `load_toolkit(toolkit_id)`; `search_toolkits(query)` finds one when only
the capability is known. Loading binds the toolkit's tools with their full schemas
**and** appends its instructions to the system message for the rest of the run —
tools without their usage rules are half a toolkit.

Two wiring traps, both found the hard way and both covered by tests:

- Tools added to `request.tools` in `wrap_model_call` reach the model but **not** the
  `ToolNode` — calling one fails with "not a valid tool". `ToolkitMiddleware`
  therefore executes toolkit tools itself in `wrap_tool_call`.
- The meta-tools and the middleware must close over **one** state object, or
  "loaded" silently diverges from "bound".

The API is stateless, so `before_agent` resets the loaded set in place per request:
every chat call starts from primary tools plus meta-tools, and loading is always an
explicit, visible act.

Today there is one toolkit, `planning` (create / list / update / delete planned
sessions, stamped `source="coach"` so the Planning page can tell them apart).
Registering another is one line in `_TOOLKIT_REGISTRY`.

### Memory ledger

The agent keeps markdown notes under `data/agent/memory/` — inside the existing
`data/` bind mount, so Docker and local runs share one ledger:

- `sessions.md` — one entry per session discussed (facts, feelings, decision taken)
- `notes.md` — durable observations (injuries, preferences, goals)

deepagents' `FilesystemMiddleware` provides the tools; a scoped `FilesystemPermission`
keeps every operation inside the memory root, so the agent can never reach the DuckDB
file, the Garmin tokens or the FIT archive. Paths are resolved relative to the backend
root, so `..` cannot escape.

`glob` and `grep` are deliberately **not** exposed: they ship an `anyOf`-nullable
optional parameter whose JSON schema some OpenRouter free providers reject outright
("more than one JSON reading of the same emitted value"), which kills every request
for *all* tools. Two ledger files do not need search — `ls` plus `read_file` suffice.

Settings → Coach shows both files read-only via `GET /agent/memory`.

### Transport

`POST /agent/chat/stream` returns SSE frames, one JSON object per frame:

| Event | Payload |
| --- | --- |
| `tool_start` / `tool_end` | tool name, and the page argument for `get_page_context` |
| `token` | final-answer delta (model node only) |
| `error` | mid-stream failure |
| `done` | end of run |

Tool *output* is never streamed — the UI has no use for 30kB of analytics JSON, it
only renders a timeline line ("lit les données de la page dashboard"). `POST
/agent/chat` is the non-streaming twin.

History is client state: the panel sends the full conversation each call, bounded at
60 messages of 16k chars (over it, 413 — never silent truncation). The conversation
survives navigation, since the current page travels in `panel_context` on every turn.
A run can be stopped from the panel (`AbortController`); closing the drawer does not
abort, so the answer is there on reopen.

## Not in scope

- **Server-side persistence.** Refreshing the browser loses the conversation. A
  LangGraph checkpointer or an `agent_conversations` table is the next step if the
  ledger turns out not to be enough.
- **Auth.** Same posture as the rest of Arete: single user, no authentication, do not
  expose the port (see "Single-user by design" in the README).
- **Concurrency.** `ToolkitMiddleware` holds its loaded set on the (process-wide)
  middleware instance, so two simultaneous runs would share it. One athlete, one
  panel; if a second surface ever appears, that state moves into the graph state.
- **Merging `/tips` into the agent.** The tips path still uses the raw `openai` SDK
  while the agent uses LangChain. Worth unifying so tips get the ledger as context,
  but it is a separate change.
