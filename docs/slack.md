# Arete in Slack

Every athlete can talk to the coach in Slack: in **direct messages**, and in one
**dedicated channel** when it is mentioned. It answers in a thread; replying in
that thread continues the conversation, and a new message starts a new one. It
uses the existing chat coach, including its training-write capabilities and
journal. Files, edits and shared channels are ignored. Slack and browser
conversations stay separate.

## Who is answered

The author of each message is identified from their Slack profile: a full member
of the workspace (no guest, bot or external account) with a confirmed address.
That address must belong to a **verified** Arete login (`app.users`) or to
`ARETE_OWNER_EMAIL`, and resolve to exactly one active athlete; otherwise Arete
replies that no account is linked and never invokes the coach. Each message runs
in its own author's athlete scope, so when another member replies in a channel
thread, the answer reads and writes **their** data. Other members' messages in
the thread are labelled `[Autre participant <@U…>]`, and the coach is told never
to attribute them to the athlete or store them in its memory.

In the channel, Arete answers a message that mentions it or that replies in one
of its threads. An answer is **public only if the athlete enabled** « Autoriser
Arete à me répondre en public dans le canal Slack » (Réglages → Connexions, off by
default); otherwise the answer goes to the athlete's DM with a short note in the
thread. The coach's prompt says who will read the answer.

## Installation

1. At <https://api.slack.com/apps>, choose **Create New App → From a manifest**,
   select workspace `T0C7ZT5V0F7`, and paste [`slack-manifest.json`](../slack-manifest.json).
   Bot scopes: `chat:write`, `im:history`, `im:write` (DM answers to channel
   mentions), `users:read` and `users:read.email` (identity), `channels:history`
   and `groups:history` (the dedicated channel). No user token, no Socket Mode.
2. Install the app from **OAuth & Permissions** (reinstall after a scope change).
   Set these variables on the Arete Vercel project, in Production only:

   | Variable | Value |
   |---|---|
   | `SLACK_SIGNING_SECRET` | Basic Information → App Credentials → Signing Secret |
   | `SLACK_BOT_TOKEN` | OAuth & Permissions → Bot User OAuth Token (`xoxb-…`) |
   | `SLACK_TEAM_ID` | `T0C7ZT5V0F7` |
   | `SLACK_CHANNEL_ID` | The dedicated channel's ID (optional: unset = DMs only) |

   Pipe copied values through `tr -d '[:space:]'` into `vercel env add`; never put
   secrets in source, command arguments or chat. A new deployment applies them.
3. The manifest subscribes to `message.im`, `message.channels` and
   `message.groups` at `https://arete-arete15.vercel.app/api/slack/events`. Invite
   Arete to the dedicated channel (`/invite @Arete`).
4. Send Arete a DM, then mention it in the channel. Check one `Agent run:` log per
   answered message, and that a member without an Arete account gets the
   "no account" reply.

Slack must reach this endpoint without Vercel Authentication. The endpoint
verifies HMAC signatures and rejects requests older than five minutes before
parsing them. With `ARETE_AUTH=clerk`, `/slack/events` is a public path: Slack
sends no Clerk session, so the signature is its only credential. Calendar tools
stay unavailable from Slack because they need a verified Clerk session.

## Execution and limits

The endpoint acknowledges before its attached FastAPI background task imports
the coach, restores journal files or queries MotherDuck. The deployed Vercel
Python runtime must support the full ASGI response lifecycle (verified against
`vercel-runtime==0.23.2`, bundled by CLI 63.1.0). This is not a detached task or a
durable job queue. A process terminated after acknowledgment can lose the job;
it is deliberately not replayed. Cold app startup still runs schema initialization
before the route: validate Slack's three-second receipt deadline on the actual
deployment, including a cold start. Slack retries are deduplicated in the database.

One Slack coach run at a time per athlete, across instances; overlapping
requests from that athlete receive a busy response and are not queued. On MotherDuck two near-simultaneous
admissions can conflict on the reservation row; the loser is answered busy
too, and releasing a finished run retries its idempotent write up to five
times. Existing browser runs are independent. A turn
has a 240-second coaching/history/send deadline, up to one history fetch and one
answer send, each HTTP call has a 10-second timeout and no retries. The existing
8 model-call / 32 tool-call limits and complete-context token guard still apply.
No model requests are added for Slack formatting or suggestions.

History is read from Slack, at most 60 messages (16,000 characters per user
message, 39,000 per answer). Partial,
paginated or stale history, and other members' messages in a DM, are rejected
explicitly, never truncated.
The reply is plain text, bounded to 39,000 characters, with automatic mentions
and unfurls disabled. No message text is stored in the delivery ledger. Existing
optional LangSmith tracing still includes the messages and Slack thread ID.

Migration 37 adds `app.slack_deliveries` (and `app.slack_execution`, unused since
migration 38). Migration 38 adds `app.slack_athletes`: per athlete, the public-reply
consent and the run reservation.
The ledger stops accepting new events at 100,000 records, requiring operator
review rather than silently forgetting duplicate IDs.

## Interrupted runs

An interrupted coach can already have committed a write, and synchronous tools
may finish after cancellation. Its reservation therefore stays locked. Check the
event's logs, wait until its Vercel invocation and tools have stopped, and inspect
training data in Arete. Do not resend the original request blindly.

Once the outcome is understood, an operator can clear **that exact event's**
reservation in the MotherDuck SQL console (replace the literal event key):

```sql
UPDATE app.slack_athletes SET run_event_key = NULL
WHERE run_event_key = 'T0C7ZT5V0F7:Ev_REVIEWED_EVENT';
```

This unblocks only the athlete that event belonged to; other athletes were never
blocked.

Keep its delivery row: deleting it would allow an old Slack delivery to execute
again. This does not queue or replay any blocked messages. A send failure after a
completed coach run releases execution but is not retried, because Slack may
have accepted the message before the connection failed.

## References

- [Slack Events API acknowledgment and retries](https://docs.slack.dev/apis/events-api/)
- [Slack signature verification](https://docs.slack.dev/authentication/verifying-requests-from-slack/)
- [Thread history API](https://docs.slack.dev/reference/methods/conversations.replies/)
- [User profile and email](https://docs.slack.dev/reference/methods/users.info/)
- [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi)
