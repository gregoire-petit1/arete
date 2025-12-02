# État d'avancement — Arete

## Contexte & guidelines projet

- Vision : assistant d'entraînement (LLM + RAG + données perso).
- Stack cible : FastAPI, DuckDB (`app.*`), uv (Python 3.11), ingestion CSV, endpoints `/health`, `/plan/jour`, `/log/recent`, CRUD persistance.
- Qualité : ruff, mypy, pytest ; `.env` + `.env.example` ; lancement via `uv run uvicorn arete.api.main:app --reload --app-dir src`.

## État actuel (mise à jour 2025-12-02)

### Infrastructure

- Environnement : Python 3.11 via uv, arbo `src/arete/...`, `.env` / `.env.example` OK, `.gitignore` couvre data/venv.
- Base : DuckDB avec helper `arete.dataio.db.connect`; DDL dans `arete.dataio.init_duckdb` crée `app.training_log`, `app.sessions`, `app.users`, `app.objectives`, `app.personal_records`.
- DuckDB 1.4.2 ne supporte pas `IDENTITY`/PK, IDs gérés applicatif (`COALESCE(MAX(id)+1)`).

### API

- `arete.api.main` expose `/health`, `/plan/jour` (stub), `/log/recent?n=` avec validation du paramètre
- Router CRUD DuckDB (`/sessions`, `/user`, `/objectives`, `/records`) avec pagination validée
- Validation : schémas Pydantic v2 avec `date`, bornes via `Field`, `Literal` pour le sexe
- Calcul BMI extrait dans helper `_calculate_bmi()`

### API Metrics ✅ NEW (2025-12-02)

Nouveau router `src/arete/api/metrics.py` exposant les métriques features :

| Endpoint                   | Méthode | Description                                             |
| -------------------------- | ------- | ------------------------------------------------------- |
| `/metrics/workload`        | GET     | ACWR, Monotony, Strain depuis l'historique training_log |
| `/metrics/fitness`         | GET     | CTL/ATL/TSB (Banister model), readiness score           |
| `/metrics/cardio/trimp`    | POST    | Calcul TRIMP pour une session cardio                    |
| `/metrics/strength/1rm`    | POST    | Estimation 1RM (Epley, Brzycki, RPE-based)              |
| `/metrics/strength/inol`   | POST    | Calcul INOL (volume/intensité)                          |
| `/metrics/recommendations` | GET     | Recommandations intelligentes en français               |

Helpers internes :

- `_get_training_loads()` : récupère DailyLoad depuis training_log
- `_get_tss_history()` : calcule TSS estimé depuis RPE × durée

### Features Engineering ✅ NEW (2025-12-01)

Module complet `src/arete/features/` avec métriques scientifiques :

#### Workload (`workload.py`)

- ACWR (Acute:Chronic Workload Ratio) avec EWMA ou fenêtre glissante
- Monotony (variabilité de la charge)
- Strain (indicateur de fatigue accumulée)
- Zones : Danger (>1.5), High Risk (1.3-1.5), Optimal (0.8-1.3), Undertrained (<0.8)
- Références : Gabbett (2016), Foster (1998)

#### Cardio (`cardio.py`)

- TRIMP (Training Impulse) avec pondération par sexe (Banister)
- Zones FC (5 zones basées sur %FCmax ou %FCR)
- Estimation VO2max (Cooper, Rockport, méthode FC)
- Efficiency Factor, calculs de pace

#### Strength (`strength.py`)

