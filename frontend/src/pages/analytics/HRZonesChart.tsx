import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Bar, BarChart, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { analyticsApi } from '@/lib/api';
import { HR_ZONE_COLORS } from '@/lib/chartTheme';
import { cn } from '@/lib/utils';
import { AXIS, ChartCard, ChartGrid, TooltipBox, axisLabel, DATE_AXIS } from './ChartCard';
import type { ChartProps } from './types';

const ZONES = ['z1', 'z2', 'z3', 'z4', 'z5'];
type Mode = 'min' | 'pct';

interface WeekRow {
  week: string;
  total_min: number;
  [key: string]: string | number; // z1..z5 in minutes, z1_pct..z5_pct in %
}

export function HRZonesChart({ period }: ChartProps) {
  const [mode, setMode] = useState<Mode>('min');
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['analytics', 'hr-zones', period],
    queryFn: () => analyticsApi.getHrZones(period),
  });

  // {weeks: [{week, zones: {z1: sec, ...}}]} -> minutes and share per zone
  const rows: WeekRow[] = (data?.weeks ?? []).map((w) => {
    const total = Object.values(w.zones).reduce((a, b) => a + b, 0);
    const row: WeekRow = { week: w.week, total_min: Math.round(total / 60) };
    for (const z of ZONES) {
      const secs = w.zones[z] ?? 0;
      row[z] = Math.round(secs / 60);
      row[`${z}_pct`] = total ? Math.round((secs / total) * 1000) / 10 : 0;
    }
    return row;
  });

  const toggle = (
    <div className="flex text-[10px] font-mono border border-text-muted/30 rounded overflow-hidden">
      {(['min', 'pct'] as Mode[]).map((m) => (
        <button
          key={m}
          type="button"
          onClick={() => setMode(m)}
          className={cn('px-2 py-0.5', mode === m ? 'bg-neon-cyan/20 text-neon-cyan' : 'text-text-muted hover:text-text-secondary')}
        >
          {m === 'min' ? 'MIN' : '%'}
        </button>
      ))}
    </div>
  );

  return (
    <ChartCard
      title="Heart Rate Zones"
      loading={isLoading}
      error={isError}
      onRetry={() => refetch()}
      empty={rows.length === 0}
      actions={toggle}
    >
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={rows}>
          <ChartGrid />
          <XAxis dataKey="week" {...DATE_AXIS} />
          <YAxis
            {...AXIS}
            domain={mode === 'pct' ? [0, 100] : undefined}
            label={axisLabel(mode === 'pct' ? '%' : 'min', 'insideLeft')}
          />
          <Tooltip
            content={({ payload, label }) => {
              const row = payload?.[0]?.payload as WeekRow | undefined;
              if (!row) return null;
              return (
                <TooltipBox>
                  <div className="font-mono text-neon-cyan mb-1">
                    Week of {label} · {row.total_min} min
                  </div>
                  {ZONES.map((z, i) => (
                    <div key={z} className="flex justify-between gap-4">
                      <span style={{ color: HR_ZONE_COLORS[i] }}>Zone {i + 1}</span>
                      <span>
                        {row[z]} min · {row[`${z}_pct`]}%
                      </span>
                    </div>
                  ))}
                </TooltipBox>
              );
            }}
          />
          <Legend />
          {ZONES.map((zone, i) => (
            <Bar
              key={zone}
              dataKey={mode === 'pct' ? `${zone}_pct` : zone}
              stackId="zones"
              fill={HR_ZONE_COLORS[i]}
              name={`Zone ${i + 1}`}
            />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
