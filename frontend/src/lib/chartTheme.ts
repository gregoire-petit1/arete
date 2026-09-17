/**
 * Static mirror of the `@theme` colors in `src/index.css`.
 *
 * recharts (and inline SVG `style` props) need literal color strings, not
 * Tailwind classes. Keep both files in sync when changing a color.
 */
export const COLORS = {
  void: '#0A0A0F',
  abyss: '#12121A',
  shadow: '#1A1A24',
  neonCyan: '#00F0FF',
  neonPurple: '#9D4EDD',
  neonGold: '#FFD700',
  successGreen: '#00FF88',
  warningOrange: '#FF8C00',
  dangerRed: '#FF3B3B',
  infoBlue: '#3B82F6',
  textPrimary: '#E8E8E8',
  textSecondary: '#A0A0A0',
  textMuted: '#8A8A93',
  strava: '#FC4C02',
} as const;

export const CHART = {
  surface: '#1A1A2E',
  grid: '#3A3A46',
  axis: '#9A9AA5',
  label: '#8A8A93',
  text: '#E0E0E6',
  blue: '#3B82F6',
  green: '#22C55E',
  yellow: '#EAB308',
  orange: '#F97316',
  red: '#EF4444',
  grey: '#6B7280',
  cyan: COLORS.neonCyan,
  gold: COLORS.neonGold,
  purple: COLORS.neonPurple,
} as const;

/** Traffic-light scale used by several charts (good → bad). */
export const SCALE = {
  good: CHART.green,
  moderate: CHART.yellow,
  bad: CHART.red,
  neutral: CHART.grey,
} as const;

export const HR_ZONE_COLORS = [CHART.blue, CHART.green, CHART.yellow, CHART.orange, CHART.red];

export const SCORE_COLORS: Record<string, string> = {
  excellent: CHART.cyan,
  good: CHART.green,
  moderate: CHART.yellow,
  concerning: CHART.red,
};
