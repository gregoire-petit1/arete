import { Component, type ErrorInfo, type ReactNode } from 'react';
import { CartesianGrid, Tooltip } from 'recharts';
import type { TooltipProps } from 'recharts';
import { CHART } from '@/lib/chartTheme';

// ── recharts defaults shared by every chart ───────────────

/** Props for XAxis / YAxis: theme stroke. */
export const AXIS = { stroke: CHART.axis } as const;
export const TICK_SM = { fontSize: 12 } as const;

/** `label` prop for an axis, in theme colors. */
export function axisLabel(
  value: string,
  position: 'insideLeft' | 'insideBottom',
  extra: Record<string, number> = {}
) {
  return {
    value,
    position,
    fill: CHART.label,
    fontSize: 10,
    ...(position === 'insideLeft' ? { angle: -90 } : { offset: -5 }),
    ...extra,
  };
}

export function ChartGrid() {
  return <CartesianGrid strokeDasharray="3 3" stroke={CHART.grid} />;
}

export const TOOLTIP_STYLE = {
  backgroundColor: CHART.surface,
  border: `1px solid ${CHART.grid}`,
  color: CHART.text,
} as const;

/** recharts Tooltip with the theme content style pre-applied. */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function ChartTooltip(props: TooltipProps<any, any>) {
  return <Tooltip contentStyle={TOOLTIP_STYLE} {...props} />;
}

/** Container for custom tooltip content. */
export function TooltipBox({ children }: { children: ReactNode }) {
  return (
    <div className="bg-chart-surface border border-chart-grid p-2 text-xs text-chart-text rounded">
      {children}
    </div>
  );
}

// ── Error boundary per card ───────────────────────────────

class ChartErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null as Error | null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ChartErrorBoundary]', error, info.componentStack);
  }

  render() {
    if (this.state.error) {
      return (
        <div className="h-[300px] flex flex-col items-center justify-center gap-2 text-center px-4">
          <span className="text-danger-red font-mono text-xs uppercase tracking-wider">Chart error</span>
          <span className="text-text-muted text-xs font-mono">{this.state.error.message}</span>
          <button
            type="button"
            onClick={() => this.setState({ error: null })}
            className="mt-2 px-3 py-1 text-xs font-mono bg-neon-cyan/10 text-neon-cyan border border-neon-cyan/30 rounded hover:bg-neon-cyan/20 transition-colors"
          >
            [RETRY]
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

// ── Card ──────────────────────────────────────────────────

interface ChartCardProps {
  title: string;
  children: ReactNode;
  loading?: boolean;
  error?: boolean;
  empty?: boolean;
  emptyMessage?: string;
  onRetry?: () => void;
}

export function ChartCard({
  title,
  children,
  loading,
  error,
  empty,
  emptyMessage = 'No data for this period',
  onRetry,
}: ChartCardProps) {
  return (
    <div className="bg-abyss rounded-lg border border-text-muted/20 p-4">
      <h3 className="text-sm font-mono text-neon-cyan mb-3 uppercase tracking-wider">{title}</h3>
      {loading ? (
        <div className="h-[300px] flex items-center justify-center text-text-muted animate-pulse">Loading...</div>
      ) : error ? (
        <div className="h-[300px] flex flex-col items-center justify-center gap-2 text-danger-red text-sm font-mono">
          FAILED TO LOAD
          {onRetry && (
            <button type="button" onClick={onRetry} className="text-xs text-neon-cyan hover:underline">
              [RETRY]
            </button>
          )}
        </div>
      ) : empty ? (
        <div className="h-[300px] flex items-center justify-center text-text-muted text-sm text-center px-4">
          {emptyMessage}
        </div>
      ) : (
        <ChartErrorBoundary>{children}</ChartErrorBoundary>
      )}
    </div>
  );
}
