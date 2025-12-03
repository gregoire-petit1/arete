# TODO - Arete Development

*Last updated: 3 December 2025*

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

---

## 📋 Next Up

### 5. 🎨 UI/UX Improvements
**Reference**: `prompt_front.txt`

- [ ] Review and implement UI specs
- [ ] Dashboard enhancements
- [ ] Activity visualization

### 6. 🔄 Garmin Connect Sync
**Goal**: Auto-sync via `garth` library

- [ ] OAuth with Garmin Connect
- [ ] Auto-download activities
- [ ] Runalyze backup integration

---

## 📊 Priority Order
1. ~~Data Formatting~~ ✅
2. ~~Strength Module~~ ✅
3. ~~RAG Enrichment~~ ✅
4. **UI/UX** (frontend work)
5. **Garmin Sync** (nice to have)

---

## 🔗 Related Files
- `prompt_front.txt` - Frontend specs
- `STATUS.md` - Project status
- `README.md` - Documentation

## 🔗 Related Files
- `prompt_front.txt` - Frontend specs
- `STATUS.md` - Project status
- `README.md` - Documentation
