import { useQuery } from '@tanstack/react-query';
import { Cell, Legend, Pie, PieChart, ResponsiveContainer } from 'recharts';
import { analyticsApi } from '@/lib/api';
import { getSportHex } from '@/lib/sport';
import { ChartCard, ChartTooltip } from './ChartCard';
import type { ChartProps } from './types';

export function SportDistributionChart({ period }: ChartProps) {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['analytics', 'sport-distribution', period],
    queryFn: () => analyticsApi.getSportDistribution(period),
  });

  const sportData = data?.sports ?? [];

  return (
    <ChartCard
      title="Sport Distribution"
      loading={isLoading}
      error={isError}
      onRetry={() => refetch()}
      empty={sportData.length === 0}
    >
      <ResponsiveContainer width="100%" height={300}>
        <PieChart>
          <Pie data={sportData} dataKey="hours" nameKey="sport" innerRadius={60} outerRadius={100} paddingAngle={2}>
            {sportData.map((entry, i) => (
              <Cell key={i} fill={getSportHex(entry.sport)} />
            ))}
          </Pie>
          <ChartTooltip />
          <Legend />
        </PieChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
