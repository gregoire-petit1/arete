import { cn } from '@/lib/utils';
import { StrengthIcon } from '@/components';
import { RpeBadge } from '@/components/ui';
import type { StrengthSession } from '@/types';

export function SessionRow({
  session,
  onView,
  onDelete,
}: {
  session: StrengthSession;
  onView: () => void;
  onDelete: () => void;
}) {
  return (
    <div
      className={cn(
        'flex items-center gap-2 sm:gap-4 p-2 sm:p-3 rounded',
        'bg-abyss/50 border border-text-muted/10',
        'hover:border-neon-cyan/30 transition-all cursor-pointer'
      )}
      onClick={onView}
    >
      <StrengthIcon size="md" className="text-warning-orange" />
      <div className="flex-1">
        <div className="flex items-center gap-2">
          <span className="text-sm font-mono text-text-primary">
            {new Date(session.date).toLocaleDateString('fr-FR', { day: '2-digit', month: 'short' })}
          </span>
          <span className="text-text-muted">—</span>
          <span className="text-sm font-mono text-text-secondary">{session.name || 'Session'}</span>
        </div>
        <div className="text-[10px] sm:text-xs font-mono text-text-muted mt-1">
          {session.duration_min && `${session.duration_min}min`}
          {' │ '}
          Volume: {(session.total_volume / 1000).toFixed(1)}k kg
          {' │ '}
          {session.total_sets} sets
        </div>
      </div>
      <RpeBadge rpe={session.overall_rpe} />
      <button
        type="button"
        className="text-xs font-mono text-neon-cyan hover:underline"
        onClick={(e) => {
          e.stopPropagation();
          onView();
        }}
      >
        [VIEW]
      </button>
      <button
        type="button"
        className="text-xs font-mono text-danger-red hover:underline"
        onClick={(e) => {
          e.stopPropagation();
          if (confirm('Delete this session?')) onDelete();
        }}
      >
        [DEL]
      </button>
    </div>
  );
}
