# Design: Strava API Integration

**Date**: 2026-05-12
**Status**: Approved

## Context

Arete currently imports cardio activities via Garmin Connect sync and FIT file upload.
Strava replaces Garmin Connect as the primary sync source. FIT upload remains as a bonus.

The existing `actual_sessions` table is source-agnostic — `ActivitySource.STRAVA = "strava"`
already exists in the codebase, and the Settings UI has a placeholder Strava card.

## Constraints

- Single-user app (user_id=1, no multi-tenant)
- Localhost only — OAuth callback on `localhost:8000`
- Manual sync (button press), no webhooks or cron
- Import all activity types (Run, Ride, Swim, Hike, etc.)
- No new heavy dependencies — use `httpx` (already available)

## Architecture

```
Settings UI (STRAVA tab)
  → "Connect Strava" → GET /strava/authorize → redirect to Strava OAuth
  → Strava callback  → GET /strava/callback?code=... → token exchange → DB
  → "Sync" button    → POST /strava/sync → fetch activities → actual_sessions
  → "Disconnect"     → DELETE /strava/disconnect → purge tokens
```

### New files

| File | Purpose |
|------|---------|
| `src/arete/strava/client.py` | OAuth flow + Strava API calls |
| `src/arete/strava/models.py` | Pydantic models, Strava → ActualSession mapping |
| `src/arete/api/strava.py` | FastAPI router: authorize, callback, sync, status, disconnect |

### API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/strava/authorize` | Returns Strava OAuth URL for redirect |
| GET | `/strava/callback` | Receives OAuth code, exchanges for tokens, stores in DB |
| POST | `/strava/sync` | Fetches recent activities, inserts into actual_sessions |
| GET | `/strava/status` | Returns connection status + athlete info |
| DELETE | `/strava/disconnect` | Deletes stored tokens |

## Token Storage

DB table (not JSON file) — backed up with the database, no filesystem concerns:

```sql
CREATE TABLE IF NOT EXISTS app.strava_tokens (
    user_id         INTEGER PRIMARY KEY DEFAULT 1,
    athlete_id      INTEGER,
    access_token    VARCHAR NOT NULL,
    refresh_token   VARCHAR NOT NULL,
    expires_at      INTEGER NOT NULL,   -- Unix timestamp
    athlete_name    VARCHAR,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Auto-refresh: before each API call, if `expires_at - 300 < now()`, refresh the token
using the `refresh_token` grant. Strava issues a new refresh_token on each refresh —
must persist immediately.

## Strava → actual_sessions Mapping

| Strava API field | actual_sessions column | Notes |
|-----------------|----------------------|-------|
| `start_date_local` | `date` | Date part only |
| `type` / `sport_type` | `sport` | Lowercase: 'run', 'ride', etc. |
| `elapsed_time` | `duration_sec` | |
| `distance` | `distance_m` | Already in meters |
| `average_heartrate` | `avg_hr` | |
| `max_heartrate` | `max_hr` | |
| `average_speed` | `avg_speed_mps` | |
| `max_speed` | `max_speed_mps` | |
| `total_elevation_gain` | `ascent_m` | |
| `start_latlng[0]` | `start_lat` | |
| `start_latlng[1]` | `start_lon` | |
| `calories` | `calories` | |
| `average_cadence` | `avg_cadence` | ×2 for running (Strava reports half) |
| `id` (string) | `garmin_activity_id` | Reuse existing VARCHAR column |
| `start_date` | `start_time` | Full ISO timestamp |
| — | `source` | `'strava'` |

Deduplication: check `garmin_activity_id` + `source = 'strava'` before insert.

Pace computation: `avg_pace_sec_km = 1000 / avg_speed_mps` (computed, not from API).

## Frontend

Settings.tsx STRAVA tab (placeholder already exists):
- **Disconnected**: "Connect Strava" button (orange, Strava brand color #FC4C02)
- **Connected**: athlete name, last sync date, "Sync Now" button, "Disconnect" button
- Sync button shows activity count after import

## Environment Variables

```
STRAVA_CLIENT_ID=<from strava.com/settings/api>
STRAVA_CLIENT_SECRET=<from strava.com/settings/api>
STRAVA_REDIRECT_URI=http://localhost:8000/strava/callback
```

Added to `.env`, gitignored. Callback domain in Strava app settings: `localhost`.

## What's NOT in scope

- Webhook push (requires public domain)
- Automatic background sync (cron)
- Multi-user Strava credentials
- Activity detail streams (GPS points, laps) — summary only
- Removing existing Garmin code (kept but secondary)
