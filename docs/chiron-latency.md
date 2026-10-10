# Chiron: perceived latency

The [approved Figma exploration](https://www.figma.com/design/gzX3POjHbPbtjw8I1Nz8Vj?node-id=101-5208)
adds immediate feedback and a compact activity journal to the existing coach.
The implementation reuses Inter, JetBrains Mono, the original Chiron portrait,
semantic theme colors, streamed markdown and document attachments. It works in
the side panel, expanded desktop conversation and mobile layout.

## Activation and ownership

The existing Settings gamification opt-in (`useGamePreference().enabled`) enables
Chiron's new presentation. Opting out keeps the original coach presentation.
`CoachActivity` owns presence, elapsed time and the collapsed activity journal;
`agentActivity` owns French action labels and the whole-run replay guard.
`ToolActivity` remains the shared event detail renderer. There is no new package,
server event, API endpoint, database migration or model request. Existing optional
auto-suggestions are unchanged.

## State contract

| Evidence | Visible feedback |
| --- | --- |
| Local send | “Demande envoyée”, stop available immediately |
| Successful HTTP response with stream body | “Chiron prépare sa réponse” |
| `tool_start` | Actual action label; parallel unfinished actions remain pending |
| Successful `tool_end` | Result-specific confirmation; a read is never described as a write |
| Failed `tool_end` | Failure remains visible even when another action succeeds |
| `token` / `message` | Render received markdown immediately, without an artificial typing delay |
| `done` | Stop presence; retain the response and activity |
| Stop / lost stream | Retain text, next draft and attachments; unfinished actions have an unknown outcome |

Tool status comes from the existing runtime classification before preview
truncation. The browser does not infer success by parsing output snippets.
Unknown tool names receive a neutral label. Garmin operation cards retain their
own authoritative domain outcome; a completed tool is not a delivery guarantee.

The activity details show elapsed time, not an estimated remaining duration.
After eight seconds without answer text, one static notice explains that the
athlete can continue using Arete. Browser offline state has its own notice.
The clock uses the originating request timestamp across hiding/switching threads,
and stops at the transport's 310-second bound. No live region announces its ticks.

Retry/regenerate remains available for plain-text requests. A run containing tool
activity, calendar proposals, imports or workout results cannot be replayed as a
whole: that could duplicate a committed action or erase the evidence needed to
check it. The athlete can send a new follow-up while retaining the original run.
This guard applies in both coach presentations, including restored conversations.

## Motion and accessibility

The approved Smart Animate variants are translated into CSS state animations:
three 5-pixel dots travel 3 pixels with a 280 ms stagger over a 1.28-second cycle.
Confirmation settles in 260 ms. Labels fade in 160 ms and text blocks in 120 ms,
once per block, never once per token. The original portrait does not move.
The confirmation mask is the exported Figma vector, colored with the app's success
token so Odyssey and Performance remain consistent. Reduced-motion preferences
disable the loop and all new transitions while keeping identical status text.

Only a pending response owns a clock and connectivity listeners. UI state changes
do not create network or model requests. The existing bounded performance buffer
also records `coach:time-to-feedback` and `coach:time-to-first-text`; these measure
browser feedback and actual first text independently of provider latency.

## Validation

Component and hook tests cover transport acceptance, elapsed time, parallel tools,
read/write labels, errors, interruption, offline state and replay prevention.
`frontend/browser-tests/chiron.spec.ts` uses a local SSE fixture, never a real model.
It samples a complete rendered animation cycle, checks immediate text rendering
without remounting the paragraph, verifies draft preservation and one request per
turn, and checks mobile overflow, portrait geometry, both light themes,
reduced motion and opt-out behavior. Run `make check` and
`npm --prefix frontend run test:browser -- chiron.spec.ts`.
