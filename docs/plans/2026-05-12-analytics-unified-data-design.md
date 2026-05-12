# Analytics & Unified Data Architecture — Design Doc

**Date:** 2026-05-12
**Status:** Approved

## Problem

Strava activities are imported into `actual_sessions` but the Dashboard reads only
`training_log` (a legacy subjective journal table). The two systems are completely
disconnected, so Strava imports have zero effect on displayed metrics.

Additionally, there are no performance analytics graphs — the app lacks the visual
training analysis that Strava provides.

## Decision

### 1. `actual_sessions` becomes the single source of truth

New columns added to `actual_sessions`:

| Column | Type | Source |
|--------|------|--------|
| `name` | VARCHAR | Strava activity title or manual |
| `notes` | TEXT | Manual input (Log page) |
| `rpe` | INTEGER (1-10) | Manual input |
| `workout_type` | VARCHAR | Strava or auto-detected |
| `moving_time_sec` | INTEGER | Strava (vs elapsed) |
| `suffer_score` | INTEGER | Strava relative effort |
| `laps_json` | TEXT | Strava detail endpoint |
| `splits_json` | TEXT | Strava detail (per km) |
| `best_efforts_json` | TEXT | Strava detail (PRs) |
| `avg_watts` | INTEGER | Strava (cycling/power) |
| `weighted_avg_watts` | INTEGER | Strava NP |
| `device_name` | VARCHAR | Strava detail |

`training_log` remains read-only for historical CSV data. All Dashboard metrics and
analytics read from `actual_sessions`.

### 2. Enriched Strava sync

**Current flow:** summary list → mapping → insert

**New flow:**
1. `GET /athlete/activities` (paginated summary) — get IDs
2. For each new activity: `GET /activities/{id}` (detail) — laps, splits, best_efforts,
   description, watts, device
3. Enriched mapping → insert with all new columns
4. Rate limiting: max 100 calls/15min (Strava limit), retry + backoff

**Initial sync:** 3 months of history. Then incremental from last known date.

### 3. New Analytics page (5 pages total)

Navigation: Dashboard, Planning, Log, **Analytics**, Settings

**Layout:** Period selector (7d/30d/90d/6m/1y/All) + sport filter on top.
Responsive grid of charts below.

**6 charts:**

| # | Chart | Type | Data |
|---|-------|------|------|
| 1 | Weekly volume | Stacked bar | Hours + km per week, colored by sport |
| 2 | Training load | Multi-axis line | CTL (fitness), ATL (fatigue), TSB (form) |
| 3 | Pace evolution | Line + trend | Avg pace per running activity over time |
| 4 | HR zones | Stacked bar / heatmap | % time in each zone per week |
| 5 | Sport distribution | Donut | Hours by sport over period |
| 6 | PRs & records | Table + sparklines | Best efforts (1km, 5km, 10km...) with date |

**Chart library:** Recharts (React, lightweight, responsive).

**Mobile:** Charts stack vertically (1 per row).

### 4. Dashboard migration

Dashboard HUD reads `actual_sessions` instead of `training_log`:

| Stat | New calculation |
|------|-----------------|
| HP (Readiness) | TSB from TSS-based performance model |
| MP (Fitness) | CTL from actual_sessions TSS |
| XP (Volume) | Weekly TSS sum from actual_sessions |
| Level | Consecutive weeks with activity streak |

**TSS estimation priority:**
1. RPE if provided → `duration_min × (RPE/10)² / 0.36`
2. Strava suffer_score → approximate mapping
3. HR-based TRIMP from avg_hr + duration

### 5. Log page enhancement

The Log page allows adding subjective data to Strava-imported activities:
- RPE (slider 1-10)
- Notes (free text — session structure, intervals, etc.)
- Strava metrics displayed read-only

## Data flow

```
Strava ──fetch detail──→ actual_sessions (source of truth)
                              ↑ enriched manually (RPE, notes)
                              │
                    ┌─────────┴──────────┐
                    │                    │
              Dashboard (HUD)      Analytics (6 charts)
              HP/MP/XP/Level       Volume, Load, Pace,
                                   HR Zones, Sports, PRs
```

## Non-goals

- Strava webhooks / automatic sync (manual button only)
- Deprecating `training_log` table (kept for CSV history)
- Real-time streaming of activities
