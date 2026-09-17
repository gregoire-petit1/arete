import { useQuery } from '@tanstack/react-query';
import { Trophy } from 'lucide-react';
import { analyticsApi } from '@/lib/api';

/** All-time bests, independent of the selected period. */
export function RecordsCard() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ['analytics', 'records'],
    queryFn: () => analyticsApi.getRecords(),
    staleTime: 5 * 60 * 1000,
  });
  const records = data?.records ?? [];

  return (
    <section className="bg-abyss rounded-lg border border-text-muted/20 p-4 flex flex-col gap-3">
      <header className="flex items-center gap-2">
        <Trophy className="w-4 h-4 text-neon-gold" aria-hidden />
        <h3 className="text-sm font-mono text-neon-cyan uppercase tracking-wider">Records</h3>
      </header>

      {isLoading ? (
        <p className="text-sm text-text-muted animate-pulse py-6 text-center">Chargement…</p>
      ) : isError ? (
        <p className="text-sm text-danger-red py-6 text-center">Données indisponibles</p>
      ) : records.length === 0 ? (
        <p className="text-sm text-text-muted py-6 text-center">
          Aucun record : les meilleurs efforts viennent des activités Strava.
        </p>
      ) : (
        <table className="w-full text-sm">
          <thead>
            <tr className="text-[10px] uppercase tracking-wider text-text-muted font-mono">
              <th className="text-left font-normal pb-1">Distance</th>
              <th className="text-right font-normal pb-1">Temps</th>
              <th className="text-right font-normal pb-1">Date</th>
            </tr>
          </thead>
          <tbody>
            {records.map((r) => (
              <tr key={r.name} className="border-t border-text-muted/10">
                <td className="py-1.5 font-mono text-text-secondary">{r.name}</td>
                <td className="py-1.5 text-right font-mono text-text-primary tabular-nums">{r.time_display}</td>
                <td className="py-1.5 text-right font-mono text-text-muted tabular-nums" title={r.activity_name}>
                  {new Date(`${r.date}T00:00:00`).toLocaleDateString('fr-FR', {
                    day: 'numeric',
                    month: 'short',
                    year: '2-digit',
                  })}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
