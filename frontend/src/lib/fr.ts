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

/** Backend sport strings (Garmin and Strava spellings) to French labels. */
export const SPORT_LABEL: Record<string, string> = {
  run: 'Course',
  running: 'Course',
  trail_run: 'Trail',
  trail_running: 'Trail',
  treadmill_running: 'Tapis',
  virtual_run: 'Course virtuelle',
  virtualrun: 'Course virtuelle',
  ride: 'Vélo',
  cycling: 'Vélo',
  virtual_ride: 'Home-trainer',
  indoor_cycling: 'Vélo intérieur',
  mountain_biking: 'VTT',
  swim: 'Natation',
  swimming: 'Natation',
  lap_swimming: 'Natation',
  strength: 'Musculation',
  strength_training: 'Musculation',
  weight_training: 'Musculation',
  walk: 'Marche',
  walking: 'Marche',
  hike: 'Randonnée',
  hiking: 'Randonnée',
  rowing: 'Rameur',
  indoor_rowing: 'Rameur',
  yoga: 'Yoga',
  mobility: 'Mobilité',
  cardio: 'Cardio',
  other: 'Autre',
};

export const sportLabel = (sport: string | null | undefined): string =>
  sport ? (SPORT_LABEL[sport.toLowerCase()] ?? sport.replace(/_/g, ' ')) : 'Autre';
