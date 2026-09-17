import { cn } from '@/lib/utils';
import { SESSION_TYPE_LABEL } from '@/components/PlannedSessionCard';
import { getSportColor, getSportIconComponent } from '@/lib/sport';
import type { ActualSession, PlannedSession } from '@/types';
import { toLocalISODate } from '@/lib/dates';

interface CalendarDayProps {
  date: string;
  planned: PlannedSession[];
  actual: ActualSession[];
  isToday: boolean;
  onClick?: () => void;
}

function CalendarDay({ date, planned, actual, isToday, onClick }: CalendarDayProps) {
  const dayOfWeek = new Date(date).toLocaleDateString('fr-FR', { weekday: 'short' }).toUpperCase().slice(0, 3);
  const dayNum = new Date(date).getDate();

  // Combine all sessions for the day
  const allSessions = [
    ...planned.map((p) => ({ type: 'planned' as const, sport: p.sport || p.session_type, data: p })),
    ...actual
      .filter((a) => !planned.some((p) => p.sport === a.sport || p.session_type === a.activity_type))
      .map((a) => ({ type: 'actual' as const, sport: a.sport || a.activity_type, data: a })),
  ];

  const hasCompleted = actual.length > 0;
  const hasPending = planned.length > 0 && actual.length < planned.length;
  const isRest = planned.length === 0 && actual.length === 0;

  return (
    <div
      onClick={onClick}
      className={cn(
        'flex flex-col p-2 rounded transition-all duration-200',
        'border min-h-[120px]',
        onClick ? 'cursor-pointer hover:scale-[1.02]' : 'cursor-default',
        isToday && 'border-neon-cyan shadow-[0_0_15px_rgba(0,240,255,0.3)]',
        hasCompleted && !isToday && 'border-success-green/40 bg-success-green/5',
        hasPending && !hasCompleted && !isToday && 'border-text-muted/30 bg-abyss/50',
        isRest && 'border-text-muted/10 bg-void/50'
      )}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-[10px] font-mono text-text-muted tracking-wider">{dayOfWeek}.</span>
        <span className={cn('text-sm font-mono font-medium', isToday ? 'text-neon-cyan' : 'text-text-secondary')}>
          {dayNum}
        </span>
      </div>

      {allSessions.length > 0 ? (
        <div className="flex-1 flex flex-col gap-1">
          {allSessions.slice(0, 3).map((session, idx) => {
            const IconComponent = getSportIconComponent(session.sport);
            const colorClass = getSportColor(session.sport);
            const isComplete =
              session.type === 'actual' ||
              actual.some(
                (a) =>
                  a.sport === session.data.sport ||
                  a.activity_type === (session.data as PlannedSession).session_type
              );

            return (
              <div
                key={idx}
                className={cn(
                  'flex items-center gap-1.5 px-1.5 py-1 rounded text-[10px] font-mono',
                  isComplete ? 'bg-success-green/15 text-success-green' : 'bg-abyss/80 text-text-secondary'
                )}
              >
                <IconComponent size="sm" className={cn(isComplete ? 'text-success-green' : colorClass)} />
                <span className="truncate capitalize" title={(session.data as PlannedSession).description ?? undefined}>
                  {session.type === 'planned'
                    ? (SESSION_TYPE_LABEL[(session.data as PlannedSession).session_type] ?? session.sport)
                    : session.sport?.toLowerCase()}
                </span>
                {isComplete && <span className="ml-auto">✓</span>}
              </div>
            );
          })}
          {allSessions.length > 3 && (
            <div className="text-[10px] text-text-muted font-mono text-center">+{allSessions.length - 3} more</div>
          )}
        </div>
      ) : (
        <div className="flex-1 flex items-center justify-center">
          <span className="text-[10px] font-mono text-text-muted tracking-wider">REST</span>
        </div>
      )}
    </div>
  );
}

interface CalendarWeekProps {
  startDate: string;
  plannedSessions: PlannedSession[];
  actualSessions: ActualSession[];
  onDayClick?: (date: string) => void;
}

export function CalendarWeek({ startDate, plannedSessions, actualSessions, onDayClick }: CalendarWeekProps) {
  const today = toLocalISODate();

  const days = Array.from({ length: 7 }, (_, i) => {
    const date = new Date(startDate);
    date.setDate(date.getDate() + i);
    return toLocalISODate(date);
  });

  const plannedByDate = new Map<string, PlannedSession[]>();
  plannedSessions.forEach((s) => {
    const dateKey = s.date.split('T')[0];
    if (!plannedByDate.has(dateKey)) plannedByDate.set(dateKey, []);
    plannedByDate.get(dateKey)!.push(s);
  });

  const actualByDate = new Map<string, ActualSession[]>();
  actualSessions.forEach((s) => {
    const dateKey = s.date.split('T')[0];
    if (!actualByDate.has(dateKey)) actualByDate.set(dateKey, []);
    actualByDate.get(dateKey)!.push(s);
  });

  return (
    <div className="grid grid-cols-7 gap-2">
      {days.map((date) => (
        <CalendarDay
          key={date}
          date={date}
          planned={plannedByDate.get(date) || []}
          actual={actualByDate.get(date) || []}
          isToday={date === today}
          onClick={onDayClick ? () => onDayClick(date) : undefined}
        />
      ))}
    </div>
  );
}
