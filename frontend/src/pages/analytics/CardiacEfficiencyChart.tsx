import { useQuery } from '@tanstack/react-query';
import { Legend, Line, LineChart, ResponsiveContainer, XAxis, YAxis } from 'recharts';
import { analyticsApi } from '@/lib/api';
import { CHART } from '@/lib/chartTheme';
import { AXIS, ChartCard, ChartGrid, ChartTooltip, TICK_SM } from './ChartCard';
import type { ChartProps } from './types';

export function CardiacEfficiencyChart({ period }: ChartProps) {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['analytics', 'cardiac-efficiency', period],
    queryFn: () => analyticsApi.getCardiacEfficiency(period),
  });

  const effData = data?.data ?? [];

  return (
    <ChartCard
      title="Cardiac Efficiency Trend"
      loading={isLoading}
      error={isError}
      onRetry={() => refetch()}
      empty={effData.length === 0}
    >
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={effData}>
          <ChartGrid />
          <XAxis dataKey="week" {...AXIS} tick={TICK_SM} />
          <YAxis yAxisId="eff" stroke={CHART.cyan} domain={['auto', 'auto']} />
          <YAxis yAxisId="hr" orientation="right" stroke={CHART.red} domain={['auto', 'auto']} />
          <ChartTooltip
            formatter={(value: number, name: string) => {
              if (name === 'Efficiency') return [value.toFixed(1) + ' bpm/(km/h)', name];
              if (name === 'Avg HR') return [value + ' bpm', name];
              return [value, name];
            }}
            labelFormatter={(label: string) => `Week of ${label}`}
          />
          <Legend />
          <Line
            yAxisId="eff"
            type="monotone"
            dataKey="efficiency"
            stroke={CHART.cyan}
            name="Efficiency"
            strokeWidth={2}
            dot={{ r: 3 }}
          />
          <Line
            yAxisId="hr"
            type="monotone"
            dataKey="avg_hr"
            stroke={CHART.red}
            name="Avg HR"
            strokeWidth={1}
            strokeDasharray="5 5"
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
