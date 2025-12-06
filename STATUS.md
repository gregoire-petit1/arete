# État d'avancement — Arete

## Contexte & guidelines projet

- Vision : assistant d'entraînement (LLM + RAG + données perso).
- Stack cible : FastAPI, DuckDB (`app.*`), uv (Python 3.11), ingestion CSV, endpoints `/health`, `/plan/jour`, `/log/recent`, CRUD persistance.
- Qualité : ruff, mypy, pytest ; `.env` + `.env.example` ; lancement via `uv run uvicorn arete.api.main:app --reload --app-dir src`.

## État actuel (mise à jour 2025-12-03)

### Infrastructure

- Environnement : Python 3.11 via uv, arbo `src/arete/...`, `.env` / `.env.example` OK, `.gitignore` couvre data/venv.
- Base : DuckDB avec helper `arete.dataio.db.connect`; DDL dans `arete.dataio.init_duckdb` crée `app.training_log`, `app.sessions`, `app.users`, `app.objectives`, `app.personal_records`.
- DuckDB 1.4.2 ne supporte pas `IDENTITY`/PK, IDs gérés applicatif (`COALESCE(MAX(id)+1)`).
- **248 tests** passants, CI GitHub Actions

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

| Limite Groq (llama-3.3-70b) | Valeur  | Notre usage |
| --------------------------- | ------- | ----------- |
| Tokens/minute               | 12,000  | ~2,000/req  |
| Tokens/jour                 | 100,000 | ~50 req/day |
| Requests/minute             | 30      | ~1-2        |
| Requests/jour               | 1,000   | ~50         |

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

### Garmin Pipeline ✅ NEW (2025-12-03)

Module complet `src/arete/garmin/` pour l'analyse automatisée des activités Garmin :

#### Architecture du module

| Fichier          | Description                                      |
| ---------------- | ------------------------------------------------ |
| `models.py`      | Dataclasses PlannedSession, ActualSession, etc.  |
| `fit_parser.py`  | Parsing FIT avec fitparse (time series, laps)    |
| `repository.py`  | CRUD DuckDB pour sessions planifiées/réalisées   |
| `matcher.py`     | Matching automatique planned ↔ actual            |
| `time_series.py` | TimeSeriesData, DerivedMetrics, WorkoutStructure |
| `analyzer.py`    | Analyse LLM (basique, détaillée, intervalles)    |

#### FIT Parser (`fit_parser.py`)

- Parsing fichiers `.FIT` via fitparse>=1.2.0
- Mode `detailed=True` : extraction time series complète
- Extraction des données :
  - **Session** : sport, durée, distance, HR, pace, élévation
  - **Records** : HR, speed, cadence, power, altitude, GPS (1Hz)
  - **Running Dynamics** (HRM-Pro) : stance time, vertical oscillation, step length
  - **Laps** : intensité (warmup/active/rest), durée, pace, HR
- Calcul automatique zones HR (5 zones basées sur HRmax)

#### Time Series Analysis (`time_series.py`)

**TimeSeriesPoint** - Données par seconde :

- Core : heart_rate, speed_mps, cadence, power, altitude
- Running dynamics : stance_time, stance_time_balance, step_length, vertical_oscillation, vertical_ratio
- GPS : lat, lon

**DerivedMetrics** - Métriques calculées :

- HR : avg, max, drift%, decoupling%
- Pace : avg, CV%, fade%
- Cadence : avg, CV%
- Power : avg, NP (normalized power), VI (variability index)
- Running dynamics : stance_ms, stance_drift%, step_mm, vert_osc_mm, vert_ratio%, balance%
- Elevation : ascent_m, descent_m, impact
- Splits : km-by-km avec pace, HR

**WorkoutStructure** - Analyse des laps :

- Détection automatique interval workouts
- Groupement par intensité (warmup/work/rest/cooldown)
- Métriques intervalles : pace_cv%, hr_drift%
- Identification meilleur/pire intervalle

#### Session Matching (`matcher.py`)

- Matching automatique planned ↔ actual sessions
- Scores de confiance : HIGH (>80%), MEDIUM (50-80%), LOW (<50%)
- Critères : date, sport, durée (tolérance 20%), distance

#### LLM Analyzer (`analyzer.py`)

3 modes d'analyse avec prompts optimisés tokens :

