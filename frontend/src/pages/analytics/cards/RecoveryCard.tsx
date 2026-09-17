import { Area, AreaChart, ResponsiveContainer, XAxis, YAxis } from 'recharts';
import type { Bucket, Card } from '@/types';
import { CHART } from '@/lib/chartTheme';
import { StatCard } from '../StatCard';
import { ChartGrid, ChartTooltip, bucketAxis, bucketLabel } from '../chartParts';

/** One Garmin recovery metric: mean over the window and its trend. */
export function RecoveryCard({
  title,
  question,
  card,
  bucket,
  color,
  unit,
  previousLabel,
  loading,
  error,
}: {
  title: string;
  question: string;
  card?: Card;
  bucket: Bucket;
  color: string;
  unit: string;
  previousLabel: string;
  loading?: boolean;
  error?: boolean;
}) {
  const data = (card?.series ?? []).map((p) => ({
    bucket: p.bucket,
    value: p.value === null ? null : Number(p.value),
  }));
  const gradientId = `grad-${title.replace(/\s/g, '')}`;

  return (
    <StatCard
      title={title}
      question={question}
      card={card}
      secondaryLabels={['Dernière mesure']}
      previousLabel={previousLabel}
      loading={loading}
      error={error}
    >
      <ResponsiveContainer width="100%" height={150}>
        <AreaChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -12 }}>
          <defs>
            <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.35} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <ChartGrid />
          <XAxis {...bucketAxis(bucket)} />
          <YAxis
            domain={['dataMin - 3', 'dataMax + 3']}
            stroke={CHART.axis}
            tick={{ fontSize: 11, fill: CHART.axis }}
            width={40}
          />
          <ChartTooltip
            labelFormatter={bucketLabel(bucket)}
            formatter={(value: number) => [`${value.toFixed(0)} ${unit}`.trim(), title]}
          />
          <Area
            type="monotone"
            dataKey="value"
            name={title}
            stroke={color}
            strokeWidth={2}
            fill={`url(#${gradientId})`}
            connectNulls
          />
        </AreaChart>
      </ResponsiveContainer>
    </StatCard>
  );
}
