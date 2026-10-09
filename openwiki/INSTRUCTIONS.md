# Arete wiki brief

Write concise English documentation grounded in the current source and tests.
Focus on setup and configuration, backend and frontend ownership, data storage
and migrations, Garmin/Strava sync, workout parsing, and the coaching runtime.
Read `AGENTS.md`, `README.md` and `docs/architecture.md` first. Treat design plans
as historical intent: verify behavior against code before documenting it.

Keep generated reference pages in `openwiki/` and link to the maintained guides
in `docs/` instead of duplicating them. Update only facts affected by source
changes; preserve accurate text. Cite source paths and retain grounded Claims.
Never invent successful tests, provider guarantees or deployment configuration.

Do not edit application code, tests, workflows, existing `docs/` guides or this
brief. In `AGENTS.md` and `CLAUDE.md`, only maintain OpenWiki's discovery block;
preserve all existing project instructions. Do not run the application, contact
its API or access training data, credentials, `.env`, `.context/` or databases.