| Mode       | Description                   | Données                    |
| ---------- | ----------------------------- | -------------------------- |
| `basic`    | Adhérence planned vs actual   | Résumé session             |
| `detailed` | Analyse technique approfondie | DerivedMetrics (~500 char) |
| `interval` | Analyse séance qualité        | WorkoutStructure JSON      |

**Format réponse LLM** :

- `performance` : note A-F, forces, faiblesses
- `technique` : analyse, conseils
- `physiologie` : hr_analysis, fatigue_indicators
- `pacing` : evaluation, suggestion
- `intervalles` : progression, meilleur/pire intervalle
- `recommendation_prioritaire` : une action clé

**Fallback rule-based** si LLM indisponible.

#### Garmin API (`src/arete/api/garmin.py`)

| Endpoint                          | Méthode | Description                           |
| --------------------------------- | ------- | ------------------------------------- |
| `/garmin/planned`                 | POST    | Créer session planifiée               |
| `/garmin/planned`                 | GET     | Lister sessions planifiées            |
| `/garmin/planned/{id}`            | GET     | Détail session planifiée              |
| `/garmin/planned/{id}`            | DELETE  | Supprimer session planifiée           |
| `/garmin/upload-fit`              | POST    | Upload fichier FIT + matching auto    |
| `/garmin/actual`                  | GET     | Lister sessions réalisées             |
| `/garmin/actual/{id}`             | GET     | Détail session réalisée               |
| `/garmin/actual/{id}/match/{pid}` | POST    | Matcher manuellement                  |
| `/garmin/actual/{id}/match`       | DELETE  | Supprimer matching                    |
| `/garmin/actual/{id}/analyze`     | POST    | Lancer analyse LLM                    |
| `/garmin/actual/{id}/analysis`    | GET     | Récupérer analyse existante           |
| `/garmin/summary`                 | GET     | Stats matching (total, matched, etc.) |
| `/garmin/unmatched`               | GET     | Lister sessions non-matchées          |

**Paramètres analyse** :

- `?detailed=true` : analyse détaillée avec time series
- `?force=true` : régénérer même si cache existant

#### Exemple d'utilisation

```bash
# 1. Créer une session planifiée
curl -X POST http://localhost:8000/garmin/planned \
  -H "Content-Type: application/json" \
  -d '{"date": "2025-12-03", "session_type": "intervals", "description": "4x8min @4:20-4:25 r2min"}'

# 2. Upload FIT file (matching automatique)
curl -X POST http://localhost:8000/garmin/upload-fit \
  -F "file=@data/activity.fit"

# 3. Analyse détaillée avec structure intervalles
curl -X POST "http://localhost:8000/garmin/actual/1/analyze?detailed=true"
```

**Exemple réponse analyse interval** :

```json
{
  "analysis_type": "interval",
  "insights": {
    "execution": {"note": "B", "regularite": "bonne"},
    "intervalles": {
      "analyse": "Allures régulières (CV 1.5%)",
      "progression": "positive",
      "meilleur_intervalle": 5,
      "pire_intervalle": 2
    },
    "_workout_structure": {
      "type": "intervals",
      "structure": "8x work + rest",
      "warmup": "19min",
      "intervals": [{"n": 1, "pace": "4:32", "hr": 179}, ...],
      "rest_avg": "2.0min",
      "pace_cv%": 1.5,
      "hr_drift%": 4.5
    }
  }
}
```

### Sécurité & Robustesse (CodeRabbit review fixes)

- ✅ Gestion des ressources : connexions DB fermées via try/finally
- ✅ DELETE atomique avec `RETURNING` (pas de TOCTOU)
- ✅ Transaction pour création user (race condition évitée)
- ✅ Validation pagination : `_validate_pagination()` avec MAX_LIMIT=100
- ✅ Ingestion CSV : CAST avec whitelist `ALLOWED_COLUMNS`, pas de TRY_CAST
- ✅ Contraintes NOT NULL ajoutées au schéma DDL

### Strength Training Module ✅ NEW (2025-12-03)

Module complet `src/arete/strength/` pour l'entraînement musculaire :

#### Architecture du module

| Fichier         | Description                                        |
| --------------- | -------------------------------------------------- |
| `models.py`     | Dataclasses Exercise, ExerciseSet, StrengthSession |
| `repository.py` | CRUD complet + PRs + trends + volume par muscle    |

#### Modèles de données

**Exercise** - Bibliothèque d'exercices :

- name, category (compound/isolation/accessory), primary_muscle, secondary_muscles
- equipment, instructions, default_rest_seconds

