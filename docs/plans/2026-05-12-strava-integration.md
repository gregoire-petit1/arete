# Strava Integration — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Connect Strava via OAuth2 and sync activities into the existing `actual_sessions` table.

**Architecture:** New `src/arete/strava/` module (client + models) + `src/arete/api/strava.py` router.
Tokens stored in DB table `app.strava_tokens`. Reuses `GarminRepository.create_actual_session()`
with `source=ActivitySource.STRAVA`. Frontend wires the existing Strava placeholder in Settings.

**Tech Stack:** FastAPI, httpx (sync), DuckDB, React/TypeScript

---

### Task 1: DB schema — strava_tokens table + migration

**Files:**
- Modify: `src/arete/dataio/init_duckdb.py`

**Step 1: Add strava_tokens DDL to the schema**

In `init_duckdb.py`, add after the `user_settings` table DDL:

```sql
CREATE TABLE IF NOT EXISTS app.strava_tokens (
    user_id         INTEGER PRIMARY KEY DEFAULT 1,
    athlete_id      INTEGER,
    access_token    VARCHAR NOT NULL,
    refresh_token   VARCHAR NOT NULL,
    expires_at      INTEGER NOT NULL,
    athlete_name    VARCHAR,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

No migration needed — `CREATE TABLE IF NOT EXISTS` handles both new and existing DBs.

**Step 2: Run tests to verify no regression**

Run: `uv run pytest tests/ -x -q`
Expected: 306 passed

**Step 3: Commit**

```bash
git add src/arete/dataio/init_duckdb.py
git commit -m "feat(strava): add strava_tokens table schema"
```

---

### Task 2: Strava client — OAuth + API

**Files:**
- Create: `src/arete/strava/__init__.py`
- Create: `src/arete/strava/client.py`
- Test: `tests/test_strava_client.py`

**Step 1: Create `src/arete/strava/__init__.py`**

Empty file.

**Step 2: Write tests for StravaClient**

```python
# tests/test_strava_client.py
"""Tests for Strava OAuth client."""
from __future__ import annotations
import time
from unittest.mock import patch, MagicMock
import pytest
from arete.strava.client import StravaClient


@pytest.fixture
def client():
    return StravaClient(
        client_id="test_id",
        client_secret="test_secret",
        redirect_uri="http://localhost:8000/strava/callback",
    )


class TestAuthorizeUrl:
    def test_contains_client_id(self, client):
        url = client.get_authorize_url()
        assert "client_id=test_id" in url

    def test_contains_redirect_uri(self, client):
        url = client.get_authorize_url()
        assert "redirect_uri=" in url

    def test_contains_scope(self, client):
        url = client.get_authorize_url()
        assert "activity:read_all" in url

    def test_contains_state(self, client):
        url = client.get_authorize_url(state="abc123")
        assert "state=abc123" in url


class TestTokenExchange:
    @patch("arete.strava.client.httpx.post")
    def test_exchange_code_returns_tokens(self, mock_post, client):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "access_token": "at_123",
                "refresh_token": "rt_456",
                "expires_at": 9999999999,
                "athlete": {"id": 42, "firstname": "Greg", "lastname": "P"},
            },
        )
        tokens = client.exchange_code("auth_code_xyz")
        assert tokens["access_token"] == "at_123"
        assert tokens["refresh_token"] == "rt_456"
        assert tokens["athlete"]["id"] == 42

    @patch("arete.strava.client.httpx.post")
    def test_exchange_code_raises_on_error(self, mock_post, client):
        mock_post.return_value = MagicMock(
            status_code=400,
            text="Bad Request",
            json=lambda: {"message": "Bad Request"},
        )
        with pytest.raises(ValueError):
            client.exchange_code("bad_code")


class TestTokenRefresh:
    @patch("arete.strava.client.httpx.post")
    def test_refresh_returns_new_tokens(self, mock_post, client):
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {
                "access_token": "new_at",
                "refresh_token": "new_rt",
                "expires_at": 9999999999,
            },
        )
        tokens = client.refresh_token("old_rt")
        assert tokens["access_token"] == "new_at"
        assert tokens["refresh_token"] == "new_rt"


class TestFetchActivities:
    @patch("arete.strava.client.httpx.get")
    def test_fetch_single_page(self, mock_get, client):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [
                {"id": 1, "name": "Morning Run", "type": "Run",
                 "start_date": "2026-05-10T08:00:00Z",
                 "distance": 10000, "moving_time": 3600,
                 "total_elevation_gain": 50},
            ],
        )
        activities = client.fetch_activities("at_123", after=0)
        assert len(activities) == 1
        assert activities[0]["id"] == 1

    @patch("arete.strava.client.httpx.get")
    def test_fetch_empty(self, mock_get, client):
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [],
        )
        activities = client.fetch_activities("at_123", after=0)
        assert activities == []


