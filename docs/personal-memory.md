# Personal memory

Arete keeps active personal facts in every model request and retrieves older
source passages with BM25. Conversations remain in browser storage. This is a
context contribution, not a new agent or a separate permission system.

## Ownership and persistence

`services/athlete_facts.py` owns facts, validity and optimistic concurrency.
Migration 19 adds evidence classification, source references, inclusive
`valid_until`, revision numbers and historical snapshots. Existing facts are
`legacy`, including those originally entered in Settings: the migration does not
invent confirmation or reconstruct lost revisions.

`evidence` is independent of `source` (the original writer):

- `explicit`: a declaration by the athlete. New Settings entries and text
  corrections are explicit. The coach must supply a source reference when
  recording an explicit declaration.
- `hypothesis`: a coach inference. Repetition does not confirm it. Settings has an
  explicit confirmation action. This is the tool's conservative default.
- `legacy`: existing evidence whose origin cannot be established retrospectively.

All active facts valid on the server's current date reach the context, grouped by
these three classifications. Future and expired facts remain stored and searchable.
The complete request budget rejects an oversized mandatory context rather than
silently dropping the oldest constraints. Reads are capped at 10,000 facts and a
fact at 1,000 revisions, with explicit failures at the bounds.

An update atomically checks the revision, stores the previous snapshot and
increments the current revision. The history includes both versions and their
recording timestamps; it does not infer when an old statement ceased to be true
in the world. Deletion removes the fact and all its snapshots. No failed write is
retried automatically.

## HTTP and tools

`GET /athlete-facts` adds `evidence`, `source_ref`, `valid_until`, `revision` and
`created_at` to the existing fields. `GET /athlete-facts/{id}/history` returns the
current version followed by older snapshots. Missing facts return 404.

PATCH accepts the new fields and `expected_revision`. DELETE accepts
`expected_revision` as a query parameter. Stale revisions return 409; invalid
values return 422. For compatibility, omission of the revision means **revision
1**, not “overwrite any version”. Older clients can update an untouched row but
must reload/update their client to modify a newer version. The current browser
and coach tool send the displayed revision. PATCH with `valid_until: null` clears
an expiry. Dates are inclusive, so an exception valid through October 10 is still
applicable on October 10.

`remember_fact` retains its name and adds evidence, source reference, revision and
validity dates. A temporary exception is a separate fact, not a rewrite of a
standing preference. Unresolved contradictions call for clarification when they
affect a decision. These prompt rules guide advice; only domain validation can
make a constraint an enforced prohibition on writes.

## Retrieval

`services/personal_context.py` exposes `search_personal_context(query, thread_id,
current_date, limits)`. It returns sourced hits, their traversal paths, corpus and
match counts, an explicit selection-limit flag and elapsed time. An unavailable
source raises an error, never an empty success.

The corpus contains current/historical facts, journal entries and monthly
archives, actual/planned/strength session text, and ready document blocks from
the current thread. Metrics remain the analytics services' responsibility.
Document provenance quotes are excluded from planning text; only references to
blocks authorized in the current thread can be traversed.

BM25Plus uses `k1=1.5`, `b=0.75`, `delta=0`. Unlike common BM25Okapi configurations,
this retains positive scores when a term occurs in most documents. Unicode
normalization folds accents/case but preserves negation, numbers and units.
Passages include source metadata and dates, without LLM-generated summaries.

Named bounds:

- 10,000 passages, 20 MiB of source/indexed text, 1,000 journal-directory entries.
- 800 characters per passage; complete sources are split, never silently cut off.
- 16,000 query characters and 256 unique query terms.
- Eight lexical seeds, two graph hops, 24 visited passages.
- At most 2,048 estimated tokens for the retrieved contribution, further reduced
  to the remaining complete-request budget. Whole selected passages are omitted
  with counts when they cannot fit; mandatory facts/history are preserved.

Graph traversal follows explicit references: fact → previous revision,
actual → planned session, strength → actual session, prescription → authorized
source block, and journal → typed session reference. Server feedback now records
`actual:N` or `strength:N`. Dates/names alone never establish an edge.
**Graph expansion is disabled in production.** `SearchLimits(graph=True)` is
available for evaluation; enablement requires behavior-level evidence, not just
better source recall.

The context builder runs synchronous reads in an AnyIO worker. Each model
boundary rebuilds a disposable corpus, including after memory writes; there is
no process-global index to become stale after correction or deletion. The database
corpus uses one read transaction. Existing filesystem journal synchronization is
unchanged. No automatic reload/replay of an agent run is introduced.

Briefing/feedback remain tool-free and receive their existing facts and recent
journal. Chat retrieval adds zero model calls. `Agent run:` logs include
`memory_searches`, `memory_ms` and the last contribution's `memory_tokens`.
Detailed search logs contain counts/timing, not source text.

## Evaluation

`tests/data/personal_memory_cases.jsonl` has 60 synthetic French cases, with a
fixed 40/20 development/validation split and human-readable behavior rubrics.
Source isolation, concurrency, expiry, deletion, schema migration, runtime
integration and failures have separate service/API/browser tests.

Run the offline selection comparison without accessing athlete data:

```sh
uv run python scripts/eval_personal_memory.py --split development
uv run python scripts/eval_personal_memory.py --split validation
```

It compares the frozen selection baseline (30 facts/five recent entries), BM25
and BM25 plus graph expansion on the same synthetic evidence. The baseline is a
selection ablation, not a replay of the complete former agent. Some cases
intentionally put evidence outside the recent excerpt. Source recall on these
fixtures is not an estimate of production answer quality.

Opt-in answer generation uses one pinned configured-provider model across all
three variants, no tools, no fallback, no retries, temperature 0, 4,096 output
tokens, a 16,384-token envelope and a 60-second timeout. It never opens a database:

```sh
ARETE_EVAL=1 uv run python scripts/eval_personal_memory.py \
  --live --model EXACT_MODEL_ID --split development --limit 5
```

The hard maximum is 180 model calls; the example makes 15. Outputs include usage,
served model, latency and a rubric for human review. Preference compliance,
temporal errors and unsupported claims remain **unknown** until rated. Offline
retrieval success must not populate these metrics. `--ratings` accepts a JSON
list with `id`, `variant`, and boolean `preference_followed`, `temporal_error`,
`unsupported_claim` fields.

Local measurement on a synthetic DuckDB corpus (20 warm reads): 1,000 passages
had warm p95 around 19 ms; 10,000 around 113 ms. First reads were around 43 ms and
112 ms respectively (the latter reused imported libraries). These numbers exclude
MotherDuck networking and serverless startup. The deployment target remains
p95 below 500 ms, to be verified in that environment. Graph remains off until
live answers demonstrate relational gains without constraint regressions.

Migration is additive and runs through normal initialization; no production data
or deployment is touched by the offline tests. Run `make check` before shipping.
