# TODO - Arete Development

_Last updated: 7 December 2025_

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

---

## 📋 Next Up

### 11. 🔧 Fonctionnalités à implémenter

**Goal**: Rendre fonctionnels les éléments UI actuellement non-fonctionnels

- [ ] **Quest Log** : bouton NEW QUEST, bouton VIEW dans RECENT QUESTS
- [ ] **The Forge** : bouton NEW SESSION (clarifier différence avec NEW QUEST)
- [ ] **Matrix** : bouton Refresh

### 12. 🔄 Training Session Parser

**Goal**: Parse user training notes into structured sessions

- [ ] Parse training notation (e.g., "3x10 bp db 30kg r90")
- [ ] Match exercises to catalog (aliases: bp → bench_press)
- [ ] Calculate session volume and store in DuckDB
- [ ] Connect to muscle heatmap visualization

### 13. 📊 Enhanced Analytics

- [ ] Weekly/monthly volume trends by muscle group
- [ ] PR tracking with progression charts
- [ ] Recovery recommendations based on muscle fatigue
- [ ] Integration of cardio + strength load for ACWR

### 14. 🎯 Goal Tracking

- [ ] Define user goals (5K sub-20, bench 140kg 1RM, marathon)
- [ ] Progress tracking towards goals
- [ ] AI-generated training blocks to reach goals

### 15. 🏋️ Import Séances Muscu

- [ ] Format d'import à définir (CSV, JSON, formulaire)
- [ ] Parsing et validation des données
- [ ] Intégration avec le calendrier (Matrix)

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
10. **Fonctionnalités à implémenter** (next)
11. **Training Session Parser**
12. **Enhanced Analytics**
13. **Goal Tracking**
14. **Import Séances Muscu**

---

## 🔗 Related Files

- `prompt_front.txt` - Frontend specs
- `STATUS.md` - Project status
- `README.md` - Documentation
