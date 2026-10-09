# Arete in Slack

The app answers the athlete's **private text messages**, in a thread. Reply in
that thread to continue; a new top-level DM starts a new conversation. It uses
the existing chat coach, including its training-write capabilities and journal.
Files, edits, channel mentions, shared channels and other users are ignored.
Slack conversations and browser conversations remain separate.

## Installation

1. At <https://api.slack.com/apps>, choose **Create New App → From a manifest**,
   select workspace `T0C7ZT5V0F7`, and paste [`slack-manifest.json`](../slack-manifest.json).
   This only needs `chat:write` and `im:history`; no user token or channel access.
2. Install the app in that workspace from **OAuth & Permissions**. Set these
   environment variables on the **existing Arete Vercel project**, in Production:

   | Variable | Value |
   |---|---|
   | `SLACK_SIGNING_SECRET` | Basic Information → App Credentials → Signing Secret |
   | `SLACK_BOT_TOKEN` | OAuth & Permissions → Bot User OAuth Token (`xoxb-…`) |
   | `SLACK_TEAM_ID` | `T0C7ZT5V0F7` |
   | `SLACK_USER_ID` | `U0C837K76MU` |

   Use the Vercel dashboard or interactive `vercel env add NAME production`;
   never put secrets in source, shell command arguments or chat. Keep Slack
   production credentials out of branch previews. Existing model and MotherDuck
   configuration is reused. No new provider or database is needed.
3. Deploy the reviewed code to the real Arete project. The backend function's
   maximum duration is set to **300 seconds** in `vercel.json`. Vercel needs a new deployment to apply
   environment changes. Follow the repository's local-test and explicit
   shipping-approval workflow.
4. In Slack **Event Subscriptions**, enable events and set Request URL to
   `https://<actual-arete-domain>/api/slack/events`. Add the bot event **message.im**.
   The signed URL challenge is handled without a model call. Reinstall if Slack
   requests it. The manifest intentionally omits the event URL until the real
   deployment exists, so initial app creation does not depend on URL verification.
5. Send Arete a DM such as `Quelle séance aujourd’hui ?`, then reply in its thread.
   Check one `Agent run:` log per message. Verify another member cannot invoke it.

Slack must reach this endpoint without Vercel Authentication. If the deployment
is protected, configure access for this webhook; do not disable protection for
the whole app. The endpoint verifies HMAC signatures and rejects requests
older than five minutes before parsing them.

## Execution and limits

The endpoint acknowledges before its attached FastAPI background task imports
the coach, restores journal files or queries MotherDuck. The deployed Vercel
Python runtime must support the full ASGI response lifecycle (verified against
`vercel-runtime==0.23.2`, bundled by CLI 63.1.0). This is not a detached task or a
durable job queue. A process terminated after acknowledgment can lose the job;
it is deliberately not replayed. Cold app startup still runs schema initialization
before the route: validate Slack's three-second receipt deadline on the actual
deployment, including a cold start. Slack retries are deduplicated in the database.

One Slack coach run at a time across instances; overlapping requests receive a
busy response and are not queued. Existing browser runs are independent. A turn
has a 240-second coaching/history/send deadline, up to one history fetch and one
answer send, each HTTP call has a 10-second timeout and no retries. The existing
8 model-call / 32 tool-call limits and complete-context token guard still apply.
No model requests are added for Slack formatting or suggestions.

History is read from Slack, at most 60 messages (16,000 characters per user
message, 39,000 per answer). Partial,
paginated, stale or foreign history is rejected explicitly, never truncated.
The reply is plain text, bounded to 39,000 characters, with automatic mentions
and unfurls disabled. No message text is stored in the delivery ledger. Existing
optional LangSmith tracing still includes the messages and Slack thread ID.

Migration 17 adds `app.slack_deliveries` and a singleton `app.slack_execution`.
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
UPDATE app.slack_execution SET event_key = NULL
WHERE id = 1 AND event_key = 'T0C7ZT5V0F7:Ev_REVIEWED_EVENT';
```

Keep its delivery row: deleting it would allow an old Slack delivery to execute
again. This does not queue or replay any blocked messages. A send failure after a
completed coach run releases execution but is not retried, because Slack may
have accepted the message before the connection failed.

## References

- [Slack Events API acknowledgment and retries](https://docs.slack.dev/apis/events-api/)
- [Slack signature verification](https://docs.slack.dev/authentication/verifying-requests-from-slack/)
- [Thread history API](https://docs.slack.dev/reference/methods/conversations.replies/)
- [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi)
