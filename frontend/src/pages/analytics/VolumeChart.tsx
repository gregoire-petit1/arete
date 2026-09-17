import { useQuery } from '@tanstack/react-query';
import { Bar, BarChart, Legend, ResponsiveContainer, XAxis, YAxis } from 'recharts';
import { analyticsApi } from '@/lib/api';
import { getSportHex } from '@/lib/sport';
import { AXIS, ChartCard, ChartGrid, ChartTooltip, DATE_AXIS } from './ChartCard';
import type { ChartProps } from './types';

export function VolumeChart({ period }: ChartProps) {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['analytics', 'volume', period],
    queryFn: () => analyticsApi.getVolume(period),
  });

  // {weeks: [{week, sports: {run: {hours, km}}}]} -> [{week, run: 1.5, ...}]
  const volumeData = (data?.weeks ?? []).map((w) => {
    const flat: Record<string, string | number> = { week: w.week };
    for (const [sport, val] of Object.entries(w.sports)) flat[sport] = val.hours;
    return flat;
  });
  const sports = Array.from(
    new Set(volumeData.flatMap((w) => Object.keys(w).filter((k) => k !== 'week')))
  );

  return (
    <ChartCard
      title="Training Volume"
      loading={isLoading}
      error={isError}
      onRetry={() => refetch()}
      empty={volumeData.length === 0}
    >
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={volumeData}>
          <ChartGrid />
          <XAxis dataKey="week" {...DATE_AXIS} />
          <YAxis {...AXIS} />
          <ChartTooltip />
          <Legend />
          {sports.map((sport) => (
            <Bar key={sport} dataKey={sport} stackId="volume" fill={getSportHex(sport)} name={sport} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
