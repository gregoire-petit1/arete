import type { ActivityStreams } from '@/types';

/** Sports whose speed reads as a pace (min/km); the others as km/h. */
const FOOT = ['run', 'walk', 'hik', 'trail'];

export function isFootSport(sport: string | null | undefined): boolean {
  const s = (sport ?? '').toLowerCase();
  return FOOT.some((prefix) => s.includes(prefix));
}

/** Slower than this is a stop, not a pace worth drawing (20 min/km). */
const SLOWEST_PACE_SEC_KM = 1200;

export interface ChartRow {
  t: number;
  hr: number | null;
  /** sec/km on foot, km/h otherwise. */
  pace: number | null;
  altitude: number | null;
}

/** One row per stream sample, in the units the charts draw. */
export function chartRows(streams: ActivityStreams, sport: string): ChartRow[] {
  const foot = isFootSport(sport);
  return streams.t.map((t, i) => {
    const speed = streams.speed_mps?.[i] ?? null;
    let pace: number | null = null;
    if (speed !== null && speed > 0) {
      if (!foot) pace = Math.round(speed * 36) / 10;
      else if (1000 / speed <= SLOWEST_PACE_SEC_KM) pace = Math.round(1000 / speed);
    }
    return {
      t,
      hr: streams.heart_rate?.[i] ?? null,
      pace,
      altitude: streams.altitude_m?.[i] ?? null,
    };
  });
}

/** Elapsed time: "m:ss" under an hour, "h:mm:ss" above. */
export function formatElapsed(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  const ss = String(s).padStart(2, '0');
  return h > 0 ? `${h}:${String(m).padStart(2, '0')}:${ss}` : `${m}:${ss}`;
}

const INTENSITY_LABEL: Record<string, string> = {
  warmup: 'Échauffement',
  active: 'Effort',
  '5': 'Effort',
  interval: 'Effort',
  rest: 'Récup',
  '4': 'Récup',
  recovery: 'Récup',
  cooldown: 'Retour au calme',
};

export function intensityLabel(raw: string | number | null): string {
  return raw == null ? '—' : (INTENSITY_LABEL[String(raw).toLowerCase()] ?? '—');
}

export interface ProjectedRoute {
  /** SVG `points` attribute. */
  points: string;
  start: [number, number];
  end: [number, number];
}

/**
 * Fit a [lat, lon] trace into a width × height box, north up.
 *
 * Equirectangular: longitudes shrink by cos(latitude), which is exact enough
 * at the scale of one activity. The aspect ratio is kept, the trace centred.
 */
export function projectRoute(
  route: [number, number][],
  width: number,
  height: number,
  pad = 8,
): ProjectedRoute | null {
  if (route.length < 2) return null;
  const lats = route.map(([lat]) => lat);
  const meanLat = lats.reduce((a, b) => a + b, 0) / lats.length;
  const k = Math.cos((meanLat * Math.PI) / 180);
  const xs = route.map(([, lon]) => lon * k);
  const ys = lats;
  const [minX, maxX] = [Math.min(...xs), Math.max(...xs)];
  const [minY, maxY] = [Math.min(...ys), Math.max(...ys)];
  const spanX = maxX - minX || 1e-9;
  const spanY = maxY - minY || 1e-9;
  const scale = Math.min((width - 2 * pad) / spanX, (height - 2 * pad) / spanY);
  const offsetX = (width - spanX * scale) / 2;
  const offsetY = (height - spanY * scale) / 2;
  const xy = route.map((_, i): [number, number] => [
    Math.round((offsetX + (xs[i] - minX) * scale) * 10) / 10,
    Math.round((offsetY + (maxY - ys[i]) * scale) * 10) / 10,
  ]);
  return {
    points: xy.map(([x, y]) => `${x},${y}`).join(' '),
    start: xy[0],
    end: xy[xy.length - 1],
  };
}
