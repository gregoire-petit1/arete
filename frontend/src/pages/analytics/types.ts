import type { Bucket, Period } from '@/types';

export const PERIODS: Period[] = ['7d', '30d', '90d', '6m', '1y', 'all'];

export const PERIOD_LABEL: Record<Period, string> = {
  '7d': '7 jours',
  '30d': '30 jours',
  '90d': '90 jours',
  '6m': '6 mois',
  '1y': '1 an',
  all: 'Tout',
};

export const PERIOD_SHORT: Record<Period, string> = {
  '7d': '7 J',
  '30d': '30 J',
  '90d': '90 J',
  '6m': '6 M',
  '1y': '1 AN',
  all: 'TOUT',
};

/** How the previous window is named in a delta tooltip. */
export const PREVIOUS_LABEL: Record<Period, string> = {
  '7d': 'les 7 jours précédents',
  '30d': 'les 30 jours précédents',
  '90d': 'les 90 jours précédents',
  '6m': 'les 6 mois précédents',
  '1y': "l'année précédente",
  all: 'la période précédente',
};

/** Axis label for a bucket start, adapted to the bucket width. */
export function formatBucket(iso: string, bucket: Bucket): string {
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  if (bucket === 'month') return d.toLocaleDateString('fr-FR', { month: 'short', year: '2-digit' });
  const day = d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'short' });
  return bucket === 'week' ? `sem. ${day}` : day;
}

/** Full label used inside tooltips, where there is room. */
export function formatBucketLong(iso: string, bucket: Bucket): string {
  const d = new Date(`${iso}T00:00:00`);
  if (Number.isNaN(d.getTime())) return iso;
  if (bucket === 'month') return d.toLocaleDateString('fr-FR', { month: 'long', year: 'numeric' });
  const day = d.toLocaleDateString('fr-FR', { day: 'numeric', month: 'long', year: 'numeric' });
  return bucket === 'week' ? `semaine du ${day}` : day;
}
