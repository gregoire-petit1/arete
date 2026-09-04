/**
 * Single source of truth for sport → icon / Tailwind class / chart color.
 *
 * Backend sport strings vary by source (Garmin: `running`, `strength_training`;
 * Strava: `run`, `ride`, `trail_run`, `virtual_ride`, `weight_training`).
 * Everything is first normalized to a `SportFamily`.
 */
import type { ComponentType } from 'react';
import {
  CycleIcon,
  HikeIcon,
  OtherIcon,
  RestIcon,
  RowIcon,
  RunIcon,
  StrengthIcon,
  SwimIcon,
  WalkIcon,
  YogaIcon,
  type SportIconProps,
} from '@/components/SportIcons';
import { CHART, COLORS } from '@/lib/chartTheme';

export type SportFamily =
  | 'running'
  | 'cycling'
  | 'swimming'
  | 'strength'
  | 'walking'
  | 'hiking'
  | 'rowing'
  | 'yoga'
  | 'rest'
  | 'other';

export function sportFamily(sport: string | null | undefined): SportFamily {
  const s = (sport ?? '').toLowerCase();
  if (s.includes('run')) return 'running';
  if (s.includes('row')) return 'rowing';
  if (s.includes('strength') || s.includes('weight') || s.includes('gym')) return 'strength';
  if (s.includes('cycl') || s.includes('bike') || s.includes('ride')) return 'cycling';
  if (s.includes('swim')) return 'swimming';
  if (s.includes('yoga') || s.includes('mobil') || s.includes('stretch')) return 'yoga';
  if (s.includes('hik')) return 'hiking';
  if (s.includes('walk')) return 'walking';
  if (s.includes('rest') || s.includes('recovery')) return 'rest';
  return 'other';
}

interface SportStyle {
  icon: ComponentType<SportIconProps>;
  /** Tailwind text color class */
  text: string;
  /** Literal color for recharts / inline SVG */
  hex: string;
}

const SPORT_STYLES: Record<SportFamily, SportStyle> = {
  running: { icon: RunIcon, text: 'text-neon-cyan', hex: COLORS.neonCyan },
  cycling: { icon: CycleIcon, text: 'text-warning-orange', hex: COLORS.warningOrange },
  swimming: { icon: SwimIcon, text: 'text-info-blue', hex: COLORS.infoBlue },
  strength: { icon: StrengthIcon, text: 'text-neon-purple', hex: COLORS.neonPurple },
  walking: { icon: WalkIcon, text: 'text-success-green', hex: COLORS.successGreen },
  hiking: { icon: HikeIcon, text: 'text-success-green', hex: COLORS.successGreen },
  rowing: { icon: RowIcon, text: 'text-neon-purple', hex: COLORS.neonPurple },
  yoga: { icon: YogaIcon, text: 'text-neon-purple', hex: COLORS.neonPurple },
  rest: { icon: RestIcon, text: 'text-text-muted', hex: COLORS.textMuted },
  other: { icon: OtherIcon, text: 'text-neon-gold', hex: CHART.grey },
};

export function getSportIconComponent(sport: string | null | undefined): ComponentType<SportIconProps> {
  return SPORT_STYLES[sportFamily(sport)].icon;
}

/** Tailwind text color class for a sport. */
export function getSportColor(sport: string | null | undefined): string {
  return SPORT_STYLES[sportFamily(sport)].text;
}

/** Literal hex color for a sport (recharts fills/strokes). */
export function getSportHex(sport: string | null | undefined): string {
  return SPORT_STYLES[sportFamily(sport)].hex;
}