**ExerciseSet** - Série individuelle :

- exercise_id, weight_kg, reps, rpe (1-10), rest_seconds, notes, tempo

**StrengthSession** - Session complète :

- date, exercises avec sets, duration_min, notes, fatigue_level

#### Repository Features

- `create_exercise()`, `get_exercise()`, `list_exercises()`
- `create_strength_session()` avec sets atomiques
- `get_personal_record()` - meilleur 1RM estimé par exercice
- `get_all_prs_summary()` - tous les PRs avec métadonnées
- `get_strength_trends(days=30)` - volume par muscle, session count

#### Strength API (`src/arete/api/strength.py`)

| Endpoint                     | Méthode | Description                  |
| ---------------------------- | ------- | ---------------------------- |
| `/strength/exercises`        | POST    | Créer exercice               |
| `/strength/exercises`        | GET     | Lister exercices (filtrable) |
| `/strength/exercises/{id}`   | GET     | Détail exercice              |
| `/strength/sessions`         | POST    | Créer session avec sets      |
| `/strength/sessions`         | GET     | Lister sessions              |
| `/strength/sessions/{id}`    | GET     | Détail session               |
| `/strength/prs`              | GET     | Tous les PRs                 |
| `/strength/prs/{exercise}`   | GET     | PR pour un exercice          |
| `/strength/trends`           | GET     | Tendances 30 jours           |
| `/strength/volume-by-muscle` | GET     | Volume par groupe musculaire |

### RAG Enrichment ✅ NEW (2025-12-03)

Enrichissement du contexte RAG avec données personnelles :

#### Strength Benchmarks (`retriever.py`)

**StrengthBenchmark** dataclass :

- exercise, category, muscle
- estimated_1rm, weight_kg, reps

**UserContext enrichi** :

- `strength_benchmarks: list[StrengthBenchmark]`
- `strength_session_count_30d`, `strength_total_volume_30d`
- `strength_volume_by_muscle: dict[str, float]`

#### Cardio Benchmarks (`retriever.py`)

**CardioBenchmark** dataclass :

- avg_cadence_spm, avg_vertical_oscillation_mm
- avg_ground_contact_time_ms, avg_stride_length_m
- avg_easy_hr, avg_easy_pace, best_pace
- total_distance_km_90d, session_count_90d

**HR Drift Detection** :

- Détection sessions avec spread HR >20% (potential_fatigue flag)
- `hr_drift_flags: list[str]` dans UserContext

#### Helper Functions (`augmented_generator.py`)

- `enrich_context_with_strength(context, db_path)` - ajoute PRs et volume
- `enrich_context_with_cardio(context, db_path)` - ajoute running dynamics
- `enrich_context_full(context, db_path)` - combine les deux

#### Prompt Integration

Le prompt RAG inclut maintenant :

- Résumé strength (PRs principaux, volume 30j)
- Résumé cardio (cadence, pace, sessions récentes)
- Flags de fatigue HR drift

### Frontend React ✅ NEW (2025-12-06)

Application React avec thème "Hunter" (Solo Leveling inspired).

#### Stack Frontend

| Technologie    | Version | Usage         |
| -------------- | ------- | ------------- |
| React          | 19.1.0  | UI Framework  |
| Vite           | 7.2.5   | Build tool    |
| TailwindCSS    | 4.1.7   | Styling       |
| Framer Motion  | 12.15.0 | Animations    |
| TanStack Query | 6.0.0   | Data fetching |
| Lucide React   | 0.513.0 | Icons         |
| React Router   | 7.6.1   | Navigation    |

#### Pages

| Page        | Route          | Description                            |
| ----------- | -------------- | -------------------------------------- |
| HUD         | `/`            | Dashboard fitness (CTL/ATL/TSB, ACWR)  |
| Forge       | `/forge`       | Strength training + anatomical heatmap |
| Matrix      | `/matrix`      | Calendar view sessions                 |
| Quest Log   | `/quest-log`   | Planned sessions list                  |
| Neural Link | `/neural-link` | RAG chat interface                     |
| Settings    | `/settings`    | User preferences                       |

#### Composants clés

- **AnatomicalHeatmap** : Vue corps avant/arrière style Garmin avec muscles colorés par volume
- **FitDropzone** : Upload fichiers FIT par drag & drop
- **LoadChart** : Graphique charge (ATL/CTL/TSB)
- **MetricCard** : Cards métriques avec animations
- **SessionTimeline** : Timeline sessions sur 7 jours
- **StatusBar** : Barre de statut système

