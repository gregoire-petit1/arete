# TODO - Arete Development

*Last updated: 3 December 2025*

## 📋 Today's Session

### 1. ✅ LLM Analysis Enhancement (DONE)
- [x] Basic activity analysis
- [x] Detailed time series analysis
- [x] Lap-based interval workout detection
- [ ] **Future**: Chart/visual analysis when available

---

### 2. 🔧 Data Formatting Fixes
**Issue**: `duration_min` and `distance_km` display ugly floats
```json
"duration_min": 43.416666666666664,
"distance_km": 6.686229999999999
```
**Solution**: Round to 1-2 decimals in API responses

**Files to update**:
- [ ] `src/arete/api/garmin.py` - Response models
- [ ] `src/arete/garmin/models.py` - `ActualSession` properties

---

### 3. 🏋️ Strength Training Module
**Goal**: Record strength sessions with structured data

**Data to capture**:
- Exercise name
- Sets × Reps
- Load (kg)
- RPE (1-10)
- Rest time
- Notes

**Implementation**:
- [ ] Create `src/arete/strength/models.py`
- [ ] Create `src/arete/strength/repository.py`
- [ ] Add DB tables in `init_duckdb.py`
- [ ] Create API endpoints `/strength/*`

---

### 4. 🧠 RAG Enrichment
**Goal**: Personalize analysis with user benchmarks

**Data sources to add**:
- [ ] Personal benchmarks (cadence EF, vertical osc baseline)
- [ ] Reference patterns ("HR drift >10% = glycogen depletion")
- [ ] Historical analysis trends

**Implementation**:
- [ ] Create user profile with physiological baselines
- [ ] Add pattern library to RAG collection
- [ ] Track analysis history for trend detection

---

### 5. 🎨 UI/UX Improvements
**Reference**: `prompt_front.txt`

- [ ] Review and implement UI specs
- [ ] Dashboard enhancements
- [ ] Activity visualization

---

### 6. 🔄 Phase 2 (Optional) - Garmin Connect Sync
**Goal**: Auto-sync via `garth` library

**Features**:
- [ ] OAuth with Garmin Connect
- [ ] Auto-download activities
- [ ] Runalyze backup integration

---

## 📊 Priority Order
1. **Data Formatting** (quick win)
2. **Strength Module** (new feature)
3. **RAG Enrichment** (improves analysis quality)
4. **UI/UX** (frontend work)
5. **Garmin Sync** (nice to have)

---

## 🔗 Related Files
- `prompt_front.txt` - Frontend specs
- `STATUS.md` - Project status
- `README.md` - Documentation
