import { createElement } from 'react';
import { Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import { getSportIconComponent, getSportColor } from '@/lib/sport';
import type { ActualSession, PlannedSession } from '@/types';

const INTENSITY: Record<string, string> = {
  easy: 'text-success-green border-success-green/40',
  moderate: 'text-warning-orange border-warning-orange/40',
  hard: 'text-danger-red border-danger-red/40',
};

export const SESSION_TYPE_LABEL: Record<string, string> = {
  endurance: 'EF',
  recovery: 'Récup',
  tempo: 'Seuil',
  intervals: 'Fractionné',
  long_run: 'Sortie longue',
  strength: 'Muscu',
  hypertrophy: 'Muscu',
  power: 'Muscu',
  deload: 'Deload',
};

/** True when an actual session of the same sport happened on the planned day. */
export function isPlannedDone(planned: PlannedSession, actual: ActualSession[]): boolean {
  if (planned.status === 'completed') return true;
  return actual.some((a) => a.date.slice(0, 10) === planned.date && a.sport === planned.sport);
}

export function PlannedSessionCard({
  session,
  done,
  compact = false,
  className,
}: {
  session: PlannedSession;
  done: boolean;
  compact?: boolean;
  className?: string;
}) {
  const typeLabel = SESSION_TYPE_LABEL[session.session_type] ?? session.session_type;
  const intensity = session.target_intensity ? INTENSITY[session.target_intensity] : null;

  return (
    <div
      className={cn(
        'rounded-lg border px-3 py-2',
        done ? 'border-success-green/40 bg-success-green/5' : 'border-text-muted/20 bg-shadow/50',
        className
      )}
    >
      <div className="flex items-center gap-3">
        {createElement(getSportIconComponent(session.sport), {
          className: cn('w-5 h-5 shrink-0', done ? 'text-success-green' : getSportColor(session.sport)),
        })}
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1 text-xs font-mono min-w-0">
          <span className="text-text-primary uppercase tracking-wider">{typeLabel}</span>
          <span className="text-text-muted capitalize">{session.sport}</span>
          {session.target_duration_min && <span className="text-text-muted">{session.target_duration_min} min</span>}
          {session.target_distance_km && <span className="text-text-muted">{session.target_distance_km} km</span>}
          {intensity && (
            <span className={cn('border rounded px-1.5 py-0.5 text-[10px] uppercase', intensity)}>
              {session.target_intensity}
            </span>
          )}
        </div>
        {done && <Check className="w-4 h-4 text-success-green ml-auto shrink-0" />}
      </div>
      {session.description && (
        <p className={cn('mt-1.5 text-xs font-mono text-text-secondary whitespace-pre-line', compact && 'line-clamp-2')}>
          {session.description}
        </p>
      )}
    </div>
  );
}
