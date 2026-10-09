# Documents → Planning → Garmin Connect

The coach accepts XLSX, XLS, CSV, Markdown, UTF-8 text, PDF, PNG, JPEG and WebP.
Drop up to five files into the coach or use **Joindre des fichiers**. After upload,
ask the coach to prepare sessions. **Vérifier … avant ajout au Planning** opens the
editable preview. Review the original, dates, units, steps and possible duplicates;
only the explicit confirmation inserts the selected sessions into Planning.

The Planning page's **Séances structurées et Garmin Connect** panel is a separate
human action. Select sessions, optionally select a documented compatible device,
review and send. Local edits become **À resynchroniser**. Deleting an exported
session leaves an explicit removal task. No background job exports these workouts.

## Ownership and persistence

Migration 9 adds document/chunk/quota, draft and Garmin operation tables, plus
`prescription`, `provenance` and `revision` on existing planned sessions. Originals,
extractions and drafts use the configured DuckDB/MotherDuck database, not the
server filesystem. Upload reservations count towards quota even when interrupted;
delete incomplete files to release their reservation. Individual 3 MiB chunks are
idempotent, finalized bytes are checked with SHA-256, and finalization is atomic.
Downloads also use chunks to remain below Vercel's response-body limit.

Conversation history stays in browser storage. Each invocation reconstructs only
that thread's ready documents in a Deep Agents StateBackend mounted at
`/attachments/`. Model context receives a manifest; read-only `ls`, `glob`, `grep`
and bounded `read_file` load content. No binary prompt injection, shell, filesystem
write tool or auxiliary model call is introduced. An unvalidated document import
blocks the coach's ordinary planning/workout writes. Human confirmation or explicit
abandonment resolves the draft; abandonment keeps its documents. Deleting a thread
removes its documents/drafts but preserves confirmed prescriptions and source quotes.

`services/documents.py` owns storage/extraction; `services/imports.py` owns validation
and transactional confirmation. A confirmation key plus draft version makes a lost
response safe to retry. Source quotes must match extracted locators exactly. OCR
sources stay marked. Strength uses the existing Lark grammar and exercise matching;
the preview must agree with its recognized sets. Possible duplicates are shown both
against existing sessions and within the draft; they are never silently removed.

PDF.js and one Tesseract worker perform browser extraction with app-hosted English
and French resources. Image-containing PDF pages use OCR so a textual header does
not hide an embedded scan. The document preview shows the original image/PDF beside its transcription, with
image zoom, page/sheet navigation, source references and a filter for OCR confidence
below 80% (or missing confidence). Mobile uses Original/Text tabs. This indicator is
not a guarantee of correctness: high-confidence numbers also require review.
Originals remain downloadable. Preview bytes are SHA-256 checked, requests cancel on
close, and blob URLs are revoked when their views unmount.
XLSX retains formulas and available cached values, dates, coordinates and merged-cell
warnings. XLS retains cached values and decompiled BIFF formulas. If a shared or
array expression cannot be decompiled, its tokens remain visible with a verification
warning; convert to XLSX for a readable expression. Unsupported old formula formats
fail explicitly rather than masquerading as ordinary values.
No macros or formulas are executed. Unsupported, encrypted and malformed files fail
explicitly. OCR and exact source quotes do not prove semantic transcription accuracy:
the athlete must still compare the prescription to the original.

## Bounds

| Resource | Limit |
| --- | --- |
| Original | 20 MiB; 5 per drop |
| Thread | 20 documents / 100 MiB originals / 8 MiB extracted JSON |
| Global originals | 1 GiB reserved and finalized bytes |
| Extraction | 2 MiB per document; 100 PDF pages; 25 MP image/page raster |
| Workbook | 20 sheets / 100,000 cells; 64 MiB expanded XLSX / 1,000 ZIP entries |
| OCR | One worker; 60 seconds per page / 10 minutes per document |
| Draft | 50 sessions, proposed in batches of at most 5; 50 drafts per thread |
| Prescription | 100 steps, 2 nested repeat levels, 1,000 expanded steps |
| Coach | Existing 8 model calls / 32 tools / 300 seconds |
| Garmin | Sequential; 120-second operation budget / 12 HTTP requests / 10 seconds per request |

