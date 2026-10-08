# Arete — notes for agents

Single-athlete training app: FastAPI + DuckDB backend (`src/arete`), React +
Vite frontend (`frontend/`). Garmin and Strava sync, a training plan, a strength
log, analytics.

## Commands

| Need | Command |
|---|---|
| Everything CI runs (lint, types, tests, frontend build) | `make check` |
| Tests only | `make test` |
| Dev servers, hot reload (API :8000, Vite :5173) | `make dev` |
| Always-on stack (API :8001, frontend :3080) | `make docker` |
| First setup, includes the git hooks | `make install` |

Run `make check` before declaring work done. The pre-push hook only checks
formatting and lint (`ruff`); the tests are yours to run.

## Rules that bite

- **Never `git add -A` or `git add .`** — a hook refuses it, and for good
  reason: orca workspaces can sit inside this directory and get swallowed as
  embedded repositories. Name the paths.
- **DuckDB allows one writer.** While the Docker backend runs, a local script
  that opens `data/arete.duckdb` makes the API answer 500. Prefer the HTTP API
  (`localhost:8001`) to poke at real data.
- **Personal data never goes in git.** `data/` (database, Garmin tokens, FIT
  files) and `PROG_*.md` (training plans) are ignored. Keep it that way.
- **Secrets live in `.env`**, never committed. Hooks block reading it; use
  `.env.example` to learn the variable names.

## Workflow

- Branch, push, open a pull request. CI runs on every pushed branch.
- Branches are deleted on merge. Merge commits are fine; keep commits atomic.
- Conventional Commits (`feat`, `fix`, `chore`, `ci`, `test`), subject in
  English, body explaining *why* — what was broken and what changes.

## Conventions

- UI text is French. Code, comments and commit messages are English.
- Workout text is parsed by declarative Lark grammars, not by an LLM:
  `llm/workout_grammar.py` reads the compact notation (`4x8 @80 bench press`),
  `llm/speech_grammar.py` reads spoken French and franglais. A new turn of
  phrase is a new grammar alternative plus a line in
  `tests/data/dictations.jsonl`, the corpus that guards against regressions.
- Heart-rate zones come from the athlete's threshold, refreshed from Garmin on
  every sync (`features/hr_zones.py`, `garmin/threshold.py`).
- Tests mirror modules (`tests/test_<module>.py`), one behaviour per test,
  descriptive names, external calls mocked.
