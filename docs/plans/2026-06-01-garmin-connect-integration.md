# Garmin Connect Integration — Phase 2 Plan

**Status:** Planned
**Date:** 2026-06-01
**Goal:** Pull daily physiological metrics from Garmin Connect (Epix Pro Gen 2 47mm) into Arete for readiness scoring and TMB plan adaptation.

---

## 1. Why this matters

The Strava MCP official would give us "readiness" as a subscription feature, but it's incompatible with OpenCode (Strava MCP doesn't follow the standard MCP OAuth spec — only works with Claude.ai/Code).

**Garmin Connect is the goldmine.** The Epix Pro Gen 2 47mm tracks overnight:

| Metric | Storage | Use for TMB plan |
|---|---|---|
| **HRV (overnight)** | `daily_metrics.hrv_rmssd_ms` | PRIMARY readiness signal |
| **Sleep duration + stages** | `daily_metrics.sleep_total_min`, `sleep_deep_min`, `sleep_rem_min`, `sleep_light_min`, `sleep_awake_min` | Recovery quality |
| **Body Battery** (0-100) | `daily_metrics.body_battery_charged`, `body_battery_drained` | Energy reserve forecast |
| **Stress** (avg) | `daily_metrics.stress_avg` | Overtraining detection |
| **Resting HR** | `daily_metrics.resting_hr` | Fatigue marker |
| **SpO2** | `daily_metrics.spo2_pct` | Acclimatization (Chamonix altitude) |
| **Training Effect** | `daily_metrics.training_effect_aerobic`, `training_effect_anaerobic` | Per-session load |
| **Recovery time** (hours) | `daily_metrics.recovery_time_hr` | Plan adaptation |
| **VO2max** | `daily_metrics.vo2max` | Fitness trend |
| **HR during activity** | Already in `actual_sessions` via Strava | Backup if Strava down |

**Without these, we are flying blind on adaptation.** The TMB plan assumes certain recovery, but real-world readiness varies 20-30% day-to-day based on HRV, sleep, stress. Right now the plan is "set and forget" — with Garmin data it becomes "responsive."

---

## 2. Technical approach

### Library
`python-garminconnect` (unofficial but mature, MIT, ~1k stars on GitHub)
- Handles OAuth2 with MFA
- Returns JSON for all metrics
- Supports sessions export

### Auth flow
1. User runs `python -m arete.garmin.auth` locally
2. Opens browser, user logs in + enters MFA code
3. Tokens stored in `app.garmin_tokens` (similar to strava_tokens)
4. Tokens refresh automatically

### Sync flow
`POST /garmin/wellness/sync` — pulls last 7 days, upserts into `app.daily_metrics` (one row per day)

### Schema (new table)

```sql
CREATE TABLE app.daily_metrics (
  user_id INTEGER NOT NULL,
  date DATE NOT NULL,
  -- Sleep
  sleep_total_min INTEGER,
  sleep_deep_min INTEGER,
  sleep_rem_min INTEGER,
  sleep_light_min INTEGER,
  sleep_awake_min INTEGER,
  sleep_score SMALLINT,  -- 0-100 (Garmin score)
  -- HRV
  hrv_rmssd_ms INTEGER,
  hrv_status VARCHAR,  -- 'BALANCED' / 'UNBALANCED' / 'LOW'
  hrv_7day_avg INTEGER,
  -- Body Battery
  body_battery_charged SMALLINT,  -- 0-100, charged overnight
  body_battery_drained SMALLINT,  -- 0-100, drained during day
  body_battery_high SMALLINT,
  body_battery_low SMALLINT,
  -- Stress
  stress_avg SMALLINT,  -- 0-100
  stress_high_min INTEGER,  -- minutes in high stress
  -- Heart
  resting_hr SMALLINT,
  max_hr_day SMALLINT,
  -- Training
  training_effect_aerobic REAL,
  training_effect_anaerobic REAL,
  recovery_time_hr INTEGER,
  -- Fitness
  vo2max REAL,
  -- Respiratory
  spo2_pct REAL,
  respiration_avg_brpm REAL,
  -- Metadata
  source VARCHAR DEFAULT 'garmin',
  fetched_at TIMESTAMP,
  PRIMARY KEY (user_id, date)
);
```

