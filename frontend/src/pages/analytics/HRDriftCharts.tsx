import { useQuery } from '@tanstack/react-query';
import { Line, LineChart, ResponsiveContainer, XAxis, YAxis } from 'recharts';
import { analyticsApi } from '@/lib/api';
import { CHART, COLORS, SCALE, SCORE_COLORS } from '@/lib/chartTheme';
import { AXIS, ChartCard, ChartGrid, ChartTooltip, TICK_SM, TooltipBox, axisLabel, DATE_AXIS } from './ChartCard';
import type { ChartProps } from './types';

/** Both HR-drift cards share the same query (deduped by React Query). */
function useHrDrift(period: ChartProps['period']) {
  return useQuery({
    queryKey: ['analytics', 'hr-drift', period],
    queryFn: () => analyticsApi.getHrDrift(period, 40),
  });
}

interface WeeklyDrift {
  week: string;
  decoupling_pct: number;
  n: number;
  top_score: string;
}

function WeekTooltip({ payload }: { payload?: Array<{ payload: WeeklyDrift }> }) {
  const w = payload?.[0]?.payload;
  if (!w) return null;
  return (
    <TooltipBox>
      <div className="font-mono text-neon-cyan">Week of {w.week}</div>
      <div>
        Avg decoupling: <b>{w.decoupling_pct}%</b> ({w.n} runs)
      </div>
      <div>
        Top score: <span style={{ color: SCORE_COLORS[w.top_score] }}>{w.top_score}</span>
      </div>
    </TooltipBox>
  );
}

export function HRDriftChart({ period }: ChartProps) {
  const { data, isLoading, isError, refetch } = useHrDrift(period);
  const runs = data?.runs ?? [];
  const baseline = data?.baseline;

  // Per-week aggregation: avg decoupling, colored by the most frequent score
  const byWeek: Record<string, { sum: number; n: number; scores: string[] }> = {};
  for (const r of runs) {
    const d = new Date(r.date);
    const monday = new Date(d);
    monday.setUTCDate(d.getUTCDate() - ((d.getUTCDay() + 6) % 7));
    const key = monday.toISOString().slice(0, 10);
    byWeek[key] ??= { sum: 0, n: 0, scores: [] };
    byWeek[key].sum += r.decoupling_pct;
    byWeek[key].n += 1;
    byWeek[key].scores.push(r.drift_score);
  }
  const weekly: WeeklyDrift[] = Object.entries(byWeek)
    .map(([week, v]) => {
      const counts: Record<string, number> = {};
      v.scores.forEach((s) => (counts[s] = (counts[s] || 0) + 1));
      const top = Object.entries(counts).sort((a, b) => b[1] - a[1])[0][0];
      return { week, decoupling_pct: Math.round((v.sum / v.n) * 10) / 10, n: v.n, top_score: top };
    })
    .sort((a, b) => a.week.localeCompare(b.week));

  return (
    <ChartCard
      title="HR Drift (Cardiac Decoupling)"
      loading={isLoading}
      error={isError}
      onRetry={() => refetch()}
      empty={runs.length === 0}
    >
      <ResponsiveContainer width="100%" height={300}>
        <LineChart data={weekly}>
          <ChartGrid />
          <XAxis dataKey="week" {...DATE_AXIS} />
          <YAxis {...AXIS} tick={TICK_SM} label={axisLabel('Decoupling %', 'insideLeft')} />
          <ChartTooltip content={<WeekTooltip />} />
          <Line
            type="monotone"
            dataKey="decoupling_pct"
            stroke={CHART.cyan}
            strokeWidth={2}
            dot={(props: { key?: React.Key | null; cx?: number; cy?: number; payload?: WeeklyDrift }) => (
              <circle
                key={props.key ?? undefined}
                cx={props.cx}
                cy={props.cy}
                r={4}
                fill={SCORE_COLORS[props.payload?.top_score ?? ''] || CHART.cyan}
                stroke={COLORS.void}
                strokeWidth={1}
              />
            )}
          />
        </LineChart>
      </ResponsiveContainer>
      {baseline && (
        <div className="mt-3 text-[10px] font-mono text-text-muted text-center">
          Baseline R² = {baseline.r_squared} on {baseline.n_samples} runs · formula: {baseline.formula}
        </div>
      )}
    </ChartCard>
  );
}

const bucketColor = (avg: number) =>
  avg < 0 ? CHART.cyan : avg < 5 ? SCALE.good : avg < 10 ? SCALE.moderate : SCALE.bad;

export function EffortBucketSummary({ period }: ChartProps) {
  const { data, isLoading, isError, refetch } = useHrDrift(period);
  const entries = Object.entries(data?.effort_buckets ?? {}).sort(([a], [b]) => a.localeCompare(b));

  return (
    <ChartCard
      title="Decoupling by Effort Class"
      loading={isLoading}
      error={isError}
      onRetry={() => refetch()}
      empty={entries.length === 0}
    >
      <div className="space-y-2">
        {entries.map(([k, v]) => {
          const avg = v.avg_decoupling_pct ?? 0;
          const color = bucketColor(avg);
          return (
            <div key={k} className="flex items-center gap-2 text-xs font-mono">
              <div className="w-28 text-text-muted capitalize">{k.replace('_', ' ')}</div>
              <div className="flex-1 bg-abyss rounded-full h-2 overflow-hidden border border-text-muted/20">
                <div
                  className="h-full"
                  style={{ width: `${Math.min(Math.abs(avg) * 5, 100)}%`, background: color }}
                />
              </div>
              <div className="w-16 text-right" style={{ color }}>
                {avg > 0 ? '+' : ''}
                {avg}%
              </div>
              <div className="w-10 text-text-muted text-right">n={v.n}</div>
            </div>
          );
        })}
      </div>
    </ChartCard>
  );
}
