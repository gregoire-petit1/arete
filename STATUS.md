# État d'avancement — Arete

## Contexte & guidelines projet

- Vision : assistant d'entraînement (LLM + RAG + données perso).
- Stack cible : FastAPI, DuckDB (`app.*`), uv (Python 3.11), ingestion CSV, endpoints `/health`, `/plan/jour`, `/log/recent`, CRUD persistance.
- Qualité : ruff, mypy, pytest ; `.env` + `.env.example` ; lancement via `uv run uvicorn arete.api.main:app --reload --app-dir src`.

## État actuel (mise à jour 2025-01)

### Infrastructure

- Environnement : Python 3.11 via uv, arbo `src/arete/...`, `.env` / `.env.example` OK, `.gitignore` couvre data/venv.
- Base : DuckDB avec helper `arete.dataio.db.connect`; DDL dans `arete.dataio.init_duckdb` crée `app.training_log`, `app.sessions`, `app.users`, `app.objectives`, `app.personal_records`.
- DuckDB 1.4.2 ne supporte pas `IDENTITY`/PK, IDs gérés applicatif (`COALESCE(MAX(id)+1)`).

### API

- `arete.api.main` expose `/health`, `/plan/jour` (stub), `/log/recent?n=` avec validation du paramètre
- Router CRUD DuckDB (`/sessions`, `/user`, `/objectives`, `/records`) avec pagination validée
- Validation : schémas Pydantic v2 avec `date`, bornes via `Field`, `Literal` pour le sexe
- Calcul BMI extrait dans helper `_calculate_bmi()`

### Sécurité & Robustesse (CodeRabbit review fixes)

- ✅ Gestion des ressources : connexions DB fermées via try/finally
- ✅ DELETE atomique avec `RETURNING` (pas de TOCTOU)
- ✅ Transaction pour création user (race condition évitée)
- ✅ Validation pagination : `_validate_pagination()` avec MAX_LIMIT=100
- ✅ Ingestion CSV : CAST avec whitelist `ALLOWED_COLUMNS`, pas de TRY_CAST
- ✅ Contraintes NOT NULL ajoutées au schéma DDL

### Qualité & Tests

- ✅ ruff (lint + format) configuré dans pyproject.toml
- ✅ mypy configuré (quelques warnings à résoudre)
- ✅ pytest avec 19 tests (API + repository)
- ✅ GitHub Actions CI (.github/workflows/ci.yml) : lint, test, typecheck

### Données

- Ingestion : `arete.dataio.ingest` pour CSV
- Colonnes françaises dans training_log (compatibilité CSV existant) : `duree_min`, `allure_minkm`, `sommeil_h`, `poids_kg`, `denivele_m`, `douleurs`, `course_date`, `objectif_tps`
- Sample `data/sample_log.csv` avec 2 lignes

## Commandes utiles

```bash
# Installation
uv sync --dev

# Initialiser la base
uv run python -c "from arete.dataio.init_duckdb import main; main()"

# Ingérer les données sample
uv run python -c "from arete.dataio.ingest import ingest_csv; ingest_csv('data/sample_log.csv')"

# Lancer l'API
uv run uvicorn arete.api.main:app --reload --app-dir src

# Reset complet
rm data/arete.duckdb && uv run python -c "from arete.dataio.init_duckdb import main; main()" && uv run python -c "from arete.dataio.ingest import ingest_csv; ingest_csv('data/sample_log.csv')"

# Tests & qualité
PYTHONPATH=src uv run pytest tests/ -v
uv run ruff check src tests
uv run ruff format src tests
```

## Écarts / points d'attention

- IDs générés côté dépôt : risque théorique de collisions si écriture concurrente (faible dans ce contexte mono-user).
- mypy : 11 warnings (fetchone() peut retourner None) - non bloquants.

## Next steps (priorisés)

1. **RAG roadmap** : définir le plan d'indexation (embeddings, store), schéma de features (ACWR, charge), et intégration dans `/plan/jour`.
2. **Features engineering** : module `src/arete/features/` pour calcul ACWR, charge monotony, etc.
3. **LLM integration** : connexion OpenAI/local LLM pour génération de recommandations.
4. **Front/UX** : mini UI ou collection HTTP (Insomnia/Postman) prête à l'emploi.
5. **Déploiement** : Docker, fly.io ou Render pour démo live.
