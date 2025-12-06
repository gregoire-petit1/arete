# TODO - Arete Development

_Last updated: 6 December 2025_

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

---

## 📋 Next Up

### 8. 🎨 UI Polish & Font Fixes

**Goal**: Uniformiser les polices et corriger les détails visuels

#### Polices à passer en Inter (titres/labels) :

- [ ] **HUD** : texte sous SYSTEM SAYS, sous SUGGESTED ACTIONS
- [ ] **Quest Log** : sous ADHERENCE DASHBOARD (completion rate, this week, days streak)
- [ ] **The Forge** :
  - Sous WEEKLY VOLUME TRACKER (total volume, total sets, avg rpe, % of weekly target)
  - Sous NO SESSIONS YET ("start forging your strength")
  - Onglet PR : tous les Est 1RM, les dates
- [ ] **Neural Link** : corps des réponses système
- [ ] **Matrix** (+ supprimer les emojis) :
  - Sous SYSTEM STATUS (API Health, DuckDB, ChromaDB, Garmin Connect)
  - Sous GARMIN SYNC CENTER (Last sync, Activities synced)
  - Sous DRAG & DROP ("or click to browse")
- [ ] **Settings** : descriptions sous les goals, "System will warn when fatigue exceeds this level"

#### Autres corrections :

- [ ] Alignement barre XP (doit arriver au même niveau que les éléments au-dessus)
- [ ] Titre onglet navigateur : "frontend" → "Arete"

### 9. 🔧 Fonctionnalités à implémenter

**Goal**: Rendre fonctionnels les éléments UI actuellement non-fonctionnels

- [ ] **Settings** : sauvegarde des changements (display name, thème, goals)
- [ ] **Quest Log** : bouton NEW QUEST, bouton VIEW dans RECENT QUESTS
- [ ] **The Forge** : bouton NEW SESSION (clarifier différence avec NEW QUEST)
- [ ] **Matrix** : bouton Refresh

### 10. 🔄 Training Session Parser

**Goal**: Parse user training notes into structured sessions

- [ ] Parse training notation (e.g., "3x10 bp db 30kg r90")
- [ ] Match exercises to catalog (aliases: bp → bench_press)
- [ ] Calculate session volume and store in DuckDB
- [ ] Connect to muscle heatmap visualization

### 11. 📊 Enhanced Analytics

- [ ] Weekly/monthly volume trends by muscle group
- [ ] PR tracking with progression charts
- [ ] Recovery recommendations based on muscle fatigue
- [ ] Integration of cardio + strength load for ACWR

### 12. 🎯 Goal Tracking

- [ ] Define user goals (5K sub-20, bench 140kg 1RM, marathon)
- [ ] Progress tracking towards goals
- [ ] AI-generated training blocks to reach goals

### 13. 🏋️ Import Séances Muscu

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
8. **UI Polish & Font Fixes** (next)
9. **Fonctionnalités à implémenter**
10. **Training Session Parser**
11. **Enhanced Analytics**
12. **Goal Tracking**
13. **Import Séances Muscu**

---

## 🔗 Related Files

- `prompt_front.txt` - Frontend specs
- `STATUS.md` - Project status
- `README.md` - Documentation
