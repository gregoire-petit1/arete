import { useQuery } from '@tanstack/react-query';
import { Legend, Line, LineChart, ResponsiveContainer, XAxis, YAxis } from 'recharts';
import { analyticsApi } from '@/lib/api';
import { CHART } from '@/lib/chartTheme';
import { AXIS, ChartCard, ChartGrid, ChartTooltip, TICK_SM } from './ChartCard';
import type { ChartProps } from './types';

export function TrainingLoadChart({ period }: ChartProps) {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['analytics', 'training-load', period],
    queryFn: () => analyticsApi.getTrainingLoad(period),
  });

  const loadData = data?.data ?? [];

  return (
    <ChartCard
      title="Training Load (PMC)"
      loading={isLoading}
      error={isError}
      onRetry={() => refetch()}
      empty={loadData.length === 0}
    >
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={loadData}>
          <ChartGrid />
          <XAxis dataKey="date" {...AXIS} tick={TICK_SM} />
          <YAxis {...AXIS} />
          <ChartTooltip />
          <Legend />
          <Line type="monotone" dataKey="ctl" stroke={CHART.blue} name="Fitness (CTL)" dot={false} />
          <Line type="monotone" dataKey="atl" stroke={CHART.red} name="Fatigue (ATL)" dot={false} />
          <Line type="monotone" dataKey="tsb" stroke={CHART.green} name="Form (TSB)" dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
