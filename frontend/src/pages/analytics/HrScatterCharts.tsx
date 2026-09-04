import { useQuery } from '@tanstack/react-query';
import { Cell, ResponsiveContainer, Scatter, ScatterChart, XAxis, YAxis } from 'recharts';
import { analyticsApi } from '@/lib/api';
import { CHART, SCALE } from '@/lib/chartTheme';
import { formatPace } from '@/lib/utils';
import type { HrPaceSession } from '@/types';
import { AXIS, ChartCard, ChartGrid, ChartTooltip, TICK_SM, TooltipBox, axisLabel } from './ChartCard';
import type { ChartProps } from './types';

/** Both scatter charts share the same query (deduped by React Query). */
function useHrPaceSessions(period: ChartProps['period']) {
  return useQuery({
    queryKey: ['analytics', 'hr-pace-scatter', period],
    queryFn: () => analyticsApi.getHrPaceScatter(period),
  });
}

const colorByElevation = (elev: number | null) => {
  if (elev == null) return SCALE.neutral;
  if (elev < 50) return SCALE.good; // flat
  if (elev < 150) return SCALE.moderate;
  return SCALE.bad; // hilly
};

function SessionTooltip({ payload }: { payload?: Array<{ payload: HrPaceSession }> }) {
  const s = payload?.[0]?.payload;
  if (!s) return null;
  return (
    <TooltipBox>
      <div className="font-mono text-neon-cyan">{s.name}</div>
      <div>
        {s.date} · {s.sport}
      </div>
      <div>
        Pace: {s.pace_display ?? '—'} · HR: {s.avg_hr} bpm
      </div>
      <div>
        D+: {s.elevation_gain ?? '—'}m · {s.distance_km ?? '—'} km
      </div>
    </TooltipBox>
  );
}

const HR_AXIS_LABEL = axisLabel('Avg HR (bpm)', 'insideLeft');

export function HrPaceScatter({ period }: ChartProps) {
  const { data, isLoading, isError, refetch } = useHrPaceSessions(period);
  const sessions = data?.sessions ?? [];

  return (
    <ChartCard
      title="HR vs Pace"
      loading={isLoading}
      error={isError}
      onRetry={() => refetch()}
      empty={sessions.length === 0}
    >
      <ResponsiveContainer width="100%" height={300}>
        <ScatterChart>
          <ChartGrid />
          <XAxis
            dataKey="pace_sec_km"
            {...AXIS}
            tick={TICK_SM}
            reversed
            tickFormatter={(v: number) => formatPace(v)}
            name="Pace"
            label={axisLabel('Pace (min/km)', 'insideBottom')}
          />
          <YAxis dataKey="avg_hr" {...AXIS} name="HR" label={HR_AXIS_LABEL} />
          <ChartTooltip content={<SessionTooltip />} />
          <Scatter data={sessions} shape="circle">
            {sessions.map((s, i) => (
              <Cell key={i} fill={colorByElevation(s.elevation_gain)} fillOpacity={0.8} />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
      <div className="flex gap-4 mt-2 text-xs text-text-muted justify-center">
        <LegendDot color="bg-chart-green" label="Flat (<50m)" />
        <LegendDot color="bg-chart-yellow" label="Moderate" />
        <LegendDot color="bg-chart-red" label="Hilly (>150m)" />
      </div>
    </ChartCard>
  );
}

function LegendDot({ color, label }: { color: string; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className={`w-2 h-2 rounded-full inline-block ${color}`} /> {label}
    </span>
  );
}

export function HrElevationScatter({ period }: ChartProps) {
  const { data, isLoading, isError, refetch } = useHrPaceSessions(period);
  const sessions = (data?.sessions ?? []).filter((s) => s.elevation_gain != null);

  return (
    <ChartCard
      title="HR vs Elevation"
      loading={isLoading}
      error={isError}
      onRetry={() => refetch()}
      empty={sessions.length === 0}
    >
      <ResponsiveContainer width="100%" height={300}>
        <ScatterChart>
          <ChartGrid />
          <XAxis
            dataKey="elevation_gain"
            {...AXIS}
            tick={TICK_SM}
            name="Elevation"
            label={axisLabel('D+ (m)', 'insideBottom')}
          />
          <YAxis dataKey="avg_hr" {...AXIS} name="HR" label={HR_AXIS_LABEL} />
          <ChartTooltip content={<SessionTooltip />} />
          <Scatter data={sessions} fill={CHART.purple} fillOpacity={0.7} />
        </ScatterChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
