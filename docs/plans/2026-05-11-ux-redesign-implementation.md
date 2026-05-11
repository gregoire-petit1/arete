# UX Redesign Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restructure Arete from 6 pages to 4, eliminate redundancies, integrate contextual AI, and make HP/MP/XP data-driven.

**Architecture:** Incremental refactor — extract shared components first, then reshape pages one at a time, finally remove dead pages and update routing. Backend-first for new data endpoints, then frontend integration.

**Tech Stack:** FastAPI (backend), React + TailwindCSS (frontend), TanStack Query (data fetching)

---

### Task 1: Extract shared GarminLoginModal component

**Files:**
- Create: `frontend/src/components/GarminLoginModal.tsx`
- Modify: `frontend/src/components/index.ts`
- Modify: `frontend/src/pages/Matrix.tsx` (import shared component)
- Modify: `frontend/src/pages/Settings.tsx` (import shared component)

**What:**
Extract the login modal (~130 lines duplicated between Matrix:443-571 and Settings:606-735) into a single shared component. Props: `isOpen`, `onClose`, `onSuccess`, `needsMfa`/`setNeedsMfa`.

Replace both inline modals with `<GarminLoginModal />`.

**Verify:** `npx tsc -b --noEmit` passes. App still works at http://localhost:3080/settings and /matrix.

**Commit:** `refactor: extract shared GarminLoginModal component`

---

### Task 2: Backend — daily tip endpoint

**Files:**
- Create: `src/arete/api/ai_tips.py`
- Modify: `src/arete/api/main.py` (include router)
- Test: `tests/test_ai_tips.py`

**What:**
New router `/tips/daily` that:
1. Fetches current ACWR, TSB, readiness from existing metrics functions
2. Generates a 1-2 sentence French tip using existing `recommendations.py` logic (no LLM needed — rule-based is fine for v1)
3. Returns `{ "tip": "string", "priority": "info|warning|alert", "generated_at": "ISO date" }`

**Verify:** `uv run pytest tests/test_ai_tips.py -v` passes.

**Commit:** `feat: add /tips/daily endpoint for contextual AI advice`

---

### Task 3: Backend — real HP/MP/XP endpoint

**Files:**
- Modify: `src/arete/api/metrics.py` (add `/metrics/player-stats` endpoint)
- Test: `tests/test_metrics_api.py` (add tests)

**What:**
New endpoint `GET /metrics/player-stats` returns:
```json
{
  "hp": { "current": 72, "max": 100, "label": "Recovery" },
  "mp": { "current": 45, "max": 100, "label": "Fitness" },
  "xp": { "current": 180, "max": 300, "label": "Weekly Volume" },
  "level": 12
}
```

Calculations:
- HP = `readiness_score` from `compute_performance_model`
- MP = `min(100, CTL / target_CTL * 100)` where target_CTL comes from user_settings (default 50)
- XP = sum of TSS this week (Mon-now). Max = weekly TSS goal from user_settings (default 300)
- Level = count of past weeks where weekly TSS >= goal (query training_log grouped by ISO week)

**Verify:** `uv run pytest tests/test_metrics_api.py -v` passes.

**Commit:** `feat: add /metrics/player-stats endpoint with real HP/MP/XP`

---

### Task 4: Backend — post-session feedback endpoint

**Files:**
- Modify: `src/arete/api/ai_tips.py` (add `/tips/post-session` endpoint)
- Test: `tests/test_ai_tips.py` (add tests)

**What:**
`POST /tips/post-session` with body `{ "session_type": "strength|cardio", "session_id": number }`.

For strength: compare volume by muscle group vs previous week → generate feedback.
For cardio: if actual_session has HR/pace data → comment on zones/pacing.

Rule-based v1, no LLM required. Returns `{ "feedback": "string", "highlights": ["string"] }`.

**Verify:** `uv run pytest tests/test_ai_tips.py -v` passes.

**Commit:** `feat: add /tips/post-session endpoint for post-workout feedback`

---

### Task 5: Settings page — absorb Matrix as "System" tab

**Files:**
- Modify: `frontend/src/pages/Settings.tsx`

**What:**
1. Add "System" tab (icon: `Terminal`) after the existing tabs
2. Move into it: system status grid, Garmin sync center, knowledge base section (copy from Matrix.tsx)
3. Use `<GarminLoginModal />` shared component (from Task 1)
4. Remove Garmin login from "Connections" tab — replace with a link "Manage in System tab"