class TestNeedsRefresh:
    def test_expired_token(self, client):
        assert client.needs_refresh(int(time.time()) - 100) is True

    def test_valid_token(self, client):
        assert client.needs_refresh(int(time.time()) + 600) is False

    def test_within_margin(self, client):
        # Expires in 4 minutes — within 5-min margin
        assert client.needs_refresh(int(time.time()) + 240) is True
```

**Step 3: Run tests to verify they fail**

Run: `uv run pytest tests/test_strava_client.py -v`
Expected: ImportError (module not found)

**Step 4: Implement StravaClient**

```python
# src/arete/strava/client.py
"""Strava OAuth2 client and API wrapper."""
from __future__ import annotations

import logging
import time
from urllib.parse import urlencode

import httpx

logger = logging.getLogger(__name__)

STRAVA_AUTH_URL = "https://www.strava.com/oauth/authorize"
STRAVA_TOKEN_URL = "https://www.strava.com/oauth/token"
STRAVA_API_BASE = "https://www.strava.com/api/v3"

# Strava reports running cadence as half the actual value (per foot, not per step)
RUNNING_CADENCE_MULTIPLIER = 2
ACTIVITIES_PER_PAGE = 50


class StravaClient:
    """Handles Strava OAuth2 flow and activity fetching."""

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
    ) -> None:
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri

    # ── OAuth ─────────────────────────────────────────────

    def get_authorize_url(self, state: str | None = None) -> str:
        """Build the Strava OAuth authorization URL."""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "activity:read_all",
            "approval_prompt": "auto",
        }
        if state:
            params["state"] = state
        return f"{STRAVA_AUTH_URL}?{urlencode(params)}"

    def exchange_code(self, code: str) -> dict:
        """Exchange an authorization code for access + refresh tokens."""
        resp = httpx.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "code": code,
                "grant_type": "authorization_code",
            },
        )
        if resp.status_code != 200:
            logger.error("Strava token exchange failed: %s", resp.text)
            raise ValueError(f"Strava token exchange failed: {resp.text}")
        return resp.json()

    def refresh_token(self, refresh_tok: str) -> dict:
        """Refresh an expired access token."""
        resp = httpx.post(
            STRAVA_TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": refresh_tok,
            },
        )
        if resp.status_code != 200:
            logger.error("Strava token refresh failed: %s", resp.text)
            raise ValueError(f"Strava token refresh failed: {resp.text}")
        return resp.json()

    @staticmethod
    def needs_refresh(expires_at: int, margin_sec: int = 300) -> bool:
        """Check if the access token needs refreshing (5-min margin)."""
        return time.time() > expires_at - margin_sec

    # ── API ───────────────────────────────────────────────

    def fetch_activities(
        self,
        access_token: str,
        after: int | None = None,
        before: int | None = None,
    ) -> list[dict]:
        """Fetch all activities with pagination.

        Args:
            access_token: Valid Strava access token.
            after: Unix timestamp — only activities after this time.
            before: Unix timestamp — only activities before this time.

        Returns:
            List of raw Strava activity dicts.
        """
        headers = {"Authorization": f"Bearer {access_token}"}
        all_activities: list[dict] = []
        page = 1

        while True:
            params: dict = {"per_page": ACTIVITIES_PER_PAGE, "page": page}
            if after is not None:
                params["after"] = after
            if before is not None:
                params["before"] = before

            resp = httpx.get(
                f"{STRAVA_API_BASE}/athlete/activities",
                headers=headers,
                params=params,
            )
            if resp.status_code != 200:
                logger.error("Strava API error: %s %s", resp.status_code, resp.text)
                break

            batch = resp.json()
            if not batch:
                break

            all_activities.extend(batch)
            if len(batch) < ACTIVITIES_PER_PAGE:
                break
            page += 1

        logger.info("Fetched %d activities from Strava", len(all_activities))
        return all_activities
```

**Step 5: Run tests**

Run: `uv run pytest tests/test_strava_client.py -v`
Expected: all pass

**Step 6: Commit**

```bash
git add src/arete/strava/ tests/test_strava_client.py
git commit -m "feat(strava): OAuth client with token exchange, refresh, activity fetch"
```

---

### Task 3: Strava models — activity mapping to ActualSession

**Files:**
- Create: `src/arete/strava/models.py`
- Test: `tests/test_strava_models.py`

**Step 1: Write tests**

```python
# tests/test_strava_models.py
"""Tests for Strava → ActualSession mapping."""
from arete.strava.models import strava_activity_to_actual_session
from arete.garmin.models import ActivitySource


