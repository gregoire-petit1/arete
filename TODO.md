# TODO - Arete Development

_Last updated: 16 December 2025_

## 📋 Completed

### 1. ✅ LLM Analysis Enhancement

- [x] Basic activity analysis
- [x] Detailed time series analysis
- [x] Lap-based interval workout detection
- [ ] **Future**: Chart/visual analysis when available

### 2. ✅ Data Formatting Fixes

- [x] `duration_min` formatted as MM:SS
- [x] `distance_km` rounded to 2 decimals

### 3. ✅ Strength Training Module

- [x] Create `src/arete/strength/models.py` (Exercise, ExerciseSet, StrengthSession)
- [x] Create `src/arete/strength/repository.py` (full CRUD + PRs + trends)
- [x] Add DB tables in `init_duckdb.py` (exercises, exercise_sets, strength_sessions)
- [x] Create API endpoints `/strength/*` (12 endpoints)
- [x] 25 tests passing

### 4. ✅ RAG Enrichment

- [x] Strength benchmarks (PRs, 30d volume by muscle group)
- [x] Cardio benchmarks (cadence, vertical osc, stride length, pace)
- [x] HR drift detection (>20% spread = potential fatigue flag)
- [x] `enrich_context_full()` helper for comprehensive context

### 5. ✅ Garmin Connect Sync

- [x] OAuth with Garmin Connect via garth
- [x] Auto-download activities (FIT files)
- [x] Runalyze backup integration
- [x] FIT file parsing with interval detection

### 6. ✅ Frontend React (Hunter Theme)

- [x] React + Vite + TailwindCSS setup
- [x] Dark "Hunter" theme (Solo Leveling inspired)
- [x] HUD page with fitness metrics (CTL/ATL/TSB, ACWR)
- [x] Forge page with strength training heatmap
- [x] Matrix page with calendar view
- [x] Quest Log page with planned sessions
- [x] Neural Link page with RAG chat interface
- [x] Settings page
- [x] Anatomical heatmap (front + back body views)
- [x] FIT file dropzone component

### 7. ✅ Exercise Knowledge Base

- [x] Exercise catalog with 46 exercises
- [x] Primary/secondary muscle mappings
- [x] DuckDB + ChromaDB seeding script
- [x] Volume calculation with secondary muscles (50% weight)

### 8. ✅ RAG Response Format Refactor

- [x] Intent detection (session_plan, exercise_info, analysis, general)
- [x] Adaptive response format per intent type
- [x] Modular frontend components for each response type
- [x] SessionPlanView, ExerciseInfoView, AnalysisView, GeneralView

### 9. ✅ UI Polish & Font Fixes

- [x] Uniformisation polices : `font-display` (Inter) pour titres, `font-mono` (JetBrains Mono) pour corps/labels
- [x] Titre onglet navigateur : "frontend" → "Arete"
- [x] Alignement barres XP (largeur fixe pour valeurs et subtitles)
- [x] Suppression des emojis (Matrix, FitDropzone, NeuralLink)
- [x] Suppression du dégradé violet sur SystemMessage

### 10. ✅ Settings Persistence

- [x] Table `user_settings` dans DuckDB
- [x] Endpoints API `GET/PUT /settings`
- [x] SettingsContext pour état global
- [x] Sauvegarde persistante (display name, theme, goals, etc.)
- [x] Thème dynamique (dark/darker/abyss) appliqué en temps réel
- [x] Display name utilisé dans Neural Link

### 11. ✅ Strength Session Parser (Paste & Parse)

- [x] Hybrid regex + LLM parser for workout text
- [x] Circuit format support (`5x(ex1, ex2)` multipliers)
- [x] Fuzzy exercise matching with abbreviations (db, bb, ohp, rdl)
- [x] Auto-create exercises from catalog when saving
- [x] Fix duplicate exercises in library (search by catalog_id in notes)
- [x] Session saving to database
- [x] Session delete functionality (`[DEL]` button with confirmation)
- [x] Session detail modal (`[VIEW]` button)
- [x] Heatmap connected to strength sessions (volume by muscle)
- [x] Link Forge sessions to Garmin activities (link/unlink in VIEW modal)

---

## 📋 Next Up

### 12. 🔧 UI Fonctionnalités à implémenter

**Goal**: Rendre fonctionnels les éléments UI actuellement non-fonctionnels

