import { useQuery } from '@tanstack/react-query';
import { ResponsiveContainer, Scatter, ScatterChart, XAxis, YAxis } from 'recharts';
import { analyticsApi } from '@/lib/api';
import { CHART } from '@/lib/chartTheme';
import { formatPace } from '@/lib/utils';
import { AXIS, ChartCard, ChartGrid, ChartTooltip, TICK_SM } from './ChartCard';
import type { ChartProps } from './types';

export function PaceChart({ period }: ChartProps) {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['analytics', 'pace', period],
    queryFn: () => analyticsApi.getPace(period),
  });

  const paceData = data?.activities ?? [];

  return (
    <ChartCard
      title="Pace Trend"
      loading={isLoading}
      error={isError}
      onRetry={() => refetch()}
      empty={paceData.length === 0}
    >
      <ResponsiveContainer width="100%" height={300}>
        <ScatterChart>
          <ChartGrid />
          <XAxis dataKey="date" {...AXIS} tick={TICK_SM} name="Date" />
          <YAxis dataKey="pace_sec_km" {...AXIS} reversed tickFormatter={(v: number) => formatPace(v)} name="Pace" />
          <ChartTooltip
            formatter={(value: number, name: string) => [formatPace(value), name === 'pace_sec_km' ? 'Pace' : name]}
          />
          <Scatter data={paceData} fill={CHART.cyan} />
        </ScatterChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
