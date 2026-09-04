import { useQuery } from '@tanstack/react-query';
import { analyticsApi } from '@/lib/api';
import { ChartCard } from './ChartCard';

const TH = 'text-left py-2 px-2 text-neon-cyan font-mono text-xs uppercase';

export function BestEffortsTable() {
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['analytics', 'best-efforts'],
    queryFn: () => analyticsApi.getBestEfforts(),
  });

  const efforts = data?.efforts ?? [];

  return (
    <ChartCard
      title="Best Efforts (Running)"
      loading={isLoading}
      error={isError}
      onRetry={() => refetch()}
      empty={efforts.length === 0}
      emptyMessage="No best efforts data yet — sync activities from Strava to get started"
    >
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-text-muted/20">
              <th className={TH}>Effort</th>
              <th className={TH}>Best Time</th>
              <th className={TH}>Date</th>
              <th className={TH}>Activity</th>
            </tr>
          </thead>
          <tbody>
            {efforts.map((e, i) => (
              <tr key={i} className="border-b border-text-muted/10 hover:bg-void/50">
                <td className="py-2 px-2 text-text-primary">{e.name}</td>
                <td className="py-2 px-2 text-text-secondary font-mono">{e.best_time_display}</td>
                <td className="py-2 px-2 text-text-muted">{e.date}</td>
                <td className="py-2 px-2 text-text-muted">{e.activity_name || '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </ChartCard>
  );
}
