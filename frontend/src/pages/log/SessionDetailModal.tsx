import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Link, Unlink } from 'lucide-react';
import { cn } from '@/lib/utils';
import { EmptyState, LoadingState } from '@/components';
import { Modal, ModalHeader, RPE_TEXT, rpeTone } from '@/components/ui';
import { strengthApi } from '@/lib/api';

interface SessionDetailModalProps {
  sessionId: number | null;
  onClose: () => void;
}

export function SessionDetailModal({ sessionId, onClose }: SessionDetailModalProps) {
  const queryClient = useQueryClient();
  const open = sessionId !== null;

  const { data: session, isLoading } = useQuery({
    queryKey: ['strengthSession', sessionId],
    queryFn: () => strengthApi.getSession(sessionId!),
    enabled: open,
  });

  const { data: garminCandidates } = useQuery({
    queryKey: ['garminCandidates', sessionId],
    queryFn: () => strengthApi.getGarminCandidates(sessionId!),
    enabled: open,
  });

  const linkMutation = useMutation({
    mutationFn: (garminId: number | null) => strengthApi.linkToGarmin(sessionId!, garminId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['strengthSession', sessionId] });
      queryClient.invalidateQueries({ queryKey: ['garminCandidates', sessionId] });
    },
  });

  return (
    <Modal open={open} onClose={onClose} className="max-w-2xl max-h-[80vh] overflow-y-auto">
      <ModalHeader
        title={<span className="font-mono uppercase tracking-wider">SESSION DETAILS</span>}
        tone="text-neon-gold"
        onClose={onClose}
      />

      {isLoading ? (
        <LoadingState />
      ) : session ? (
        <div className="space-y-6">
          <div className="flex items-center justify-between border-b border-text-muted/20 pb-4">
            <div>
              <div className="text-sm font-mono text-text-muted">
                {new Date(session.date).toLocaleDateString('fr-FR', {
                  weekday: 'long',
                  day: 'numeric',
                  month: 'long',
                  year: 'numeric',
                })}
              </div>
              <div className="text-xl font-mono text-text-primary mt-1">{session.name || 'Session'}</div>
            </div>
            <div className="text-right">
              {session.duration_min && (
                <div className="text-sm font-mono text-text-muted">{session.duration_min} min</div>
              )}
              {session.overall_rpe && (
                <div className={cn('text-sm font-mono mt-1', RPE_TEXT[rpeTone(session.overall_rpe)])}>
                  RPE {session.overall_rpe}
                </div>
              )}
            </div>
          </div>

          <div className="grid grid-cols-3 gap-2 sm:gap-4">
            <Stat value={session.exercises_count || session.exercises?.length || 0} label="Exercises" tone="text-neon-cyan" />
            <Stat value={session.total_sets || 0} label="Sets" tone="text-neon-gold" />
            <Stat
              value={`${((session.total_volume || 0) / 1000).toFixed(1)}k`}
              label="Volume (kg)"
              tone="text-success-green"
            />
          </div>

          {session.exercises && session.exercises.length > 0 && (
            <div>
              <h3 className="text-sm font-mono text-text-muted uppercase tracking-wider mb-3">Exercises</h3>
              <div className="space-y-3">
                {session.exercises.map((ex, idx) => (
                  <div key={idx} className="p-3 bg-abyss rounded border border-text-muted/20">
                    <div className="flex items-center justify-between mb-2">
                      <span className="font-mono text-text-primary">
                        {ex.exercise?.name || `Exercise #${ex.exercise_id}`}
                      </span>
                      <span className="text-xs font-mono text-text-muted">{ex.sets?.length || 0} sets</span>
                    </div>
                    {ex.sets && ex.sets.length > 0 && (
                      <div className="flex flex-wrap gap-2">
                        {ex.sets.map((set, setIdx) => (
                          <div
                            key={setIdx}
                            className={cn(
                              'px-2 py-1 rounded text-xs font-mono',
                              set.is_warmup ? 'bg-info-blue/20 text-info-blue' : 'bg-neon-gold/10 text-neon-gold'
                            )}
                          >
                            {set.weight_kg && `${set.weight_kg}kg × `}
                            {set.reps !== null ? `${set.reps}` : 'failure'}
                            {set.rpe && ` @${set.rpe}`}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {session.notes && (
            <div>
              <h3 className="text-sm font-mono text-text-muted uppercase tracking-wider mb-2">Notes</h3>
              <p className="text-sm text-text-secondary font-mono">{session.notes}</p>
            </div>
          )}

          <div className="border-t border-text-muted/20 pt-4">
            <h3 className="text-sm font-mono text-text-muted uppercase tracking-wider mb-3 flex items-center gap-2">
              <Link className="w-4 h-4" />
              Garmin Sync
            </h3>

            {session.garmin_activity_id ? (
              <div className="flex items-center justify-between p-3 bg-success-green/10 rounded border border-success-green/30">
                <div className="flex items-center gap-2">
                  <Check className="w-4 h-4 text-success-green" />
                  <span className="text-sm font-mono text-success-green">
                    Linked to Garmin #{session.garmin_activity_id}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => linkMutation.mutate(null)}
                  disabled={linkMutation.isPending}
                  className="p-2 hover:bg-danger-red/20 rounded text-danger-red transition-colors"
                  title="Unlink"
                >
                  <Unlink className="w-4 h-4" />
                </button>
              </div>
            ) : garminCandidates?.candidates && garminCandidates.candidates.length > 0 ? (
              <div className="space-y-2">
                <p className="text-xs text-text-muted font-mono mb-2">
                  Found {garminCandidates.candidates.length} matching Garmin activity(s):
                </p>
                {garminCandidates.candidates.map((candidate) => (
                  <button
                    key={candidate.id}
                    type="button"
                    onClick={() => linkMutation.mutate(candidate.id)}
                    disabled={linkMutation.isPending}
                    className="w-full p-3 bg-abyss hover:bg-neon-cyan/10 rounded border border-text-muted/20 hover:border-neon-cyan/50 transition-colors text-left"
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <span className="text-sm font-mono text-text-primary">{candidate.date}</span>
                        <span className="text-xs font-mono text-text-muted ml-2">
                          ({Math.round(candidate.duration_seconds / 60)} min)
                        </span>
                      </div>
                      <span className="text-xs font-mono text-neon-cyan uppercase">[LINK]</span>
                    </div>
                  </button>
                ))}
              </div>
            ) : (
              <div className="p-3 bg-abyss rounded border border-text-muted/20">
                <p className="text-sm font-mono text-text-muted text-center">No matching Garmin activities found</p>
              </div>
            )}
          </div>
        </div>
      ) : (
        <EmptyState message="Session not found" />
      )}
    </Modal>
  );
}

function Stat({ value, label, tone }: { value: number | string; label: string; tone: string }) {
  return (
    <div className="text-center p-2 sm:p-3 bg-abyss rounded border border-text-muted/20">
      <div className={cn('text-lg sm:text-2xl font-mono', tone)}>{value}</div>
      <div className="text-[10px] sm:text-xs font-mono text-text-muted uppercase">{label}</div>
    </div>
  );
}
