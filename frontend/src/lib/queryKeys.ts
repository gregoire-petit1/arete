import type { QueryClient } from '@tanstack/react-query';
import { strengthApi } from './api';

/**
 * Every react-query key of the app, in one place.
 *
 * Keys are hierarchical: invalidating `['planned']` invalidates every window.
 * Use `invalidateAfterSession` after anything that creates, edits or matches a
 * session — the same data feeds Dashboard, Planning, Log and Analytics.
 */
export const qk = {
  settings: ['settings'] as const,

  planned: (start?: string, end?: string) =>
    start ? (['planned', start, end ?? start] as const) : (['planned'] as const),
  actual: (start?: string, end?: string) =>
    start ? (['actual', start, end ?? start] as const) : (['actual'] as const),
  matchSummary: (start?: string, end?: string) =>
    start ? (['matchSummary', start, end ?? start] as const) : (['matchSummary'] as const),

  strengthSessions: ['strengthSessions'] as const,
  strengthSession: (id: number) => ['strengthSession', id] as const,
  muscleStats: (days?: number) =>
    days ? (['muscleStats', days] as const) : (['muscleStats'] as const),
  garminCandidates: (sessionId: number) => ['garminCandidates', sessionId] as const,

  cardioSessions: ['cardioSessions'] as const,
  analytics: ['analytics'] as const,
  playerStats: ['player-stats'] as const,
  fitness: ['fitness'] as const,
  workload: ['workload'] as const,
  tipDaily: ['tip-daily'] as const,

  health: ['garmin-health'] as const,
  healthDaily: (date: string) => ['garmin-health', 'daily', date] as const,
  healthStatus: ['garminHealthStatus'] as const,
  syncStatus: ['syncStatus'] as const,
  stravaStatus: ['stravaStatus'] as const,

  planToday: ['plan', 'today'] as const,
  /** Watch steps of a planned session; changes whenever the session is adapted. */
  plannedStructure: (id?: number) =>
    id == null ? (['plannedStructure'] as const) : (['plannedStructure', id] as const),
  vapidKey: ['vapidPublicKey'] as const,
  /** This device's Web Push state (lib/push.ts), not a server answer. */
  pushState: ['pushState'] as const,
};

/**
 * The strength-session list Dashboard, Planning and Log share: one request,
 * each page `select`s its slice (today, the week grid, the 10 latest).
 */
export const strengthSessionsQuery = {
  queryKey: qk.strengthSessions,
  queryFn: () => strengthApi.getSessions(200),
};

/** Everything that changes when a session is logged, uploaded, synced or matched. */
export function invalidateAfterSession(queryClient: QueryClient): void {
  for (const key of [
    qk.planned(),
    qk.actual(),
    qk.matchSummary(),
    qk.strengthSessions,
    qk.muscleStats(),
    qk.cardioSessions,
    qk.analytics,
    qk.playerStats,
    qk.fitness,
    qk.workload,
    qk.planToday,
    qk.plannedStructure(),
  ]) {
    queryClient.invalidateQueries({ queryKey: key });
  }
}
