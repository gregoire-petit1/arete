/** Shared French labels for values the backend sends as snake_case enums. */

export const ZONE_LABEL: Record<string, string> = {
  // ACWR
  undertraining: 'sous-entraînement',
  optimal: 'optimal',
  caution: 'prudence',
  high_risk: 'risque élevé',
  danger: 'danger',
  // Form (TSB)
  exhausted: 'épuisé',
  fatigued: 'fatigué',
  neutral: 'neutre',
  fresh: 'frais',
  peak: 'pic de forme',
  // Readiness
  poor: 'faible',
  moderate: 'moyen',
  good: 'bon',
  excellent: 'excellent',
  unknown: 'inconnu',
};

export const zoneLabel = (zone: string | null | undefined): string =>
  zone ? (ZONE_LABEL[zone] ?? zone.replace(/_/g, ' ')) : ZONE_LABEL.unknown;

/** "7h12" from seconds, for sleep durations. */
export function formatHoursMinutes(seconds: number): string {
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds - h * 3600) / 60);
  return m === 60 ? `${h + 1}h00` : `${h}h${String(m).padStart(2, '0')}`;
}
