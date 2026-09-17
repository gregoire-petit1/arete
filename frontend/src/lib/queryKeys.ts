import type { QueryClient } from '@tanstack/react-query';

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

  strengthSessions: (limit?: number) =>
    limit ? (['strengthSessions', limit] as const) : (['strengthSessions'] as const),
  strengthSession: (id: number) => ['strengthSession', id] as const,
  volumeByMuscle: (windowDays?: number) =>
    windowDays ? (['volumeByMuscle', windowDays] as const) : (['volumeByMuscle'] as const),
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
};

/** Everything that changes when a session is logged, uploaded, synced or matched. */
export function invalidateAfterSession(queryClient: QueryClient): void {
  for (const key of [
    qk.planned(),
    qk.actual(),
    qk.matchSummary(),
    qk.strengthSessions(),
    qk.volumeByMuscle(),
    qk.cardioSessions,
    qk.analytics,
    qk.playerStats,
    qk.fitness,
    qk.workload,
  ]) {
    queryClient.invalidateQueries({ queryKey: key });
  }
}