- [ ] **The Forge** :
  - [x] NEW SESSION (paste & parse) ✅
  - [x] VIEW session details ✅
  - [x] DELETE session ✅
  - [x] Filtres exercices : mapping catégories corrigé (PUSH/PULL/LEGS/ISO)
  - [x] Link session to Garmin activity ✅
  - [ ] Afficher catégorie dans exercise card

- [ ] **Quest Log** :
  - [ ] Bouton NEW QUEST fonctionnel
  - [ ] Bouton VIEW dans RECENT QUESTS
  - [ ] Clarifier différence Quest vs Session (Quest = planifié, Session = réalisé ?)

- [ ] **Matrix** :
  - [ ] Bouton Refresh fonctionnel
  - [ ] Afficher sessions strength dans calendrier

### 13. 🏋️ Import Séances Muscu - Notations personnelles

**Goal**: Parser les notations spécifiques de l'utilisateur

- [x] Format circuit : `5x(8-10 weighted pull ups @20kg, 15 db lateral raises @20) r2'`
- [ ] Gérer range de reps (`8-10` → stocker min/max ou target)
- [ ] Parser temps de repos (`r2'`, `r1'30`)
- [ ] Support notation "to failure" (`xF`, `AMRAP`)
- [ ] Date dans le texte (`05/12/25:`)
- [ ] Notes par exercice

### 14. 📊 Heatmap Integration Complete

- [x] Strength sessions → heatmap (volume by muscle)
- [ ] Running → heatmap (quads, calves, hamstrings, hip flexors)
- [ ] Rowing → heatmap (back, biceps, legs)
- [ ] Impact musculaire basé sur durée/intensité cardio

### 15. 🎯 Programmation & Objectifs

**Goal**: Planification intelligente basée sur les objectifs

- [ ] Définir objectifs utilisateur (Settings)
- [ ] Vue hebdomadaire/mensuelle de la charge prévue
- [ ] Contexte conservé entre sessions de planification
- [ ] Suggestions IA pour atteindre les objectifs
- [ ] Blocs d'entraînement générés

### 16. 📈 HUD Enhancements

- [ ] Ajout VO2max (depuis Garmin ou estimé)
- [ ] Volume hebdo/mensuel running (vue calendrier style Strava)
- [ ] Heures d'entraînement hebdo par sport (breakdown)
- [ ] Graphiques de progression

### 17. 🏆 Gestion des PRs (Personal Records)

- [x] API PRs existe (`/strength/exercises/{id}/prs`)
- [ ] UI dédiée pour afficher les PRs
- [ ] Historique des PRs par exercice
- [ ] Notifications/célébration nouveau PR

### 18. 🆕 Gestion Exercices

- [x] Fuzzy matching avec abréviations (db, bb, ohp, rdl)
- [x] Auto-create depuis catalog quand sauvegarde
- [ ] UI pour ajouter un exercice manuellement
- [ ] Fusion/matching exercices similaires (même exo écrit différemment)
- [ ] Suggestions d'exercices équivalents

### 19. 📅 Heatmap Période Sélectionnable

- [x] Affiche volume total actuel
- [ ] Sélecteur de période (7j / 30j / 90j)
- [ ] Comparaison période précédente
- [ ] Tendance par muscle group

### 20. 🎨 Branding & Polish

- [x] Changer favicon/logo onglet web (favicon.png)
- [ ] Splash screen au chargement ?
- [ ] Animations de transition entre pages

---

## 📊 Priority Order

1. ~~Data Formatting~~ ✅
2. ~~Strength Module~~ ✅
3. ~~RAG Enrichment~~ ✅
4. ~~UI/UX Frontend~~ ✅
5. ~~Garmin Sync~~ ✅
6. ~~Exercise Knowledge Base~~ ✅
7. ~~RAG Response Refactor~~ ✅
8. ~~UI Polish & Font Fixes~~ ✅
9. ~~Settings Persistence~~ ✅
10. ~~Strength Session Parser~~ ✅
11. **UI Fonctionnalités** (Quest Log, Matrix)
12. **Import Séances Muscu avancé** (repos, range reps, failure)
13. **Heatmap Integration Complete** (cardio impact)
14. **Programmation & Objectifs**
15. **HUD Enhancements** (VO2max, volume running, heures/sport)
16. **Gestion PRs** (UI dédiée)
17. **Gestion Exercices** (ajout manuel, fusion)
18. **Heatmap Période** (sélecteur 7j/30j/90j)
19. **Branding & Polish**

---

## 🔗 Related Files

- `prompt_front.txt` - Frontend specs
- `STATUS.md` - Project status
- `README.md` - Documentation