Exceeding a bound fails explicitly. There is no silent truncation or automatic replay
of an ambiguous write. Large documents should be split before upload.

## Garmin guarantees and limits

`garminconnect==0.3.17` is pinned. `GarminClient` remains the sole authenticated
transport. Outbound exports load tokens locally and use the pinned SDK's session
and headers without its automatic refresh/replay, so the request budget counts
actual requests. An expired/refused token requires reconnecting in Settings.
Authentication and existing activity synchronization retain their current SDK flow.

Conversion is deterministic for running, cycling, pool swimming, strength, walking
and hiking. Unsupported prescriptions remain local with a reason. Examples include
unspecified pools, mixed strokes without explicit individual steps, unrecognized
Garmin exercise names, open heart-rate zones without numeric bounds and unsupported
sport/target combinations. No approximate target conversion or model call is used.

The device list recognizes documented running/cycling/pool-swimming/strength support
for fēnix 8 and Forerunner 965. Other models are explicitly unknown; export to Connect
remains available, but automatic device transfer is disabled. Family names alone do
not establish compatibility. Extend this mapping only with a model-specific Garmin
manual and test it on the device.

The service persists remote IDs, intended content/date, exported fingerprint,
remote snapshot and operation phase before writes. It rereads content and schedules;
remote changes become conflicts. A timeout after a write becomes **indeterminate**,
blocking resends until explicit reconciliation can identify a unique remote object.
Reconciliation is read-only and scans at most 500 workouts. An ambiguous device push
stays indeterminate because delivery cannot be proven. A persistent operation ID
fences stale workers. Explicit removal checks ownership/content and rereads absence.

**Programmé dans Garmin Connect** and **Transfert demandé** are separate states.
Neither means **reçu sur la montre**. Sync Connect with the watch and inspect it.

## Local verification and acceptance

`make dev` prepares the local OCR assets. Production builds do this in `prebuild`,
including Docker and Vercel. Generated OCR assets are ignored by Git and Vercel upload;
the pinned npm dependencies recreate them during build.

```sh
make check
cd frontend
npx playwright install chromium
npm run test:browser
```

Tests use isolated databases and mocked Garmin transport. Browser tests run actual
PDF.js/Tesseract extraction on a tilted printed image and textual/scanned/mixed PDFs,
and exercise drop → preview → confirmation → reload with scripted coach responses.
They also cover separate Garmin confirmation and the document preview on desktop and
mobile (original rendering, OCR confidence filtering, zoom/source controls and Escape
focus restoration). Browser checks run in the frontend CI job.
Backend tests cover actual workbook bytes, formulas, merged sheets, French units,
quotas, isolation, interrupted uploads, source validation, double confirmation,
export reservation, lost create/schedule/delete responses and remote conflicts.
Live LLM interpretation, Garmin authentication/network behavior, MotherDuck/Vercel
persistence and watch reception are **not validated by these mocks**.

Before production acceptance:

1. Review a real training document locally, including ambiguous dates and OCR digits.
2. Update the local Vercel CLI before preview testing (`npm i -g vercel@latest`;
   the detected 59.1.3 predates 63.1.0). Test a Vercel preview backed by an isolated persistent database: upload, reload,
   restart/cold-start and delete a conversation, retaining confirmed sessions.
3. Explicitly send one dated workout per sport compatible with the selected watch.
   Compare every step and date in Connect, sync the watch, then inspect it there.
4. Edit locally and explicitly resync; change the remote workout to verify conflict
   detection; delete locally and explicitly remove only the Arete-created object.

No live Garmin writes, Vercel deployment, commit or push is part of the automated suite.
