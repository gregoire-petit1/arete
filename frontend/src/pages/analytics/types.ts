export const PERIODS = ['7d', '30d', '90d', '6m', '1y', 'all'] as const;
export type Period = (typeof PERIODS)[number];

export interface ChartProps {
  period: Period;
}
