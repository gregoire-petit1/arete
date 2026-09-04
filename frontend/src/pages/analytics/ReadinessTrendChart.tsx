import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Legend, Line, LineChart, ResponsiveContainer, XAxis, YAxis } from 'recharts';
import { garminHealthApi } from '@/lib/api';
import { CHART } from '@/lib/chartTheme';
import { AXIS, ChartCard, ChartGrid, ChartTooltip } from './ChartCard';
import type { ChartProps } from './types';

const DAYS_FOR_PERIOD: Partial<Record<ChartProps['period'], number>> = { '7d': 7, '30d': 30, '90d': 90 };

export function ReadinessTrendChart({ period }: ChartProps) {
  const { start, end } = useMemo(() => {
    const now = new Date();
    const days = DAYS_FOR_PERIOD[period] ?? 180;
    return {
      end: now.toISOString().slice(0, 10),
      start: new Date(now.getTime() - days * 86400000).toISOString().slice(0, 10),
    };
  }, [period]);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['garmin-health', 'range', start, end],
    queryFn: () => garminHealthApi.getRange(start, end),
  });

  const days = data?.days ?? [];

  return (
    <ChartCard
      title="Readiness Trend"
      loading={isLoading}
      error={isError}
      onRetry={() => refetch()}
      empty={days.length === 0}
    >
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={days}>
          <ChartGrid />
          <XAxis dataKey="date" {...AXIS} tick={{ fontSize: 11 }} tickFormatter={(v: string) => v.slice(5)} />
          <YAxis yAxisId="readiness" domain={[0, 100]} stroke={CHART.gold} />
          <YAxis yAxisId="hrv" orientation="right" domain={[0, 120]} stroke={CHART.cyan} />
          <ChartTooltip labelFormatter={(v: string) => `Date: ${v}`} />
          <Legend />
          <Line
            yAxisId="readiness"
            type="monotone"
            dataKey="readiness_score"
            stroke={CHART.gold}
            strokeWidth={2}
            dot={false}
            name="Readiness"
          />
          <Line
            yAxisId="hrv"
            type="monotone"
            dataKey="hrv_last_night"
            stroke={CHART.cyan}
            strokeWidth={1.5}
            dot={false}
            name="HRV (ms)"
            strokeDasharray="4 4"
          />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
