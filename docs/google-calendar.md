# Google Calendar

Arete uses Vercel Connect for delegated Google OAuth and calls the Calendar API
from FastAPI. It does not expose an MCP server or require a JavaScript agent.
The Google HTTP contract is separate from the approval service, so provider
credentials never enter model context or browser storage.

## Operator setup

1. Update the Vercel CLI (`npm i -g vercel@latest`), then run `vercel login` from
   this workspace. Link the intended project with `vercel link`.
2. Create a **development-only** Google connector:
   `vercel connect create google --name arete-calendar-dev`.
   Follow the CLI's Google OAuth setup; if a Google Cloud client is requested,
   enable Calendar API, configure the consent audience, and register Connect's
   redirect URI `https://connect.vercel.com/callback` on a **Web application**
   client. Arete's return URL is not Google's OAuth callback. Keep the client
   secret in Connect. The connector has no default scopes: a manual
   `vercel connect token` must pass `--scopes`; Arete sends them on each request.
3. Allow the connector only in the project's Development environment. Request:
   `https://www.googleapis.com/auth/calendar.calendarlist.readonly`,
   `https://www.googleapis.com/auth/calendar.events`, and
   `https://www.googleapis.com/auth/calendar.events.freebusy`.
4. Configure `GOOGLE_CALENDAR_CONNECTOR` with the returned connector UID in `.env`.
   Set `FRONTEND_URL` to the exact browser origin (`http://localhost:5173` for
   `make dev`). Leave the server-owned `GOOGLE_CALENDAR_SUBJECT` stable; it
   identifies the single athlete at Connect, not a browser-provided identity.
5. Run `vercel env pull .env.local`. The backend reads the local OIDC token from
   this ignored file, without importing the other variables into its config.
   Refresh it with the same command if it expires. Vercel injects it at runtime
   on deployed instances. An explicit server-only `VERCEL_CONNECT_ACCESS_TOKEN`
   is supported for externally hosted environments.
6. Verify external authentication covers the frontend, every `/api/*` route,
   backend service URLs, previews, and alternate deployment domains. Only then
   set `GOOGLE_CALENDAR_ACCESS_PROTECTED=true`. This flag is an operator
   acknowledgement, **not** an authentication implementation. A local instance
   must remain bound to loopback. Google OAuth does not authenticate Arete users.
7. Restart the backend (compiled coach profiles are cached). Open **Réglages →
   Connexions → Google Calendar**, complete consent, and select a test calendar.
   Read and write selection starts empty, including after reconnection.

For production, use a **separate connector** linked only to the Production
environment and the production HTTPS `FRONTEND_URL`. Never share Google's
subject grant between development and production connectors. Preview remains
disabled unless explicitly configured with its own test connector. Connection
preferences and actions are namespaced by connector, subject and Vercel environment.

## User behavior

- Select at most 10 readable calendars and explicitly mark writable ones. OAuth
  scopes allow broader access; the Arete service enforces the narrower selection
  on reads, proposal creation, and approval. Google permissions are checked too.
- Availability skips Google's virtual calendars (week numbers, holidays,
  birthdays), which have no free/busy data, and lists them as `skipped`. Any
  other calendar error still fails the whole request rather than guessing.
- Ask the coach to read events or availability, then propose an event. For updates,
  it reads the current event and preserves unchanged fields. Cards show the
  complete before/after snapshot, calendar, timezone, and **Valider / Refuser**.
- Only the browser decision endpoint can execute writes. The agent can never
  approve an action. Clicking a button does not start another model call.
- Proposals expire after 15 minutes. Concurrent decisions claim the durable row
  atomically. Changed permissions invalidate pending cards. Event versions use
  Google's ETags to prevent overwriting changes made since the proposal.
- An uncertain write is never replayed. **Vérifier dans Google** reads the known
  event ID and compares the resulting state. Refresh an executing card if a
  request was lost; after 60 seconds it becomes verifiable. Confirming a matching
  state is not proof of which actor made the change.
- Disconnect disables local access before requesting remote revocation. A failed
  remote revocation is shown explicitly and can be retried. An already-started
  write may finish; disconnect cannot undo it.

Supported: simple events without attendees, all-day events (exclusive end date),
explicit timezone offsets, and individual recurring occurrences. Whole recurring
series, invitations, special event types, moving between calendars, and automatic
synchronization with Arete training sessions are outside this version.

## Limits and data

An operation has a 60-second deadline and each HTTP wait is capped at 15 seconds,
with no retries. Network calls check the remaining operation/run deadline and
bound response size to 1 MB and 1,024 decoded chunks. Sync I/O already in flight
cannot be forcibly cancelled by an agent cancellation. Reads allow at most 31
days, 500 events/intervals and 10 pages; overflow is an error, not partial context.
Tool results use the existing 32,000-character limit and complete-request context
budget. No auxiliary model calls or automatic follow-up generation are added.

Migration 17 adds connection preferences, a hashed expiring consent transaction,
and proposed actions with outcomes. No Google access/refresh token is stored in
DuckDB. Each proposal is bounded to 10,000 characters and at most 100 live pending
proposals exist per connection. Actions older than 30 days are removed when a new
proposal is created. Browser threads persist only action IDs; cards fetch the
server's authoritative snapshot/status after reload. Missing old cards cannot be
approved. Calendar routes bypass the PWA API cache and return `Cache-Control:
no-store`; an offline card cannot approve from a cached server response.
Calendar tool inputs/results may appear in optional LangSmith traces,
under the existing tracing policy.

## Verification

Run `make check`. Normal tests use an isolated DuckDB database and an HTTP mock;
no Google request, live model or athlete database is used.

For the real smoke test, use an isolated test calendar and a database copy:
connect → select → read events/free-busy → propose and refuse → propose and approve
creation → verify in Google → move the event → delete it → disconnect. Check that
nothing is written before each click, and that another selected read-only
calendar cannot be modified. Test consent denial and removing Google permissions.
Never run a script opening the live local database beside a running backend.

Wire references: [Vercel Connect SDK](https://github.com/vercel/vercel-plugin/blob/main/skills/vercel-connect/SKILL.md),
`@vercel/connect` 2.4.1 (`authorization.js` and `token.js`),
[Google scopes](https://developers.google.com/workspace/calendar/api/auth), and
[conditional writes](https://developers.google.com/workspace/calendar/api/guides/version-resources).
