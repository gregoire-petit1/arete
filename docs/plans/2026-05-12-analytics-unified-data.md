# Analytics & Unified Data Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Unify data architecture around `actual_sessions`, enrich Strava sync with detail data, migrate Dashboard metrics, and build a new Analytics page with 6 charts.

**Architecture:** `actual_sessions` becomes the single source of truth. Strava detail endpoint provides laps/splits/PRs. Dashboard metrics read from `actual_sessions`. New Analytics page with Recharts (already installed).

**Tech Stack:** Python/FastAPI (backend), DuckDB, React/TypeScript + Recharts (frontend), Strava API v3

---

### Task 1: Add new columns to `actual_sessions`

**Files:**
- Modify: `src/arete/dataio/init_duckdb.py` (DDL + `_run_migrations()`)

**Step 1: Add columns to DDL**

In the `CREATE TABLE IF NOT EXISTS app.actual_sessions` DDL, add these columns before the closing `)`:

```sql
name VARCHAR,
notes TEXT,
rpe INTEGER,
workout_type VARCHAR,
moving_time_sec INTEGER,
suffer_score INTEGER,
laps_json TEXT,
splits_json TEXT,
best_efforts_json TEXT,
avg_watts INTEGER,
weighted_avg_watts INTEGER,
device_name VARCHAR,
```

**Step 2: Add migration in `_run_migrations()`**

Add a new migration block after the existing `exercise_abbreviations` migration:

```python
# Migration: add analytics columns to actual_sessions
_analytics_cols = {
    "name": "VARCHAR",
    "notes": "TEXT",
    "rpe": "INTEGER",
    "workout_type": "VARCHAR",
    "moving_time_sec": "INTEGER",
    "suffer_score": "INTEGER",
    "laps_json": "TEXT",
    "splits_json": "TEXT",
    "best_efforts_json": "TEXT",
    "avg_watts": "INTEGER",
    "weighted_avg_watts": "INTEGER",
    "device_name": "VARCHAR",
}
for col_name, col_type in _analytics_cols.items():
    try:
        conn.execute(
            f"ALTER TABLE app.actual_sessions ADD COLUMN {col_name} {col_type}"
        )
        logger.info("Added column %s to actual_sessions", col_name)
    except Exception:
        pass  # Column already exists
```

**Step 3: Run and verify**

Run: `uv run python -c "from arete.dataio.init_duckdb import get_connection; c = get_connection(); print([r[0] for r in c.execute('PRAGMA table_info(\"app\".\"actual_sessions\")').fetchall()])"`

Expected: All new column names appear in the output.

**Step 4: Commit**

```bash
git add src/arete/dataio/init_duckdb.py
git commit -m "feat: add analytics columns to actual_sessions schema"
```

---

### Task 2: Enrich Strava client with detail fetch

**Files:**
- Modify: `src/arete/strava/client.py` (~line 78)
- Test: `tests/test_strava_client.py`

**Step 1: Write the failing test**

Add to `tests/test_strava_client.py`:

```python
class TestFetchActivityDetail:
    @responses.activate
    def test_fetches_detail_with_all_fields(self):
        detail = {
            "id": 123,
            "name": "Morning Run",
            "description": "Easy recovery",
            "calories": 450,
            "device_name": "Garmin FR 265",
            "laps": [{"elapsed_time": 300, "distance": 1000}],
            "splits_metric": [{"average_speed": 3.5, "distance": 1000}],
            "best_efforts": [{"name": "1k", "elapsed_time": 240}],
            "suffer_score": 78,
            "workout_type": 1,
            "average_watts": None,
            "weighted_average_watts": None,
        }
        responses.add(
            responses.GET,
            "https://www.strava.com/api/v3/activities/123",
            json=detail,
            status=200,
        )
        client = StravaClient(client_id="id", client_secret="secret", redirect_uri="http://cb")
        result = client.fetch_activity_detail("token123", 123)
        assert result["name"] == "Morning Run"
        assert result["description"] == "Easy recovery"
        assert result["laps"] == detail["laps"]

    @responses.activate
    def test_detail_returns_none_on_404(self):
        responses.add(
            responses.GET,
            "https://www.strava.com/api/v3/activities/999",
            status=404,
        )
        client = StravaClient(client_id="id", client_secret="secret", redirect_uri="http://cb")
        result = client.fetch_activity_detail("token123", 999)
        assert result is None
```