---

## 3. Readiness Score (derived)

A simple model that combines HRV + sleep + Body Battery into a 0-100 score for the LLM coach to consume:

```python
def readiness_score(metrics: DailyMetrics) -> int:
    hrv_norm = min(100, metrics.hrv_rmssd_ms / 70 * 100)  # 70ms = 100
    sleep_norm = min(100, metrics.sleep_total_min / 480 * 100)  # 8h = 100
    bb_norm = metrics.body_battery_charged  # already 0-100
    rhr_penalty = max(0, (metrics.resting_hr - 50) * 2)  # 50bpm = 0, 65bpm = 30

    score = 0.4 * hrv_norm + 0.3 * sleep_norm + 0.3 * bb_norm - rhr_penalty
    return max(0, min(100, int(score)))
```

**Adaptation rules:**
- Score 80-100: plan is go, hard sessions allowed
- Score 60-79: easy sessions only
- Score 40-59: switch to recovery or rest
- Score 0-39: full rest, no running

**This is the killer feature for S17-S19** — replaces "set and forget" with responsive plan.

---

## 4. Implementation phases

### Phase 2.1 — Foundation (2-3h)
- Add `python-garminconnect` to pyproject
- Create `app.garmin_tokens` table
- Write `arete/garmin/auth.py` (CLI OAuth)
- Write `arete/garmin/wellness.py` (sync logic)
- Add `POST /garmin/wellness/sync` endpoint
- Test with Grégoire's data

### Phase 2.2 — Backfill (1h)
- Script to backfill last 90 days of HRV/sleep data
- Validate coverage

### Phase 2.3 — Readiness API (1h)
- Add `GET /analytics/readiness?days=14` endpoint
- Frontend card on Analytics page (line chart of score)
- LLM context: include readiness in `tip_post_session` and coach analysis

### Phase 2.4 — Auto-sync (1h)
- Daily cron at 06:00 → auto-sync previous day's metrics
- Or: sync runs on each session creation

---

## 5. Privacy & security

- Tokens stored in `app.garmin_tokens` with same access controls as Strava
- `daily_metrics` is sensitive (health data) — never log the full row
- No telemetry sent to Garmin (read-only operations)
- MFA on first auth, then refresh token = silent

---

## 6. Out of scope (for now)

- Garmin Coach plans (not needed, we have Arete coach)
- Live tracking / real-time HRV during activity
- Garmin Connect IQ apps integration
- Weight scale (separate `Index` device, different API)

---

## 7. Open questions

- Do we want a **sleep debt** indicator (7-day rolling sleep duration vs target)?
- Should readiness factor in **recent training load** (TSS last 7d)?
- How do we handle **altitude** impact (Chamonix 1000m+, high passes 2500m+)? Garmin tracks acclimatization but it's a separate API.

---

## 8. Decision log

| Decision | Rationale |
|---|---|
| Use `python-garminconnect` (unofficial) | No official Garmin API for Connect data; lib is mature, used by many |
| Daily 06:00 sync (vs hourly) | HRV is overnight — no need for intra-day refresh |
| Combine HRV+Sleep+BB into readiness | More robust than any single signal; aligns with WHOOP/oura approach |
| Read-only architecture | Garmin is the source of truth for physiological data; we just mirror it |

---

## 9. Estimated value

| Use case | Without Garmin | With Garmin |
|---|---|---|
| Adapt S17-S19 to real recovery | ❌ Set & forget | ✅ Daily adjustment |
| Predict TMB readiness Day 1-3 | ❌ Guess | ✅ 3-day forecast |
| Detect overtraining | ⚠️ Manual (HR, mood) | ✅ Automatic (HRV trend) |
| Plan adherence quality | ⚠️ Compare km | ✅ Compare expected vs actual load |
| Taper optimization (S20-S21) | ❌ Generic | ✅ Personalized to recovery |
