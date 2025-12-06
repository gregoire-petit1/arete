import { motion } from 'framer-motion';
import { cn, getSportIcon, calculateXP, formatDuration } from '@/lib/utils';
import type { SessionLogRow } from '@/types';

interface SessionTimelineProps {
  sessions: SessionLogRow[];
  onSessionClick?: (session: SessionLogRow) => void;
}

export function SessionTimeline({ sessions, onSessionClick }: SessionTimelineProps) {
  if (!sessions.length) {
    return (
      <div className="text-center py-8 text-text-muted font-mono">
        NO DATA AVAILABLE
        <div className="text-xs mt-2">Begin training to initialize metrics</div>
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {sessions.map((session, idx) => {
        const xp = calculateXP(session.rpe, session.duration / 60);
        const icon = getSportIcon(session.sport);

        return (
          <motion.div
            key={session.id}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: idx * 0.1 }}
            onClick={() => onSessionClick?.(session)}
            className={cn(
              'flex items-center gap-4 p-3 rounded',
              'bg-abyss/50 border border-text-muted/10',
              'hover:border-neon-cyan/30 hover:bg-abyss',
              'transition-all duration-200 cursor-pointer'
            )}
          >
            {/* Sport Icon */}
            <div className="text-2xl">{icon}</div>

            {/* Date & Sport */}
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <span className="text-sm font-mono text-text-primary">
                  {new Date(session.date).toLocaleDateString('fr-FR', {
                    day: '2-digit',
                    month: 'short',
                  })}
                </span>
                <span className="text-text-muted">—</span>
                <span className="text-sm text-text-secondary capitalize">
                  {session.sport}
                </span>
              </div>
              {session.notes && (
                <div className="text-xs text-text-muted truncate max-w-[200px]">
                  {session.notes}
                </div>
              )}
            </div>

            {/* Duration */}
            <div className="text-sm font-mono text-text-secondary">
              {formatDuration(session.duration)}
            </div>

            {/* RPE */}
            {session.rpe && (
              <div
                className={cn(
                  'px-2 py-0.5 rounded text-xs font-mono',
                  session.rpe <= 5 && 'bg-success-green/20 text-success-green',
                  session.rpe > 5 && session.rpe <= 7 && 'bg-warning-orange/20 text-warning-orange',
                  session.rpe > 7 && 'bg-danger-red/20 text-danger-red'
                )}
              >
                RPE {session.rpe}
              </div>
            )}

            {/* XP */}
            <div className="text-sm font-mono text-neon-gold">
              +{xp} XP
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}