SAMPLE_ACTIVITY = {
    "id": 123456789,
    "name": "Morning Run",
    "type": "Run",
    "sport_type": "Run",
    "start_date": "2026-05-10T08:00:00Z",
    "start_date_local": "2026-05-10T10:00:00Z",
    "elapsed_time": 3600,
    "moving_time": 3500,
    "distance": 10000.0,
    "total_elevation_gain": 120.5,
    "average_speed": 2.78,
    "max_speed": 4.5,
    "average_heartrate": 145.0,
    "max_heartrate": 172.0,
    "average_cadence": 82.0,
    "calories": 650,
    "start_latlng": [48.8566, 2.3522],
}


class TestStravaToActualSession:
    def test_basic_fields(self):
        session = strava_activity_to_actual_session(SAMPLE_ACTIVITY)
        assert session.source == ActivitySource.STRAVA
        assert session.garmin_activity_id == "123456789"
        assert session.sport == "run"
        assert session.duration_sec == 3600
        assert session.distance_m == 10000.0

    def test_heart_rate(self):
        session = strava_activity_to_actual_session(SAMPLE_ACTIVITY)
        assert session.avg_hr == 145
        assert session.max_hr == 172

    def test_speed(self):
        session = strava_activity_to_actual_session(SAMPLE_ACTIVITY)
        assert session.avg_speed_mps == 2.78
        assert session.max_speed_mps == 4.5

    def test_pace_computed(self):
        session = strava_activity_to_actual_session(SAMPLE_ACTIVITY)
        # 1000 / 2.78 ≈ 360 sec/km
        assert session.avg_pace_sec_km == 360

    def test_elevation(self):
        session = strava_activity_to_actual_session(SAMPLE_ACTIVITY)
        assert session.ascent_m == 120.5

    def test_gps(self):
        session = strava_activity_to_actual_session(SAMPLE_ACTIVITY)
        assert session.start_lat == 48.8566
        assert session.start_lon == 2.3522

    def test_running_cadence_doubled(self):
        session = strava_activity_to_actual_session(SAMPLE_ACTIVITY)
        # Strava reports running cadence per foot → ×2
        assert session.avg_cadence == 164

    def test_cycling_cadence_not_doubled(self):
        activity = {**SAMPLE_ACTIVITY, "type": "Ride", "average_cadence": 90}
        session = strava_activity_to_actual_session(activity)
        assert session.avg_cadence == 90

    def test_missing_optional_fields(self):
        minimal = {
            "id": 1,
            "type": "Run",
            "start_date": "2026-05-10T08:00:00Z",
            "start_date_local": "2026-05-10T10:00:00Z",
            "elapsed_time": 1800,
            "distance": 5000,
        }
        session = strava_activity_to_actual_session(minimal)
        assert session.avg_hr is None
        assert session.start_lat is None
        assert session.calories is None

    def test_sport_type_mapping(self):
        for strava_type, expected in [
            ("Run", "run"), ("TrailRun", "trail_run"),
            ("Ride", "ride"), ("Swim", "swim"),
            ("Hike", "hike"), ("Walk", "walk"),
            ("WeightTraining", "weight_training"),
        ]:
            activity = {**SAMPLE_ACTIVITY, "type": strava_type}
            session = strava_activity_to_actual_session(activity)
            assert session.sport == expected, f"{strava_type} → {session.sport}"
```

**Step 2: Run tests to verify they fail, then implement**

`src/arete/strava/models.py`:

```python
"""Strava activity models and mapping to ActualSession."""
from __future__ import annotations

from datetime import datetime, timezone

from arete.garmin.models import ActualSession, ActivitySource

# Strava type → normalized sport name
_SPORT_MAP: dict[str, str] = {
    "Run": "run",
    "TrailRun": "trail_run",
    "Ride": "ride",
    "VirtualRide": "virtual_ride",
    "Swim": "swim",
    "Hike": "hike",
    "Walk": "walk",
    "WeightTraining": "weight_training",
    "Workout": "workout",
    "Yoga": "yoga",
    "CrossFit": "crossfit",
    "Rowing": "rowing",
    "Elliptical": "elliptical",
}

_RUNNING_TYPES = {"Run", "TrailRun", "VirtualRun"}


