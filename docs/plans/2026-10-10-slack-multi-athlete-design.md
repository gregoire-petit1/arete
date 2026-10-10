# Slack for every athlete — design

Status: proposed, 2026-10-10. Builds on PR #23 (Slack DMs, migration 37) and
PR #52 (private athletes, migrations 35–36).

## Decisions

- **One Arete Slack workspace.** Athletes join a workspace Arete operates; the
  app is installed once, with one bot token (`SLACK_TEAM_ID` stays). No public
  distribution, no per-workspace OAuth install, no Slack Marketplace review.
- **v1 ships first for the owner.** PR #23 runs as athlete 1 behind
  `SLACK_USER_ID`. This work replaces that variable without breaking the owner.

## Today (PR #23)

Signed DM → workspace + `SLACK_USER_ID` check → `athlete_scope(1)` → background
task → coach → threaded reply. `app.slack_deliveries` deduplicates events;
`app.slack_execution` is a **single** reservation for the whole instance. The
background task is attached to the ASGI response: a process stopped after the
receipt loses the request.

## Phase A — one linked Slack account per athlete

**Linking.** Réglages → Connexions gains a Slack card next to Garmin:
« Connecter Slack » / « Déconnecter Slack ». The button starts *Sign in with
Slack* (OpenID Connect, scopes `openid profile`) from the Clerk-authenticated
`GET /slack/authorize`, which issues a signed state carrying the athlete
(`services/oauth_state.py`, as Strava does). The public `GET /slack/callback`
verifies the state, exchanges the code, reads `https://slack.com/team_id` and
`https://slack.com/user_id` from the ID token, refuses any team other than
`SLACK_TEAM_ID`, and stores the link. Slack email is never used to match.

**Storage (migration 38).** `app.slack_links(athlete_id PK, team_id, slack_user_id,
linked_at)` with `UNIQUE(team_id, slack_user_id)`. Like `app.users`, it is an
identity mapping read *before* a scope exists, so it is global rather than a
private projection; `services/slack_links.py` is the only reader and every
write is filtered by the current athlete. Linking a Slack user already linked to
another athlete is refused. Account deactivation deletes the link.

**Ingress.** After the signature, team and DM checks, the router resolves
`slack_user_id → athlete_id`. Linked: the job runs in that athlete's
`athlete_scope`. Unlinked: one fixed reply (« Connecte ton compte Slack dans
Réglages → Connexions »), no coach, no history read. `SLACK_USER_ID` is removed;
after deploy the owner links from Réglages once.

**Concurrency (same migration).** `app.slack_runs(athlete_id PK, event_key)`
replaces the singleton: one run per athlete, the busy message is per athlete,
and an ambiguous run blocks only its athlete. `docs/slack.md` recovery becomes
per athlete. `app.slack_execution` stays (append-only migrations) but is unused.

**Ledger bound.** Delete delivered rows older than 7 days (Slack retries within
minutes), so the 100,000-row cap guards abuse, not growth.

**Out of scope.** Calendar tools from Slack (they need a Clerk account id; the
link could carry one later), channel mentions, files, streaming.

## Phase B — durable requests

Ingress: verify → record `queued` in `slack_deliveries` → publish the message to a
Vercel Queue (`idempotencyKey` = event key) → acknowledge. Consumer: take the
athlete's run reservation, then

- `queued` → mark `running`, run the coach, post, mark `done`;
- `running` on redelivery → the previous attempt died mid-run and may have
  written: post the failure message, keep the reservation for review (today's rule);
- `done` → acknowledge only.

So a request is replayed only if the coach never started, which is the safe
subset of "a restart still delivers". Poison messages are acknowledged after a
bounded delivery count.

**To verify before building B:** Queues availability on the Hobby plan, push
triggers for a Python `services` backend in `vercel.json`, the `vercel-queue`
Python SDK, and publish latency inside Slack's three-second receipt. If any
fails, keep today's attached task and document the gap.

## Phase C — streamed answers

Socket Mode is not needed: it only carries *incoming* events over a WebSocket,
needs an always-on process Vercel functions are not, and adds an `xapp-` secret.
Answers already leave through the Web API, which can stream.

**Slack API** (checked 2026-10-10): `chat.startStream` opens a message in the
thread (`chat:write`, already granted; Tier 2, 20+/min), `chat.appendStream`
adds markdown (Tier 4, 100+/min, at most 12,000 characters per call) and
`chat.stopStream` closes it. Channel streams also need `recipient_user_id` and
`recipient_team_id`.

**Flow.** The Slack producer becomes an async iterator over the coach's text,
reusing the runtime streaming the browser's SSE already uses, without importing
the HTTP route. The job starts the stream on the first text, buffers tokens and
appends at most about once per second, then stops it with the final text. The
rate tiers are per app and workspace, so the append interval grows with the
number of concurrent streams. Tool progress can show as short `task_update`
chunks (256 characters), e.g. « Lecture du journal… ». The 39,000-character
reply cap still applies.

**Failure.** If `startStream` fails, fall back to today's single
`chat.postMessage`. The stream's `ts` is stored on the delivery row; a run that
dies mid-stream (Phase B redelivery in `running`) stops that stream and posts the
failure message under it, so no half answer is left looking complete.

**Channels — open decision.** Phase C streams in DMs only. A channel answer
would show one athlete's sessions, health and memory to every member. Before any
channel mention is supported, choose: answer the mention privately in DM with a
short public note, or answer in channel only with non-personal content.

## Tests

- Cross-athlete: athlete B's Slack user never reads or writes athlete A's data;
  the job's scope is the linked athlete, never 1 by default.
- Linking: forged or expired state, foreign team, Slack user already linked
  elsewhere, unlink, deactivated account.
- Unlinked DM: fixed reply, no coach, no history call.
- Per-athlete concurrency: A busy does not block B; A ambiguous blocks only A.
- Phase B: redelivery of `queued`, `running` and `done`; duplicate publish.
- Phase C: append throttling under concurrent streams, `startStream` failure
  falls back to one message, a run dying mid-stream stops it and posts the failure.

## Delivery

Three PRs: A (linking, per-athlete runs, migration 38, Réglages card), B
(queue), then C (streaming). Each with `make check`, the `preview` label on `arete_preview`, then
Deploy production. Slack app changes: add the OIDC redirect URL
`https://arete-arete15.vercel.app/api/slack/callback` and the `openid`,
`profile` user scopes to `slack-manifest.json`.
