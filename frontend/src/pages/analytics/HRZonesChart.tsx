import { useQuery } from '@tanstack/react-query';
import { Bar, BarChart, Legend, ResponsiveContainer, XAxis, YAxis } from 'recharts';
import { analyticsApi } from '@/lib/api';
import { HR_ZONE_COLORS } from '@/lib/chartTheme';
import { AXIS, ChartCard, ChartGrid, ChartTooltip, TICK_SM, axisLabel } from './ChartCard';
import type { ChartProps } from './types';

const ZONES = ['z1', 'z2', 'z3', 'z4', 'z5'];

export function HRZonesChart({ period }: ChartProps) {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['analytics', 'hr-zones', period],
    queryFn: () => analyticsApi.getHrZones(period),
  });

  // {weeks: [{week, zones: {z1: 600, ...}}]} -> [{week, z1: 10, ...}] in minutes
  const zoneData = (data?.weeks ?? []).map((w) => {
    const flat: Record<string, string | number> = { week: w.week };
    for (const [zone, secs] of Object.entries(w.zones)) flat[zone] = Math.round(secs / 60);
    return flat;
  });

  return (
    <ChartCard
      title="Heart Rate Zones"
      loading={isLoading}
      error={isError}
      onRetry={() => refetch()}
      empty={zoneData.length === 0}
    >
      <ResponsiveContainer width="100%" height={300}>
        <BarChart data={zoneData}>
          <ChartGrid />
          <XAxis dataKey="week" {...AXIS} tick={TICK_SM} />
          <YAxis {...AXIS} label={axisLabel('min', 'insideLeft')} />
          <ChartTooltip />
          <Legend />
          {ZONES.map((zone, i) => (
            <Bar key={zone} dataKey={zone} stackId="zones" fill={HR_ZONE_COLORS[i]} name={`Zone ${i + 1}`} />
          ))}
        </BarChart>
      </ResponsiveContainer>
    </ChartCard>
  );
}