def strava_activity_to_actual_session(activity: dict) -> ActualSession:
    """Convert a raw Strava activity dict to an ActualSession."""
    strava_type = activity.get("type", "Workout")
    sport = _SPORT_MAP.get(strava_type, strava_type.lower())

    # Parse dates
    start_str = activity.get("start_date_local") or activity["start_date"]
    start_dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))

    # Speed → pace
    avg_speed = activity.get("average_speed")
    avg_pace_sec_km = None
    if avg_speed and avg_speed > 0:
        avg_pace_sec_km = int(round(1000 / avg_speed))

    # Cadence: Strava reports running cadence per foot (half)
    raw_cadence = activity.get("average_cadence")
    cadence = None
    if raw_cadence is not None:
        cadence = int(raw_cadence * 2) if strava_type in _RUNNING_TYPES else int(raw_cadence)

    # GPS
    latlng = activity.get("start_latlng") or []

    return ActualSession(
        date=start_dt.date(),
        sport=sport,
        duration_sec=activity["elapsed_time"],
        distance_m=activity.get("distance"),
        calories=activity.get("calories"),
        avg_hr=int(activity["average_heartrate"]) if activity.get("average_heartrate") else None,
        max_hr=int(activity["max_heartrate"]) if activity.get("max_heartrate") else None,
        avg_pace_sec_km=avg_pace_sec_km,
        avg_speed_mps=avg_speed,
        max_speed_mps=activity.get("max_speed"),
        ascent_m=activity.get("total_elevation_gain"),
        start_lat=latlng[0] if len(latlng) > 0 else None,
        start_lon=latlng[1] if len(latlng) > 1 else None,
        avg_cadence=cadence,
        source=ActivitySource.STRAVA,
        garmin_activity_id=str(activity["id"]),
        start_time=start_dt,
    )
```

**Step 3: Run tests, then commit**

```bash
git add src/arete/strava/models.py tests/test_strava_models.py
git commit -m "feat(strava): activity-to-ActualSession mapping with sport normalization"
```

---

### Task 4: Strava API router — OAuth + sync + status

**Files:**
- Create: `src/arete/api/strava.py`
- Modify: `src/arete/api/main.py` (register router)
- Test: `tests/test_strava_api.py`

**Step 1: Write tests**

```python
# tests/test_strava_api.py
"""Tests for /strava API endpoints."""
from __future__ import annotations
from unittest.mock import patch, MagicMock
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from arete.api.strava import router


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(router)
    return TestClient(app)


class TestStravaAuthorize:
    @patch.dict("os.environ", {
        "STRAVA_CLIENT_ID": "12345",
        "STRAVA_CLIENT_SECRET": "secret",
        "STRAVA_REDIRECT_URI": "http://localhost:8000/strava/callback",
    })
    def test_returns_authorize_url(self, client):
        resp = client.get("/strava/authorize")
        assert resp.status_code == 200
        data = resp.json()
        assert "url" in data
        assert "strava.com/oauth/authorize" in data["url"]
        assert "client_id=12345" in data["url"]


