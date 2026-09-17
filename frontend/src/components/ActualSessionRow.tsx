import { createElement } from 'react';
import { cn, formatDurationCompact, formatPace } from '@/lib/utils';
import { getSportIconComponent, getSportColor } from '@/lib/sport';
import type { ActualSession, StrengthSession } from '@/types';

/** A strength session typed in the Log, shaped like an ActualSession for calendars/lists. */
export function strengthAsActual(s: StrengthSession): ActualSession {
  return {
    id: -s.id, // negative: never collides with actual_sessions ids
    planned_session_id: null,
    date: s.date,
    sport: 'strength',
    activity_type: 'strength_log',
    duration_seconds: (s.duration_min ?? 0) * 60,
    avg_hr: null,
    max_hr: null,
    name: s.name ?? `Muscu · ${s.total_sets} séries`,
  } as ActualSession;
}

export function ActualSessionRow({ session, offPlan, className }: { session: ActualSession; offPlan?: boolean; className?: string }) {
  const s = session as ActualSession & { name?: string | null; avg_pace_sec_km?: number | null; distance_m?: number | null };
  const km = s.distance_km ?? (s.distance_m ? s.distance_m / 1000 : null);
  const pace = s.avg_pace_sec_km ?? null;
  return (
    <div className={cn('flex items-center gap-3 rounded-lg border border-text-muted/15 bg-void/40 px-3 py-1.5', className)}>
      {createElement(getSportIconComponent(session.sport), { className: cn('w-4 h-4 shrink-0', getSportColor(session.sport)) })}
      <div className="flex flex-wrap items-center gap-x-2 text-xs font-mono min-w-0">
        <span className="text-text-secondary truncate">{s.name || session.sport}</span>
        {session.duration_seconds ? <span className="text-text-muted">{formatDurationCompact(session.duration_seconds)}</span> : null}
        {km ? <span className="text-text-muted">{km.toFixed(1)} km</span> : null}
        {pace ? <span className="text-text-muted">{formatPace(pace)}/km</span> : null}
        {session.avg_hr ? <span className="text-text-muted">{session.avg_hr} bpm</span> : null}
      </div>
      {offPlan && <span className="ml-auto text-[10px] font-mono text-warning-orange border border-warning-orange/40 rounded px-1.5">hors plan</span>}
    </div>
  );
}
