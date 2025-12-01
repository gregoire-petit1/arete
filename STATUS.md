# État d'avancement — Arete

## Contexte & guidelines projet

- Vision : assistant d'entraînement (LLM + RAG + données perso).
- Stack cible : FastAPI, DuckDB (`app.*`), uv (Python 3.11), ingestion CSV, endpoints `/health`, `/plan/jour`, `/log/recent`, CRUD persistance.
- Qualité à mettre en place : ruff, mypy, pytest ; `.env` + `.env.example` ; lancement via `uv run uvicorn arete.api.main:app --reload --app-dir src`.

## État actuel (après migration DuckDB)

- Environnement : Python 3.11 via uv, arbo `src/arete/...`, `.env` / `.env.example` OK, `.gitignore` couvre data/venv.
- Base : DuckDB avec helper `arete.dataio.db.connect`; DDL dans `arete.dataio.init_duckdb` crée `app.training_log`, `app.sessions`, `app.users`, `app.objectives`, `app.personal_records`. DuckDB 1.4.2 ne supporte pas `IDENTITY`/PK, IDs gérés applicatif (`COALESCE(MAX(id)+1)`).
- Ingestion : `arete.dataio.ingest` pour CSV; sample `data/sample_log.csv` ingéré (4 lignes présentes, duplications possibles si ré-ingestion sans purge).
- API : `arete.api.main` expose `/health`, `/plan/jour` (stub), `/log/recent` (lit `training_log`) + router CRUD DuckDB (`/plan/day`, `/sessions`, `/user`, `/objectives`, `/records`).
- Validation : schémas Pydantic avec `date`, bornes via `Field`, `Literal` pour le sexe.
- Tests/CI : aucun pour l'instant.

## Écarts / points d’attention

- IDs générés côté dépôt (pas de contraintes PK DuckDB 1.4.2) : risque de collisions si écriture concurrente (faible dans ce contexte).
- Données démo : `training_log` contient 4 lignes (duplicat possible) — prévoir un reset avant démo/tests.
- Qualité/CI manquants (ruff/mypy/pytest, GH Actions).
- README/STATUS pas encore alignés avec la nouvelle stack DuckDB + dépôt applicatif.

## Next steps (priorisés)

1. **Nettoyage DB démo** : option simple `rm data/arete.duckdb && PYTHONPATH=src uv run python -m arete.dataio.init_duckdb && PYTHONPATH=src uv run python -m arete.dataio.ingest data/sample_log.csv` pour repartir avec 2 lignes.
2. **Qualité & tests** : ajouter ruff/mypy/pytest + tests API (health, plan_jour, log_recent, CRUD) sur DuckDB éphémère.
3. **Docs** : mettre à jour README/STATUS avec commandes (init, ingestion, run API) et mention du fallback ID côté app.
4. **RAG roadmap** : définir le plan d'indexation (embeddings, store), schéma de features (ACWR, charge), et intégration dans `/plan/jour`.
5. **CI/CD light** : GH Actions pour lint/test, badge README.
6. **Front/UX ou clients** (optionnel) : specs pour une mini UI ou collection HTTP (Insomnia/Postman) prête à l'emploi.
