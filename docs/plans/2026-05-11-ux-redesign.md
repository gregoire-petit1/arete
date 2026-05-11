# UX Redesign — From 6 Pages to 4

**Date:** 2026-05-11
**Status:** Approved

## Context

Arete has 6 pages with significant redundancy: duplicated Garmin login modals (Matrix + Settings), FIT upload in 2 places, recent sessions shown on 2 pages, and a chat page (NeuralLink) that doesn't fit the natural user flow. The Matrix page is admin tooling that most users would never visit.

User's primary flow: check metrics + today's plan → log sessions → review/adjust weekly planning.

## Design Decisions

### Page Structure: 6 → 4

| Page | Purpose | Source |
|------|---------|--------|
| **Dashboard** | Today's plan + metrics + AI tip | HUD enriched |
| **Planning** | Weekly calendar + adherence | QuestLog cleaned |
| **Log** | Record sessions (force + cardio) | Forge + FIT upload |
| **Settings** | User prefs + system admin | Settings + Matrix absorbed |

**Removed pages:**
- **NeuralLink** — replaced by contextual AI integrated into each page
- **Matrix** — absorbed into Settings as "System" tab

### Navigation

Bottom tab bar (mobile): Dashboard | Planning | Log | Settings
Top nav (desktop): same 4 items.

### AI Integration (replaces NeuralLink)

No dedicated chat page. Instead, contextual AI advice surfaces where relevant:

- **Dashboard**: "Tip of the day" block based on current ACWR/TSB/readiness. Cached 1x/day.
- **Planning**: Per-day suggestion badges on empty calendar slots. Generated on demand.
- **Log (post-session)**: Feedback block after saving a session (volume trends, pacing analysis).

Chat can be re-added later as a floating assistant if needed.

### HP / MP / XP — Real Data

| Bar | Label | Source | Calculation |
|-----|-------|--------|-------------|
| HP | Recovery | `readiness_score` | Direct from fitness model (0-100) |
| MP | Fitness | CTL (chronic training load) | `min(100, CTL / target_CTL * 100)` |
| XP | Weekly Volume | Sum of weekly TSS | Accumulates Mon→Sun, resets Monday |
| Level | Consistency | Weekly goal streak | +1 each week XP reaches the threshold |

`target_CTL` and weekly TSS goal come from user Settings (Goals tab).

### Log Page — Two Tabs

**Force tab** (from Forge, simplified):
- Text parser form (existing AI parser)
- Muscle heatmap
- Personal Records
- Recent strength sessions
- Exercise library removed as standalone section (search integrated into parser)

**Cardio tab** (new):
- FIT file upload (moved from QuestLog/Matrix)
- Activity summary after import
- AI post-session feedback

### Settings — New "System" Tab

Absorbs Matrix content:
- API/DB/RAG status
- Garmin connection (single login modal, shared component)
- Garmin sync controls
- Knowledge base management
- Data export/import

### Redundancies Eliminated

| Redundancy | Resolution |
|------------|------------|
| Garmin Login Modal (Matrix + Settings) | Single shared `GarminLoginModal` component |
| FIT Upload (QuestLog + Matrix) | Moved to Log > Cardio tab only |
| Recent Sessions (HUD + QuestLog) | Dashboard only (unified list) |
| Garmin sync status (Matrix + Settings) | Settings > System tab only |
| Strength sessions fetched by QuestLog | Removed from Planning, stays in Log |

## Out of Scope

- Light theme / theme switching
- Multi-user / authentication
- Exercise library as standalone page
- Floating chat assistant (future iteration)
