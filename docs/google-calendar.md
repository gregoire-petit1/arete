# Google Calendar

The Calendar integration rides on sign-in: the Google account a user signs in
with through Clerk holds the grant, and Clerk keeps its refresh token. FastAPI
asks Clerk for a fresh access token per operation and calls the Calendar API.
No Google credential enters DuckDB, the model context or browser storage. Each
signed-in account has its own connection, selection and pending actions.

## Operator setup

1. Turn on sign-in (`ARETE_AUTH=clerk`, see the README's "Who can use it").
   Calendar is available exactly when sign-in is: no other variable.
2. In Google Cloud, create a **Web application** OAuth client, enable the Calendar
   API, and add the three scopes below to the consent screen. While the app is in
   testing mode, list each user as a test user (`calendar.events` is a sensitive
   scope: going public needs Google's verification).
3. In the Clerk dashboard (`vercel integration open clerk`), Google social
   connection: switch to custom credentials with that client, and register
   Clerk's redirect URI on it. Leave the sign-in scopes at their defaults: the
   calendar is asked for later, only by users who connect it. Clerk's shared
   development credentials cannot request extra scopes.
4. Scopes requested on **Connecter Google Calendar**:
   `https://www.googleapis.com/auth/calendar.calendarlist.readonly`,
   `https://www.googleapis.com/auth/calendar.events`,
   `https://www.googleapis.com/auth/calendar.events.freebusy`.
5. Open **Réglages → Connexions → Google Calendar**, connect, and select a test
   calendar. Read and write selection starts empty, including after reconnection.

Use one Clerk instance (and Google client) per environment: development and
preview on the development instance, production on its own.

## How connecting works

**Connecter** first asks the server (`POST /google-calendar/connect`), which
checks that the account's Google token carries the scopes. When it does not,
the browser asks Google through Clerk (`reauthorize` with the extra scopes on
the existing Google account, or a new Google account for a user who signed up by
e-mail) and comes back to Settings, which calls `connect` once more without
asking again: a refused consent cannot loop. **Déconnecter** disables access
locally, then revokes the Google grant; the next connection asks Google again.

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
- Disconnect disables local access before revoking the Google grant. A failed
  revocation is shown explicitly and can be retried. An already-started write
  may finish; disconnect cannot undo it. Revoking the grant does not sign the
  user out: sign-in asks Google again for its basic scopes.

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

Migration 17 adds connection preferences and proposed actions with outcomes
(its consent columns are unused since Clerk carries the consent). No Google access/refresh token is stored in
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

Wire references: Clerk's backend `users.get_o_auth_access_token` (Python SDK)
and `ExternalAccount.reauthorize` / `User.createExternalAccount` (`@clerk/react`),
[Google scopes](https://developers.google.com/workspace/calendar/api/auth),
[token revocation](https://developers.google.com/identity/protocols/oauth2/web-server#tokenrevoke), and
[conditional writes](https://developers.google.com/workspace/calendar/api/guides/version-resources).