**Step 2: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_strava_client.py::TestFetchActivityDetail -v`
Expected: FAIL — `fetch_activity_detail` not defined

**Step 3: Implement `fetch_activity_detail`**

Add method to `StravaClient` class in `client.py`:

```python
def fetch_activity_detail(
    self, access_token: str, activity_id: int
) -> dict | None:
    """Fetch detailed data for a single activity (laps, splits, best_efforts)."""
    resp = httpx.get(
        f"{self.BASE_URL}/activities/{activity_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json()
```

**Step 4: Run tests to verify they pass**

Run: `uv run python -m pytest tests/test_strava_client.py -v`
Expected: All pass (existing 12 + 2 new)

**Step 5: Commit**

```bash
git add src/arete/strava/client.py tests/test_strava_client.py
git commit -m "feat: add fetch_activity_detail to StravaClient"
```

---

### Task 3: Enrich Strava model mapping

**Files:**
- Modify: `src/arete/strava/models.py`
- Modify: `src/arete/garmin/models.py` (add fields to `ActualSession` dataclass)
- Test: `tests/test_strava_models.py`

**Step 1: Add new fields to `ActualSession` dataclass**

In `src/arete/garmin/models.py`, add to `ActualSession`:

```python
name: str | None = None
notes: str | None = None
rpe: int | None = None
workout_type: str | None = None
moving_time_sec: int | None = None
suffer_score: int | None = None
laps_json: str | None = None
splits_json: str | None = None
best_efforts_json: str | None = None
avg_watts: int | None = None
weighted_avg_watts: int | None = None
device_name: str | None = None
```

**Step 2: Write failing tests**

Add to `tests/test_strava_models.py`:

```python
def test_maps_detail_fields():
    activity = {
        "id": 1, "type": "Run", "start_date_local": "2026-05-10T07:30:00",
        "elapsed_time": 3600, "distance": 10000,
        "name": "Morning Run",
        "description": "Easy jog in the park",
        "moving_time": 3400,
        "suffer_score": 78,
        "workout_type": 3,
        "calories": 450,
        "device_name": "Garmin FR 265",
        "average_watts": None,
        "weighted_average_watts": None,
        "laps": [{"elapsed_time": 300}],
        "splits_metric": [{"distance": 1000, "average_speed": 2.78}],
        "best_efforts": [{"name": "1k", "elapsed_time": 240}],
    }
    session = strava_activity_to_actual_session(activity)
    assert session.name == "Morning Run"
    assert session.notes == "Easy jog in the park"
    assert session.moving_time_sec == 3400
    assert session.suffer_score == 78
    assert session.device_name == "Garmin FR 265"
    assert '"elapsed_time": 300' in session.laps_json
    assert '"distance": 1000' in session.splits_json
    assert '"name": "1k"' in session.best_efforts_json


def test_maps_cycling_watts():
    activity = {
        "id": 2, "type": "Ride", "start_date_local": "2026-05-10T07:30:00",
        "elapsed_time": 3600, "distance": 30000,
        "average_watts": 200, "weighted_average_watts": 210,
    }
    session = strava_activity_to_actual_session(activity)
    assert session.avg_watts == 200
    assert session.weighted_avg_watts == 210
```

**Step 3: Run tests to verify they fail**

Run: `uv run python -m pytest tests/test_strava_models.py::test_maps_detail_fields tests/test_strava_models.py::test_maps_cycling_watts -v`

**Step 4: Update mapping function**

In `strava_activity_to_actual_session()`, add mappings:

```python
import json

# Detail fields
name=activity.get("name"),
notes=activity.get("description"),
moving_time_sec=activity.get("moving_time"),
suffer_score=activity.get("suffer_score"),
workout_type=str(activity["workout_type"]) if activity.get("workout_type") is not None else None,
device_name=activity.get("device_name"),
avg_watts=int(activity["average_watts"]) if activity.get("average_watts") else None,
weighted_avg_watts=int(activity["weighted_average_watts"]) if activity.get("weighted_average_watts") else None,
laps_json=json.dumps(activity["laps"]) if activity.get("laps") else None,
splits_json=json.dumps(activity["splits_metric"]) if activity.get("splits_metric") else None,
best_efforts_json=json.dumps(activity["best_efforts"]) if activity.get("best_efforts") else None,
```

**Step 5: Run tests**

Run: `uv run python -m pytest tests/test_strava_models.py -v`
Expected: All pass

**Step 6: Commit**

```bash
git add src/arete/garmin/models.py src/arete/strava/models.py tests/test_strava_models.py
git commit -m "feat: enrich ActualSession with detail fields from Strava"
```

---

### Task 4: Update Strava sync to fetch details + update repository

**Files:**
- Modify: `src/arete/api/strava.py` (sync endpoint, ~line 158)
- Modify: `src/arete/garmin/repository.py` (`create_actual_session` INSERT)
- Test: `tests/test_strava_integration.py`

**Step 1: Update repository INSERT**

In `src/arete/garmin/repository.py`, find the `create_actual_session` method's INSERT statement. Add the 12 new columns to the INSERT (columns list + VALUES placeholders + corresponding values from the ActualSession object).

**Step 2: Update sync endpoint**

In `src/arete/api/strava.py` `sync()` function (~line 158), after getting the activity list, for each new activity (not already in DB):

```python
# Fetch detail for each new activity
detail = client.fetch_activity_detail(access_token, activity["id"])
if detail:
    # Merge detail into summary (detail has all summary fields + extra)
    activity_data = detail
else:
    activity_data = activity

session = strava_activity_to_actual_session(activity_data)
```

Add rate limiting between detail calls:

```python
import time

# Strava rate limit: 100 requests per 15 minutes
if idx > 0 and idx % 95 == 0:
    logger.info("Approaching rate limit, pausing 60s...")
    time.sleep(60)
```

**Step 3: Add/update integration test**

Update `tests/test_strava_integration.py` to verify detail fields are populated in the imported session.

**Step 4: Run all Strava tests**

Run: `uv run python -m pytest tests/test_strava_*.py -v`
Expected: All pass

**Step 5: Commit**

```bash
git add src/arete/api/strava.py src/arete/garmin/repository.py tests/test_strava_integration.py
git commit -m "feat: fetch Strava detail data during sync"
```

---

### Task 5: Migrate metrics to read `actual_sessions`

**Files:**
- Modify: `src/arete/api/metrics.py` (lines 172-324)
- Test: `tests/test_metrics.py` (existing tests must still pass)

**Step 1: Rewrite `_get_tss_history()` (line 216)**

Replace the `training_log` query with an `actual_sessions` query. TSS calculation priority:
1. If `rpe` is set: `(duration_sec/60) * (rpe/10)^2 / 0.36`
2. If `suffer_score` is set: `suffer_score * 0.8` (approximate mapping)
3. Fallback: HR-based estimate `(duration_sec/60) * (avg_hr/180)^2 / 0.36`
4. Last resort: `(duration_sec/60) * 0.25 / 0.36` (assume RPE 5)

```sql
SELECT date,
       SUM(
         CASE
           WHEN rpe IS NOT NULL THEN
             (COALESCE(duration_sec, 0) / 60.0) * POWER(rpe / 10.0, 2) / 0.36
           WHEN suffer_score IS NOT NULL THEN
             suffer_score * 0.8
           WHEN avg_hr IS NOT NULL THEN
             (COALESCE(duration_sec, 0) / 60.0) * POWER(avg_hr / 180.0, 2) / 0.36
           ELSE
             (COALESCE(duration_sec, 0) / 60.0) * 0.25 / 0.36
         END
       ) as daily_tss
FROM app.actual_sessions
WHERE date >= ? AND date <= ?
  AND user_id = 1
GROUP BY date
ORDER BY date ASC
```

**Step 2: Rewrite `_get_training_loads()` (line 172)**

```sql
SELECT date,
       SUM(COALESCE(duration_sec, 0)) / 60.0 as total_duration,
       AVG(COALESCE(rpe, 5)) as avg_rpe
FROM app.actual_sessions
WHERE date >= ? AND date <= ?
  AND user_id = 1
GROUP BY date
ORDER BY date ASC
```

**Step 3: Rewrite `_compute_weekly_tss()` (line 273)**

Same TSS formula as Step 1 but for a date range, reading from `actual_sessions`.

**Step 4: Rewrite `_compute_level()` (line 294)**

```sql
SELECT MIN(date) FROM app.actual_sessions WHERE user_id = 1
```

Then count consecutive weeks with at least one session.

**Step 5: Run existing tests**

Run: `uv run python -m pytest tests/ -v -k metrics`
Expected: Tests may need updating if they mock `training_log` queries. Update mocks to match new queries.

**Step 6: Commit**

```bash
git add src/arete/api/metrics.py tests/
git commit -m "feat: migrate metrics to read actual_sessions instead of training_log"
```

---

### Task 6: Backend analytics endpoints

**Files:**
- Create: `src/arete/api/analytics.py`
- Modify: `src/arete/api/main.py` (register router)
- Test: `tests/test_analytics.py`

**Endpoints needed:**

1. `GET /analytics/volume?period=30d&sport=all` — weekly volume (hours + km)
2. `GET /analytics/training-load?period=90d` — daily CTL/ATL/TSB
3. `GET /analytics/pace?period=90d&sport=running` — pace per activity over time
4. `GET /analytics/hr-zones?period=30d` — time in HR zones per week
5. `GET /analytics/sport-distribution?period=90d` — hours by sport
6. `GET /analytics/best-efforts?sport=running` — PRs extracted from best_efforts_json

**Step 1: Write failing tests for each endpoint** (6 test functions minimum)

**Step 2: Implement `src/arete/api/analytics.py`**

Each endpoint queries `actual_sessions` with appropriate aggregation.

Key SQL patterns:
- Volume: `GROUP BY DATE_TRUNC('week', date), sport`
- Training load: reuse `_get_tss_history()` + `compute_performance_model()`
- Pace: `SELECT date, avg_pace_sec_km FROM actual_sessions WHERE sport = 'running'`
- HR zones: `SELECT hr_zones_json FROM actual_sessions WHERE hr_zones_json IS NOT NULL`
- Distribution: `SELECT sport, SUM(duration_sec) FROM actual_sessions GROUP BY sport`
- Best efforts: `SELECT best_efforts_json FROM actual_sessions WHERE best_efforts_json IS NOT NULL`

**Step 3: Register router in `main.py`**

```python
from arete.api.analytics import router as analytics_router
app.include_router(analytics_router)
```

**Step 4: Run tests**

Run: `uv run python -m pytest tests/test_analytics.py -v`

**Step 5: Commit**

```bash
git add src/arete/api/analytics.py src/arete/api/main.py tests/test_analytics.py
git commit -m "feat: add analytics API endpoints"
```

---

### Task 7: Frontend — Add Analytics page route + navigation

**Files:**
- Create: `frontend/src/pages/Analytics.tsx`
- Modify: `frontend/src/App.tsx` (add route, line ~31)
- Modify: `frontend/src/components/Navigation.tsx` or equivalent (add nav item)
- Modify: `frontend/src/lib/api.ts` (add `analyticsApi`)

**Step 1: Add API client**

In `api.ts`, add:

```typescript
export const analyticsApi = {
  getVolume: (period = '30d', sport = 'all') =>
    fetchAPI(`/analytics/volume?period=${period}&sport=${sport}`),
  getTrainingLoad: (period = '90d') =>
    fetchAPI(`/analytics/training-load?period=${period}`),
  getPace: (period = '90d', sport = 'running') =>
    fetchAPI(`/analytics/pace?period=${period}&sport=${sport}`),
  getHrZones: (period = '30d') =>
    fetchAPI(`/analytics/hr-zones?period=${period}`),
  getSportDistribution: (period = '90d') =>
    fetchAPI(`/analytics/sport-distribution?period=${period}`),
  getBestEfforts: (sport = 'running') =>
    fetchAPI(`/analytics/best-efforts?sport=${sport}`),
};
```

**Step 2: Create Analytics page skeleton**

`frontend/src/pages/Analytics.tsx` — Period selector + sport filter + 6 chart placeholders using Recharts.

**Step 3: Add route**

In `App.tsx` line ~34, add:

```tsx
<Route path="/analytics" element={<AnalyticsPage />} />
```

**Step 4: Add navigation item**

Add "Analytics" link with BarChart3 icon from lucide-react.

**Step 5: Commit**

```bash
git add frontend/src/pages/Analytics.tsx frontend/src/App.tsx frontend/src/lib/api.ts frontend/src/components/
git commit -m "feat: add Analytics page with route and navigation"
```

---

### Task 8: Frontend — Implement 6 charts

**Files:**
- Modify: `frontend/src/pages/Analytics.tsx`

**Charts to implement (one at a time):**

1. **VolumeChart** — `BarChart` stacked by sport. X = week, Y = hours. Secondary Y = km.
2. **TrainingLoadChart** — `LineChart` with 3 lines: CTL (blue), ATL (red), TSB (green).
3. **PaceChart** — `ScatterChart` + trend `Line`. X = date, Y = pace (min/km).
4. **HrZonesChart** — `BarChart` stacked. X = week, Y = minutes. 5 zones (Z1-Z5) with standard colors.
5. **SportDistributionChart** — `PieChart` / donut. Segments = sports, sized by hours.
6. **BestEffortsTable** — Not a Recharts chart. HTML table with sparkline `LineChart` inline.

Each chart is a separate React component. All use the dark theme colors from the app.

**Step by step: implement one chart, verify it renders, commit, next chart.**

**Commit after each chart or after all 6:**

```bash
git add frontend/src/pages/Analytics.tsx
git commit -m "feat: implement analytics charts (volume, load, pace, HR zones, sports, PRs)"
```

---

### Task 9: Log page — Add RPE + notes editing for sessions

**Files:**
- Modify: `frontend/src/pages/Log.tsx`
- Modify: `src/arete/api/routes.py` or create endpoint for updating session RPE/notes
- Test: `tests/test_session_update.py`

**Step 1: Backend — Add `PATCH /sessions/{id}` endpoint**

Accept `{ rpe: int | null, notes: str | null }`. Update `actual_sessions` row.

**Step 2: Frontend — Add edit UI**

On the Log page, when viewing a session (imported from Strava), show:
- RPE slider (1-10)
- Notes textarea
- Save button

Strava metrics (pace, HR, distance) displayed read-only.

**Step 3: Commit**

```bash
git commit -m "feat: add RPE and notes editing for sessions on Log page"
```

---

### Task 10: Rebuild, E2E test, push

**Step 1: Re-sync Strava** (will now fetch detail data for new activities)

**Step 2: Rebuild Docker**

```bash
docker compose build --no-cache backend frontend
docker compose up -d --force-recreate
```

**Step 3: Verify**
- Dashboard shows updated HP/MP/XP from `actual_sessions`
- Analytics page loads with charts
- Log page shows sessions with RPE/notes editing
- Strava sync fetches detail data

**Step 4: Push**

```bash
git push origin main
git push forgejo main
```
