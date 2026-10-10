# Slack for every athlete — design

Status: Phase A implemented; B and C proposed. 2026-10-10. Builds on PR #23 (Slack DMs, migration 37) and
PR #52 (private athletes, migrations 35–36).

## Decisions

- **One Arete Slack workspace.** Athletes join a workspace Arete operates; the
  app is installed once, with one bot token (`SLACK_TEAM_ID` stays). No public
  distribution, no per-workspace OAuth install, no Slack Marketplace review.
- **v1 shipped first for the owner** (PR #23, athlete 1 behind `SLACK_USER_ID`),
  live since 2026-10-10. Phase A replaces that variable.
- **Identity by Slack profile email**, matched to a verified Arete login, and a
  dedicated channel whose public answers need each athlete's consent.

## Today (PR #23)

Signed DM → workspace + `SLACK_USER_ID` check → `athlete_scope(1)` → background
task → coach → threaded reply. `app.slack_deliveries` deduplicates events;
`app.slack_execution` is a **single** reservation for the whole instance. The
background task is attached to the ASGI response: a process stopped after the
receipt loses the request.

## Phase A — every athlete, by email (implemented)

Chosen on 2026-10-10 over Sign in with Slack linking: simpler, no OAuth screen.

- **Identity.** `users.info` gives the author's profile; guests, bots, external
  or unconfirmed accounts are refused. The address must match a verified Arete
  login (or `ARETE_OWNER_EMAIL`) behind exactly one active athlete; otherwise a
  fixed « aucun compte » reply, no coach. `SLACK_USER_ID` is removed.
- **Scope per message.** Each message runs in its author's athlete scope, so a
  member replying in someone else's thread is answered with their own data.
- **Dedicated channel** (`SLACK_CHANNEL_ID`). Arete answers a mention, or a reply
  in one of its threads. Other members' messages are labelled in the history and
  the coach is told not to attribute or memorise them.
- **Consent.** « Autoriser Arete à me répondre en public dans le canal Slack »
  (Réglages → Connexions), off by default; without it the answer goes to the
  athlete's DM with a short note in the thread. The context builder's `surface`
  section tells the coach who reads the answer.
- **Concurrency.** Migration 40 adds `app.slack_athletes` (consent and run
  reservation per athlete), replacing the instance-wide singleton. Reservation
  conflicts on MotherDuck are answered busy; the idempotent release is retried.

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

**Channels.** Decided in Phase A: a channel answer is public only with the
athlete's consent, otherwise it goes to their DM. Streams follow the same rule.

## Tests

- Cross-athlete: the job's scope is the author's resolved athlete, never 1 by
  default; consent is per athlete.
- Identity: unverified, ambiguous, unknown or deleted accounts; guests, bots,
  other teams and unconfirmed Slack addresses.
- Unknown author: fixed reply, no coach. Channel chatter outside Arete's threads
  is ignored.
- Per-athlete concurrency: A busy does not block B; A ambiguous blocks only A.
- Phase B: redelivery of `queued`, `running` and `done`; duplicate publish.
- Phase C: append throttling under concurrent streams, `startStream` failure
  falls back to one message, a run dying mid-stream stops it and posts the failure.

## Delivery

Three PRs: A (email identity, dedicated channel, consent, per-athlete runs,
migration 40), B (queue), then C (streaming). Each with `make check`, the
`preview` label on `arete_preview`, then Deploy production. Phase A's Slack app
changes are in `slack-manifest.json`: new bot scopes and the channel events.