**Verify:** `npx tsc -b --noEmit`. Navigate to /settings, all tabs work.

**Commit:** `feat: absorb Matrix into Settings as System tab`

---

### Task 6: Log page — merge Force + Cardio tabs

**Files:**
- Create: `frontend/src/pages/Log.tsx`
- Modify: `frontend/src/pages/index.ts`

**What:**
New page with 2 tabs:

**Force tab** — from Forge.tsx, keep:
- Session log form (text parser + preview + save)
- Muscle heatmap (compact)
- PRs section
- Recent strength sessions
- Remove: Exercise Library grid (search stays in parser modal)

**Cardio tab** — new:
- `<FitDropzone />` component
- After upload: activity summary card
- Post-session AI feedback (from Task 4 endpoint)

Common bottom section: unified "Recent Sessions" (strength + cardio merged).

**Verify:** `npx tsc -b --noEmit`. Page renders both tabs.

**Commit:** `feat: create Log page with Force and Cardio tabs`

---

### Task 7: Planning page — clean QuestLog

**Files:**
- Modify: `frontend/src/pages/QuestLog.tsx` (rename export to `PlanningPage`)
- Modify: `frontend/src/pages/index.ts`

**What:**
Remove from QuestLog:
1. "Recent Sessions" section (moved to Dashboard/Log)
2. FIT Upload zone (moved to Log > Cardio)
3. `strengthSessions` query + merge logic (no longer needed)

Keep:
- Week navigation
- Calendar week grid
- Adherence dashboard
- New Quest form modal
- Session detail modal

Rename export: `QuestLogPage` → `PlanningPage`.

**Verify:** `npx tsc -b --noEmit`. Calendar and adherence still render.

**Commit:** `refactor: clean Planning page, remove redundant sections`

---

### Task 8: Dashboard page — rewrite HUD

**Files:**
- Modify: `frontend/src/pages/HUD.tsx` (rename export to `DashboardPage`)
- Modify: `frontend/src/pages/index.ts`
- Modify: `frontend/src/lib/api.ts` (add new API calls)

**What:**
Rewrite HUD layout:

**Top block: "Today's Plan"**
- Fetch today's planned sessions from `/garmin/planned?start=today&end=today`
- Display each planned session with sport icon + description
- "Log this session" button → navigates to /log with pre-filled data
- If no plan: "Rest day" or "Add a session" link to /planning

**Middle block: "Player Status"**
- Fetch from `/metrics/player-stats` (Task 3)
- HP/MP/XP bars with real data
- Level badge
- Metric cards (ACWR, TSB, Readiness) — kept from current HUD

**Bottom block: "AI Tip"**
- Fetch from `/tips/daily` (Task 2)
- Single styled card with priority-based coloring

**Quick actions footer:** "Log Session" + "View Planning" buttons.

Rename export: `HUDPage` → `DashboardPage`.

**Verify:** `npx tsc -b --noEmit`. Dashboard renders with all 3 blocks.

**Commit:** `feat: rewrite Dashboard with plan du jour, real HP/MP/XP, AI tip`

---

### Task 9: Update routing and navigation

**Files:**
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/Navigation.tsx`
- Modify: `frontend/src/pages/index.ts`
- Delete: `frontend/src/pages/NeuralLink.tsx`
- Delete: `frontend/src/pages/Matrix.tsx`

**What:**
Routes: `/` (Dashboard), `/planning`, `/log`, `/settings`
Nav items: Dashboard (LayoutDashboard), Planning (CalendarDays), Log (Dumbbell), Settings (Settings)

Remove NeuralLink.tsx and Matrix.tsx files.
Update page exports in index.ts.

**Verify:** `npx tsc -b --noEmit`. All 4 routes accessible. No 404s. Old routes redirect or 404 gracefully.

**Commit:** `feat: 4-page navigation, remove NeuralLink and Matrix`

---

### Task 10: Docker rebuild + final verification

**What:**
1. `docker compose build`
2. `docker compose up -d`
3. Verify all 4 pages at http://localhost:3080
4. Verify API health at http://localhost:3080/api/health
5. Run full test suite: `uv run pytest`

**Commit:** `chore: verify Docker build after UX redesign`
