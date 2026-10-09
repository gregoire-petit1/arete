/** CSS variables keep SVG charts, tooltips and legends in sync with the active theme. */
export const COLORS = {
  void: 'var(--color-void)',
  abyss: 'var(--color-abyss)',
  shadow: 'var(--color-shadow)',
  neonCyan: 'var(--color-neon-cyan)',
  neonPurple: 'var(--color-neon-purple)',
  neonGold: 'var(--color-neon-gold)',
  successGreen: 'var(--color-success-green)',
  warningOrange: 'var(--color-warning-orange)',
  dangerRed: 'var(--color-danger-red)',
  infoBlue: 'var(--color-info-blue)',
  textPrimary: 'var(--color-text-primary)',
  textSecondary: 'var(--color-text-secondary)',
  textMuted: 'var(--color-text-muted)',
  strava: 'var(--color-strava)',
} as const;

export const CHART = {
  surface: 'var(--color-chart-surface)',
  grid: 'var(--color-chart-grid)',
  axis: 'var(--color-chart-axis)',
  label: 'var(--color-chart-label)',
  text: 'var(--color-chart-text)',
  blue: 'var(--color-chart-blue)',
  green: 'var(--color-chart-green)',
  yellow: 'var(--color-chart-yellow)',
  orange: 'var(--color-chart-orange)',
  red: 'var(--color-chart-red)',
  grey: 'var(--color-chart-grey)',
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