class TestStravaStatus:
    @patch("arete.api.strava._get_strava_tokens")
    def test_disconnected(self, mock_tokens, client):
        mock_tokens.return_value = None
        resp = client.get("/strava/status")
        assert resp.status_code == 200
        assert resp.json()["connected"] is False

    @patch("arete.api.strava._get_strava_tokens")
    def test_connected(self, mock_tokens, client):
        mock_tokens.return_value = {
            "athlete_id": 42,
            "athlete_name": "Greg",
            "expires_at": 9999999999,
        }
        resp = client.get("/strava/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is True
        assert data["athlete_name"] == "Greg"


class TestStravaDisconnect:
    @patch("arete.api.strava._delete_strava_tokens")
    def test_disconnect(self, mock_delete, client):
        resp = client.delete("/strava/disconnect")
        assert resp.status_code == 200
        mock_delete.assert_called_once()
```

**Step 2: Implement the router**

Create `src/arete/api/strava.py` with:
- `GET /strava/authorize` — returns `{"url": "..."}` (frontend opens this in a new tab)
- `GET /strava/callback` — exchanges code, stores tokens, returns HTML "Connected! Close this tab."
- `POST /strava/sync` — accepts optional `{"days": 30}`, fetches activities, inserts into DB
- `GET /strava/status` — returns `{"connected": bool, "athlete_name": str | null}`
- `DELETE /strava/disconnect` — deletes tokens from DB

DB helpers as module-level functions:
- `_get_strava_tokens()` — SELECT from app.strava_tokens
- `_save_strava_tokens(tokens)` — UPSERT into app.strava_tokens
- `_delete_strava_tokens()` — DELETE from app.strava_tokens
- `_ensure_fresh_token(tokens)` — refresh if needed, persist, return valid access_token

**Step 3: Register in main.py**

Add after the ai_tips router registration:

```python
# Routes Strava
from arete.api.strava import router as strava_router
app.include_router(strava_router)
```

**Step 4: Run tests, then commit**

```bash
git add src/arete/api/strava.py src/arete/api/main.py tests/test_strava_api.py
git commit -m "feat(strava): API router with OAuth, sync, status, disconnect endpoints"
```

---

### Task 5: Environment variables

**Files:**
- Modify: `.env`

**Step 1: Add Strava credentials**

Append to `.env`:

```
# Strava OAuth
STRAVA_CLIENT_ID=<user's client id>
STRAVA_CLIENT_SECRET=<user's client secret>
STRAVA_REDIRECT_URI=http://localhost:8000/strava/callback
```

**Step 2: Rebuild backend**

```bash
docker compose up -d --build --force-recreate backend
```

**Step 3: Verify DB table created**

```bash
docker compose exec backend uv run python -c "
from arete.dataio.db import connect
con = connect(True)
print(con.execute('DESCRIBE app.strava_tokens').fetchall())
con.close()
"
```

No commit needed (`.env` is gitignored).

---

### Task 6: Frontend — Settings Strava tab

**Files:**
- Modify: `frontend/src/lib/api.ts` (add stravaApi)
- Modify: `frontend/src/pages/Settings.tsx` (wire Strava card)

**Step 1: Add stravaApi to api.ts**

```typescript
export const stravaApi = {
  getStatus: () => fetchAPI<{
    connected: boolean;
    athlete_name: string | null;
    athlete_id: number | null;
  }>("/strava/status"),

  getAuthorizeUrl: () => fetchAPI<{ url: string }>("/strava/authorize"),

  sync: (days = 30) =>
    fetchAPI<{
      success: boolean;
      imported: number;
      skipped: number;
      errors: string[];
    }>("/strava/sync", {
      method: "POST",
      body: JSON.stringify({ days }),
    }),

  disconnect: () =>
    fetchAPI<{ success: boolean }>("/strava/disconnect", { method: "DELETE" }),
};
```

**Step 2: Update ConnectionsTab in Settings.tsx**

Replace the Strava "Coming Soon" placeholder with:
- On mount: call `stravaApi.getStatus()` to populate connection state
- If disconnected: "Connect Strava" button → opens `stravaApi.getAuthorizeUrl()` in new tab
- If connected: show athlete name + "Sync Now" button + "Disconnect" button
- Sync button: calls `stravaApi.sync()`, shows count of imported activities
- Use Strava brand color `#FC4C02` for the connect button

**Step 3: Verify frontend compiles**

```bash
docker compose up -d --build --force-recreate frontend
```

**Step 4: Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/pages/Settings.tsx
git commit -m "feat(strava): frontend Strava connection + sync UI in Settings"
```

---

### Task 7: Integration test — full OAuth → sync flow

**Files:**
- Test: `tests/test_strava_integration.py`

**Step 1: Write end-to-end test (mocked HTTP)**

Test the full flow: authorize → callback → sync → verify activities in DB.
All Strava HTTP calls mocked via `unittest.mock.patch`.

**Step 2: Run full test suite**

```bash
uv run pytest tests/ -x -q
```

Expected: all pass (306 existing + ~20 new Strava tests)

**Step 3: Commit**

```bash
git add tests/test_strava_integration.py
git commit -m "test(strava): integration test for OAuth + sync flow"
```

---

### Task 8: Manual end-to-end verification

**Step 1:** Open `http://localhost:3080` → Settings → CONNECTIONS tab
**Step 2:** Click "Connect Strava" → authorize on Strava → redirected back
**Step 3:** Click "Sync Now" → verify activities appear
**Step 4:** Check backend: `curl http://localhost:8000/garmin/actual | python3 -m json.tool`
**Step 5:** Verify activities have `source: "strava"`

---

## Summary

| Task | Files | Tests |
|------|-------|-------|
| 1. DB schema | init_duckdb.py | existing |
| 2. Strava client | strava/client.py | test_strava_client.py (~12) |
| 3. Activity mapping | strava/models.py | test_strava_models.py (~10) |
| 4. API router | api/strava.py + main.py | test_strava_api.py (~5) |
| 5. Env vars | .env | manual |
| 6. Frontend | api.ts + Settings.tsx | manual |
| 7. Integration test | — | test_strava_integration.py |
| 8. E2E verification | — | manual |
