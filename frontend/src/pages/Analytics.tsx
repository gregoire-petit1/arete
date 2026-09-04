import { useState } from 'react';
import { cn } from '@/lib/utils';
import {
  BestEffortsTable,
  CardiacEfficiencyChart,
  EffortBucketSummary,
  HRDriftChart,
  HRZonesChart,
  HrElevationScatter,
  HrPaceScatter,
  PaceChart,
  PERIODS,
  ReadinessTrendChart,
  SportDistributionChart,
  TrainingLoadChart,
  VolumeChart,
  type Period,
} from './analytics/index';

function SectionTitle({ children }: { children: string }) {
  return (
    <h2 className="text-lg font-bold font-mono text-neon-cyan/80 tracking-wider uppercase pt-2">{children}</h2>
  );
}

export function AnalyticsPage() {
  const [period, setPeriod] = useState<Period>('30d');

  return (
    <div className="max-w-7xl mx-auto px-4 py-6 space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <h1 className="text-xl font-bold font-mono text-neon-cyan tracking-wider uppercase">Analytics</h1>
        <div className="flex gap-1 flex-wrap">
          {PERIODS.map((p) => (
            <button
              key={p}
              type="button"
              onClick={() => setPeriod(p)}
              className={cn(
                'px-3 py-1 text-xs font-mono rounded transition-all border',
                period === p
                  ? 'bg-neon-cyan/20 text-neon-cyan border-neon-cyan/40'
                  : 'text-text-muted hover:text-text-secondary bg-abyss border-text-muted/20'
              )}
            >
              {p.toUpperCase()}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <VolumeChart period={period} />
        <TrainingLoadChart period={period} />
        <PaceChart period={period} />
        <HRZonesChart period={period} />
        <SportDistributionChart period={period} />
        <BestEffortsTable />
      </div>

      <SectionTitle>Cardiac Analysis</SectionTitle>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <CardiacEfficiencyChart period={period} />
        <HrPaceScatter period={period} />
        <HrElevationScatter period={period} />
      </div>

      <SectionTitle>HR Drift (Aerobic Decoupling)</SectionTitle>
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <HRDriftChart period={period} />
        <EffortBucketSummary period={period} />
      </div>

      <SectionTitle>Readiness & Recovery</SectionTitle>
      <div className="grid grid-cols-1 gap-4">
        <ReadinessTrendChart period={period} />
      </div>
    </div>
  );
}
