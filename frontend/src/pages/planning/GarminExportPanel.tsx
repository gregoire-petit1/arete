import { type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { PlannedSession } from '@/types';
import { exportApi } from '@/lib/documents';
import { WorkoutSelection } from '@/components/WorkoutSelection';
import { exportLabel } from '@/lib/workouts';
import { useWorkoutActions } from '@/hooks/useWorkoutActions';

export function GarminExportPanel({ sessions, children }: { sessions: PlannedSession[]; children?: (render: (id: number) => ReactNode) => ReactNode }) {
  const statuses = useQuery({ queryKey: ['garmin-exports'], queryFn: exportApi.statuses, retry: false });
  const actions = useWorkoutActions();
  return <section className="mb-6" aria-label="Envoi des séances vers Garmin">
    <WorkoutSelection sessions={sessions.map(session => ({ session: { ...session, revision: session.revision ?? 1 }, export: statuses.data?.find(s => s.session_id === session.id) ?? null }))}>{children}</WorkoutSelection>
    {statuses.error && <p role="alert" className="mt-2 text-xs text-danger-red">{statuses.error.message}</p>}
    {statuses.data?.filter(s => s.deleted && s.state !== 'removed').map(state => <div key={state.session_id} className="mt-3 rounded-lg border border-warning-orange/30 p-3 text-sm">
      <p>Séance supprimée #{state.session_id} · {exportLabel(state)}</p>
      {state.error && <p className="text-danger-red">{state.error}</p>}
      <button className="mr-4 min-h-11 text-neon-cyan" disabled={actions.busy} onClick={() => void actions.run({ kind: 'remove', session: { id: state.session_id, revision: 1, date: '', sport: '', description: '', status: 'deleted' } })}>Retirer de Garmin Connect</button>
      <button className="min-h-11 text-neon-cyan" disabled={actions.busy} onClick={() => void actions.run({ kind: 'verify', session: { id: state.session_id, revision: 1, date: '', sport: '', description: '', status: 'deleted' } })}>Vérifier Garmin</button>
    </div>)}
    {actions.error && <p role="alert" className="text-xs text-danger-red">{actions.error}</p>}
  </section>;
}
