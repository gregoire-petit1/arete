# Conversational workouts and Garmin Connect

Chat accepts requests such as “Prépare un fractionné mardi, avec 15 minutes
faciles, 6 × 400 m et 90 secondes de récupération, puis envoie-le sur Garmin”.
The planning toolkit persists a versioned coach prescription. The preloaded Garmin
toolkit inspects, exports and reconciles it without OCR or an import draft. Missing
required parameters are requested; an explicit export request supplies intent.
Document imports retain their separate human source validation.

## Execution and UI

- A local acknowledgement requires no model request. Created sessions and export
  transitions arrive as `workout_update` events before the final answer. Each carries
  a thread, tool-call identifier, sequence, session revision and durable export state.
- The same card displays dates, literal step summaries, expandable prescriptions,
  local persistence and Garmin status in chat and inside existing Planning rows.
  Distance steps never receive a guessed duration.
- Selection, editing and sending use HTTP directly. Connect is the default; device
  discovery starts only when watch transfer is selected. A transfer request never
  claims successful receipt on the watch.
- Direct actions in chat append a factual message to the originating thread.
  Revision checks protect edits and selection; durable reservations protect writes
  from overlapping chat, Planning and daily jobs. Legacy IDs are verified and reused.
- Cards refresh after mutations, remount and reconnection. Revision and durable
  update time reject stale state. Browser conversation storage accepts old messages
  and restores workout references; the server remains authoritative.
- Navigation/hiding the panel preserves the run in the app provider. Closing or
  reloading the tab does not promise background completion. Stop closes the response,
  not a committed remote write. Runs containing workouts have no automatic replay.
- Errors keep successful results visible. An uncertain operation requires Garmin
  reconciliation; no batch or write retry runs automatically.

The service batch is sequential: at most five sessions, 120 seconds total, 60 remote
requests, at most 12 requests per session, clamped to the invocation deadline.
Planning selects at most 50 sessions and sends batches of five, stopping on the
first failure. Cards poll only active writes, every second for at most 150 seconds.
Chat retains eight model requests, 32 tools and five minutes. No auxiliary model
request animates the UI or generates follow-ups.

## Verification and measurement

`make check` covers backend, frontend unit tests, lint, types and build.
`cd frontend && npm run test:browser` includes a real chunked SSE fixture with
1, 10 and 30 second response delays, cards before `done`, hiding/reopening chat,
restoration, focus, mobile direct edits/exports, reduced motion and uncertain
export recovery without replay. The remote Garmin service is simulated; these
checks do not establish real account/device compatibility or model success rates.

Browser Performance measures include `coach:time-to-useful-result`,
`coach:time-to-scheduled`, `coach:total`, `coach:last-stream-gap`,
`workout:event-to-card` and `workout:action-total`. Marks and measures replace their
previous value rather than growing with conversation length. The card measure is
an effect-time approximation, not a browser paint or INP measurement. Browser test
attachments report simulated delay, time until the card is visible and recorded
measures. No measured production latency improvement is claimed.

A local mock-model context-budget run measured 5,565 approximate tokens before
history/page data: 1,312 system tokens and 4,249 schema tokens for 25 tools. Use
`scripts/agent_context_budget.py` with a disposable database to repeat it. Four
model calls for inspect → create → export → answer is a target, not a hard promise;
actual calls remain observable in the `Agent run:` log.

Before releasing, perform a separate live acceptance with Arthur's chosen future
session: inspect its content, request Connect export, verify content/date in Connect,
edit locally and verify dirty status, explicitly resend and verify the same remote
workout is reused. Request watch transfer only with an explicitly selected compatible
device and verify receipt on that device. Use a disposable session for cleanup.
No real Garmin writes are performed by the automated suite.

The planned comparison with the previous interface and Arthur's qualitative rating
of 1/10/30-second waits still requires a user session. Automated visibility timings
are not a usability study and do not validate the 100/200 ms design targets or INP.
