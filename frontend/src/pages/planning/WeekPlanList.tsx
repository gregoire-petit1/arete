import { ActualSessionRow } from '@/components/ActualSessionRow';
import { PlannedSessionCard, isPlannedDone } from '@/components/PlannedSessionCard';
import { cn } from '@/lib/utils';
import type { ActualSession, PlannedSession } from '@/types';

function dayLabel(iso: string): string {
  return new Date(iso).toLocaleDateString('fr-FR', { weekday: 'long', day: 'numeric', month: 'short' });
}

export function WeekPlanList({
  days,
  planned,
  actual,
  selectedDate,
  today,
  planStart,
  onSelect,
}: {
  days: string[];
  planned: PlannedSession[];
  actual: ActualSession[];
  selectedDate: string | null;
  today: string;
  planStart: string;
  onSelect: (date: string | null) => void;
}) {
  const shown = selectedDate ? days.filter((d) => d === selectedDate) : days;

  return (
    <div className="space-y-4">
      {selectedDate && (
        <button
          type="button"
          onClick={() => onSelect(null)}
          className="text-xs font-mono text-neon-cyan hover:underline"
        >
          ← Toute la semaine
        </button>
      )}
      {shown.map((date) => {
        const sessions = planned.filter((p) => p.date === date);
        const done = actual.filter((a) => a.date.slice(0, 10) === date);
        // realised sessions not explained by a planned one of the same sport that day
        const offPlan = done.filter(
          (a) => a.planned_session_id == null && !sessions.some((p) => p.sport === a.sport)
        );
        const isToday = date === today;
        return (
          <section key={date}>
            <h3
              className={cn(
                'text-xs font-mono uppercase tracking-wider mb-2 flex items-center gap-2',
                isToday ? 'text-neon-cyan' : 'text-text-muted'
              )}
            >
              {dayLabel(date)}
              {isToday && <span className="text-[10px] border border-neon-cyan/40 rounded px-1">aujourd'hui</span>}
            </h3>
            {sessions.length === 0 && done.length === 0 ? (
              <p className="text-xs font-mono text-text-muted/70 pl-1">Repos</p>
            ) : (
              <div className="space-y-2">
                {sessions.map((s) => (
                  <PlannedSessionCard key={s.id} session={s} done={isPlannedDone(s, actual)} />
                ))}
                {offPlan.map((a) => (
                  <ActualSessionRow key={a.id} session={a} offPlan={sessions.length > 0 || date >= planStart} />
                ))}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
