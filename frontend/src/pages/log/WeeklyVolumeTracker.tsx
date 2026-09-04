import { Panel } from '@/components/ui';
import type { StrengthSession } from '@/types';

const WEEKLY_TARGET_KG = 20000;

export function WeeklyVolumeTracker({ sessions }: { sessions: StrengthSession[] }) {
  const volume = sessions.reduce((sum, s) => sum + (s.total_volume || 0), 0);
  const sets = sessions.reduce((sum, s) => sum + (s.total_sets || 0), 0);
  const avgRpe = sessions.length
    ? sessions.reduce((sum, s) => sum + (s.overall_rpe || 0), 0) / sessions.length
    : 0;
  const pct = (volume / WEEKLY_TARGET_KG) * 100;

  return (
    <Panel title="WEEKLY VOLUME TRACKER" delay={0.1}>
      <div className="grid grid-cols-3 gap-2 sm:gap-4 mb-4">
        <div className="text-center">
          <div className="text-lg sm:text-2xl font-mono font-bold text-neon-cyan">{(volume / 1000).toFixed(1)}k</div>
          <div className="text-xs text-text-muted font-mono">Total Volume (kg)</div>
        </div>
        <div className="text-center">
          <div className="text-lg sm:text-2xl font-mono font-bold text-neon-purple">{sets}</div>
          <div className="text-[10px] sm:text-xs text-text-muted font-mono">Total Sets</div>
        </div>
        <div className="text-center">
          <div className="text-lg sm:text-2xl font-mono font-bold text-warning-orange">{avgRpe.toFixed(1)}</div>
          <div className="text-xs text-text-muted font-mono">Avg RPE</div>
        </div>
      </div>
      <div className="h-2 bg-shadow rounded overflow-hidden">
        <div
          className="h-full bg-neon-cyan transition-all duration-500"
          style={{ width: `${Math.min(100, pct)}%` }}
        />
      </div>
      <div className="text-xs text-text-muted font-mono mt-2 text-right">
        {pct.toFixed(0)}% of weekly target ({WEEKLY_TARGET_KG.toLocaleString('en-US')} kg)
      </div>
    </Panel>
  );
}