- Estimation 1RM : 7 formules (Epley, Brzycki, Lombardi, O'Conner, Wathan, Mayhew, RPE-based)
- Zones de force (5 zones : Recovery → Max Strength)
- INOL (Intensity × Number of Lifts)
- Zones VBT (Velocity-Based Training)
- Volume, tonnage, intensité

#### Fitness-Fatigue (`fitness.py`)

- CTL (Chronic Training Load / Fitness) — EWMA 42 jours
- ATL (Acute Training Load / Fatigue) — EWMA 7 jours
- TSB (Training Stress Balance / Form) = CTL − ATL
- Readiness Score (0-100 composite)
- Zones : Exhausted, Fatigued, Neutral, Fresh, Peak
- Référence : Banister (1975)

#### Recommendations (`recommendations.py`)

- Recommandations intelligentes en français
- Évaluation des risques (ACWR, monotony, strain, TSB)
- Génération de plan hebdomadaire
- Actions prioritaires avec catégories

### LLM Integration ✅ (2025-12-02)

Module `src/arete/llm/` avec intégration Groq :

- **Client** (`client.py`) : Groq API via OpenAI SDK (Llama 3.3 70B Versatile)
- **TrainingContext** : dataclass avec métriques utilisateur
- **generate_plan()** : génération de plan avec fallback intelligent
- **Fallback** : plans prédéfinis si LLM indisponible (high fatigue → recovery, low TSB → regeneration)
- Endpoint `/plan/jour` utilise le LLM avec contexte DB

#### Token Management ✅ (2025-12-02)

Module `token_manager.py` pour optimisation du budget Groq free tier :

| Limite Groq (llama-3.3-70b) | Valeur    | Notre usage |
| --------------------------- | --------- | ----------- |
| Tokens/minute               | 12,000    | ~2,000/req  |
| Tokens/jour                 | 100,000   | ~50 req/day |
| Requests/minute             | 30        | ~1-2        |
| Requests/jour               | 1,000     | ~50         |

Fonctionnalités :
- **Usage tracking** : comptage tokens prompt + completion par requête
- **Rate limiting** : blocage automatique si quotas dépassés
- **Model fallback** : bascule vers modèle plus léger si quota épuisé
- **Prompts optimisés** : réduction de ~60% des tokens (800 vs 2000)
- **Endpoint `/rag/llm/usage`** : statistiques temps réel

### RAG System ✅ (2025-12-02)

Module `src/arete/rag/` avec ChromaDB :

#### Knowledge Base (`knowledge_base.py`)

- ChromaDB PersistentClient avec 3 collections :
  - `scientific` : littérature scientifique (ACWR, Banister, Foster, Mujika)
  - `protocols` : protocoles d'entraînement (deload, recovery, build)
  - `exercises` : base d'exercices (footing, tempo, intervals, long run)
- Embeddings automatiques via ChromaDB (all-MiniLM-L6-v2)
- Metadata sanitization (listes → JSON strings)

#### Retriever (`retriever.py`)

- Récupération contextuelle basée sur métriques utilisateur
- UserContext avec acwr, tsb, fatigue, experience, sport
- get_risk_level() pour évaluation du risque
- infer_intent() : risk_mitigation, variety_seeking, recovery_needed, ready_for_intensity

#### Augmented Generator (`augmented_generator.py`)

- Combine RAG + LLM pour recommandations enrichies
- Cite les sources dans la justification
- Metadata avec sources_retrieved et context_summary

#### Seed Knowledge (`seed_knowledge.py`)

- 5 documents scientifiques (Gabbett, Banister, Foster, Mujika, TRIMP)
- 4 protocoles (deload, recovery, build phase, taper)
- 4 exercices (footing Z2, tempo, intervals, long run)

#### RAG API (`src/arete/api/rag.py`)

| Endpoint                  | Méthode | Description                         |
| ------------------------- | ------- | ----------------------------------- |
| `/rag/query`              | POST    | Génération de plan RAG-augmenté     |
| `/rag/search`             | GET     | Recherche dans la knowledge base    |
| `/rag/stats`              | GET     | Statistiques des collections        |
| `/rag/seed`               | POST    | Seeding de la base de connaissances |
| `/rag/clear/{collection}` | DELETE  | Vidage d'une collection             |

### Sécurité & Robustesse (CodeRabbit review fixes)

- ✅ Gestion des ressources : connexions DB fermées via try/finally
- ✅ DELETE atomique avec `RETURNING` (pas de TOCTOU)
- ✅ Transaction pour création user (race condition évitée)
- ✅ Validation pagination : `_validate_pagination()` avec MAX_LIMIT=100
- ✅ Ingestion CSV : CAST avec whitelist `ALLOWED_COLUMNS`, pas de TRY_CAST
- ✅ Contraintes NOT NULL ajoutées au schéma DDL

### Qualité & Tests

- ✅ ruff (lint + format) configuré dans pyproject.toml
- ✅ mypy configuré et 100% clean sur features/ et api/
- ✅ pytest avec **190 tests** (API + repository + features + metrics API + LLM + RAG + TokenManager)
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

## Next steps (priorisés)

1. ~~**Features engineering** : module `src/arete/features/` pour calcul ACWR, charge monotony, etc.~~ ✅ **DONE**
2. ~~**Intégration API** : exposer les métriques features via endpoints `/metrics/workload`, `/metrics/fitness`, etc.~~ ✅ **DONE**
3. ~~**LLM integration** : connexion Groq/Llama pour génération de recommandations personnalisées.~~ ✅ **DONE**
4. ~~**RAG roadmap** : indexation ChromaDB avec littérature scientifique, intégration dans `/plan/jour`.~~ ✅ **DONE**
5. **Front/UX** : mini UI ou collection HTTP (Insomnia/Postman) prête à l'emploi.
6. **Déploiement** : Docker, fly.io ou Render pour démo live.