#### Thème Hunter

- Palette dark : `void (#0a0a0f)`, `neon-purple`, `neon-cyan`, `warning-orange`, `danger-red`
- Fonts : Inter (sans), JetBrains Mono (mono)
- Glass panels avec blur et bordures subtiles
- Animations fluides (Framer Motion)

### Exercise Knowledge Base ✅ NEW (2025-12-06)

Module `src/arete/data/` avec catalogue d'exercices et seeding.

#### Catalogue (`exercises_catalog.py`)

- **46 exercices** avec mappings muscles primaires/secondaires
- **20 groupes musculaires** organisés par région (chest, back, shoulders, arms, legs)
- **Alias d'exercices** : bp → bench_press, pu → pull_up, dl → deadlift, etc.
- Catégories : chest, back, shoulders, arms, legs

#### Seeding (`seed_exercises.py`)

- Crée tables DuckDB : `app.muscles`, `app.exercises`
- Seed ChromaDB : collection `exercises` (46 docs), collection `protocols` (muscle groups)
- Script idempotent (INSERT OR REPLACE)

#### Volume Calculation Update

`strength/repository.py` mis à jour :

- `get_volume_by_muscle()` inclut muscles secondaires (pondérés à 50%)
- Lookup via `EXERCISES_BY_ID` pour mappings précis

### RAG Response Format Refactor ✅ NEW (2025-12-06)

Système de réponse RAG adaptatif selon l'intention de la question.

#### Intent Detection

`augmented_generator.py` détecte automatiquement :

| Intent        | Mots-clés                              | Format réponse     |
| ------------- | -------------------------------------- | ------------------ |
| session_plan  | séance, entraînement, programme        | Plan structuré     |
| exercise_info | muscle, travaille, exercice, technique | Info exercice      |
| analysis      | analyse, charge, récupération, fatigue | Points clés + reco |
| general       | (autres)                               | Réponse libre      |

#### Formats de réponse

**session_plan** :

```json
{"type": "session_plan", "titre": "...", "sections": [...], "cibles": {...}, "charge_prevue": "..."}
```

**exercise_info** :

```json
{"type": "exercise_info", "exercice": "...", "muscles_principaux": [...], "muscles_secondaires": [...], "conseils": [...]}
```

**analysis** :

```json
{"type": "analysis", "titre": "...", "resume": "...", "points_cles": [...], "recommandations": [...]}
```

#### Frontend Components

Composants React modulaires dans `NeuralLink.tsx` :

- `SessionPlanView` : affiche sections, cibles, charge
- `ExerciseInfoView` : affiche muscles (rouge primaire, orange secondaire), conseils, variantes
- `AnalysisView` : affiche points clés colorés (bon/attention/alerte), recommandations
- `GeneralView` : affiche réponse texte + points clés

### Qualité & Tests

- ✅ ruff (lint + format) configuré dans pyproject.toml
- ✅ mypy configuré et 100% clean sur features/ et api/
- ✅ pytest avec **248 tests** (API + repository + features + metrics API + LLM + RAG + TokenManager + Strength + Garmin)
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
5. ~~**Garmin Pipeline** : parsing FIT, matching planned/actual, analyse LLM détaillée + intervalles.~~ ✅ **DONE**
6. ~~**Strength Module** : module muscu avec exercices, sets, PRs, volume tracking.~~ ✅ **DONE**
7. ~~**RAG Enrichment** : benchmarks personnels (strength + cardio) dans le contexte RAG.~~ ✅ **DONE**
8. ~~**Frontend React** : UI "Hunter" theme avec dashboard, heatmap musculaire, chat RAG.~~ ✅ **DONE**
9. ~~**Exercise Knowledge Base** : catalogue 46 exercices avec muscles primaires/secondaires, seeding ChromaDB.~~ ✅ **DONE**
10. ~~**RAG Response Refactor** : détection d'intent (session_plan, exercise_info, analysis) et formats adaptatifs.~~ ✅ **DONE**
11. **Training Session Parser** : parsing des notes d'entraînement utilisateur vers sessions structurées.
12. **Enhanced Analytics** : tendances volume par muscle, tracking PRs, recommandations récupération.
13. **Goal Tracking** : définition d'objectifs, suivi de progression, blocs d'entraînement IA.
14. **Déploiement** : Docker, fly.io ou Render pour démo live.
