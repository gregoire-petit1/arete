# HR Zones & Cardiac Analytics — Design

**Date**: 2026-05-13
**Status**: Approved

## Context

All 71 Strava-synced sessions have `avg_hr` populated, but `hr_zones_json` is always NULL because we never call Strava's zones endpoint. The DDL, dataclass, and analytics endpoint for HR zones already exist but produce empty results.

User wants: (1) HR zone data from Strava, (2) cardiac efficiency tracking over time, (3) HR vs pace/elevation analysis.

## Volet 1: Strava HR Zones Import

### What
Call `GET /activities/{id}/zones` during sync to populate `hr_zones_json`.

### Strava API Response Format
```json
[
  {
    "type": "heartrate",
    "distribution_buckets": [
      {"min": 0, "max": 115, "time": 120},
      {"min": 115, "max": 152, "time": 600},
      {"min": 152, "max": 171, "time": 1200},
      {"min": 171, "max": 190, "time": 300},
      {"min": 190, "max": -1, "time": 60}
    ]
  }
]
```

### Storage Format
Normalize to: `{"z1": 120, "z2": 600, "z3": 1200, "z4": 300, "z5": 60}` (seconds per zone).

### Changes
- `StravaClient.fetch_activity_zones(activity_id)` — new method, `GET /activities/{id}/zones`
- `strava_activity_to_actual_session()` — accept optional zones data, map to `hr_zones_json`
- Sync flow — call zones endpoint alongside detail endpoint (same rate limit applies)
- Re-sync existing 71 sessions to backfill `hr_zones_json`

### Scope
- OAuth scope `activity:read_all` is sufficient (no scope change needed)
- 1 extra API call per activity during sync
- Rate limit: same 90-call/60s window applies

## Volet 2: Cardiac Analytics Charts

### New Endpoints

#### `GET /analytics/cardiac-efficiency?period=90d`
Returns weekly cardiac efficiency for runs.

Metric: `avg_hr / (1000 / avg_pace_sec_km)` = bpm per km/h. Lower = more efficient.

Response:
```json
{
  "data": [
    {"week": "2026-04-06", "efficiency": 28.5, "avg_hr": 165, "avg_pace": "5:30", "n_runs": 3},
    {"week": "2026-04-13", "efficiency": 27.2, "avg_hr": 162, "avg_pace": "5:25", "n_runs": 4}
  ]
}
```

SQL: Filter `sport IN ('run', 'running')`, `avg_hr IS NOT NULL`, `avg_pace_sec_km IS NOT NULL`. Group by week, compute weighted average efficiency.

#### `GET /analytics/hr-pace-scatter?period=90d`
Returns per-session data points for scatter plots.

Response:
```json
{
  "sessions": [
    {
      "date": "2026-04-15",
      "pace_sec_km": 330,
      "avg_hr": 168,
      "max_hr": 185,
      "elevation_gain": 120,
      "distance_km": 10.5,
      "name": "Morning Run",
      "sport": "run"
    }
  ]
}
```

SQL: Filter `sport IN ('run', 'running', 'walk', 'walking')`, `avg_hr IS NOT NULL`. Return raw session data for client-side scatter rendering.

### New Frontend Charts (in Analytics page)

#### Chart 1 — Cardiac Efficiency Trend (LineChart)
- X: week, Y: efficiency ratio
- Shows trend line of HR/speed ratio over time
- Secondary Y axis: avg_hr for context
- Lower = better (heart works less for same speed)

#### Chart 2 — HR vs Pace Scatter (ScatterChart)
- X: pace (min/km, reversed), Y: avg HR (bpm)
- Color: by month (gradient) or elevation bucket
- Tooltip: date, name, distance, elevation

#### Chart 3 — HR vs Elevation Scatter (ScatterChart)
- X: elevation gain (m), Y: avg HR (bpm)
- Size: distance_km (bigger bubble = longer run)
- Same data source as Chart 2 (no extra endpoint)

### Existing HR Zones Chart
Already functional — will auto-populate once Volet 1 backfills `hr_zones_json`.

## Implementation Order
1. Backend: `fetch_activity_zones()` in StravaClient + tests
2. Backend: Wire zones into sync flow + model mapping
3. Backend: 2 new analytics endpoints + tests
4. Frontend: 3 new chart components in Analytics.tsx
5. Re-sync Strava to backfill HR zones
6. Docker rebuild + verify

## Data Available
- 71 sessions, all with `avg_hr`
- ~27 runs with pace data
- Elevation data from Strava (`elevation_gain`)
- `avg_pace_sec_km` stored on actual_sessions
