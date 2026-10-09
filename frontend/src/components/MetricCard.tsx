import { Minus, TrendingDown, TrendingUp } from 'lucide-react';
import { type ZoneKind, zoneLabel } from '@/lib/fr';
import { cn, getZoneColor } from '@/lib/utils';

interface MetricCardProps {
  title: string;
  value: number | string;
  kind: ZoneKind;
  zone: string | null | undefined;
  subtitle?: string;
  trend?: 'up' | 'down' | 'stable';
}

// Glow shadows use the theme colors (success-green, warning-orange, danger-red, neon-cyan) at 30%.
const zoneColorMap = {
  green: {
    border: 'border-success-green/50',
    badge: 'bg-success-green/20 text-success-green',
    glow: 'hover:shadow-[0_0_20px_rgba(0,255,136,0.3)]',
  },
  orange: {
    border: 'border-warning-orange/50',
    badge: 'bg-warning-orange/20 text-warning-orange',
    glow: 'hover:shadow-[0_0_20px_rgba(255,140,0,0.3)]',
  },
  red: {
    border: 'border-danger-red/50',
    badge: 'bg-danger-red/20 text-danger-red',
    glow: 'hover:shadow-[0_0_20px_rgba(255,59,59,0.3)]',
  },
  cyan: {
    border: 'border-neon-cyan/50',
    badge: 'bg-neon-cyan/20 text-neon-cyan',
    glow: 'hover:shadow-[0_0_20px_rgba(0,240,255,0.3)]',
  },
};

export function MetricCard({ title, value, kind, zone, subtitle, trend }: MetricCardProps) {
  const zoneColor = getZoneColor(kind, zone);
  const colors = zoneColorMap[zoneColor];
  const TrendIcon = trend === 'up' ? TrendingUp : trend === 'down' ? TrendingDown : Minus;

  return (
    <div
      className={cn(
        'glass-panel p-4 transition-all duration-300 hover:scale-[1.02] animate-fade-up',
        colors.border,
        colors.glow
      )}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-xs font-mono text-text-muted uppercase tracking-wider">{title}</span>
        {trend && (
          <TrendIcon
            className={cn(
              'w-4 h-4',
              trend === 'up' && 'text-success-green',
              trend === 'down' && 'text-danger-red',
              trend === 'stable' && 'text-text-muted'
            )}
          />
        )}
      </div>

      <div className="text-3xl font-mono font-bold text-text-primary mb-2">{value}</div>

      <div
        className={cn('inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-mono uppercase', colors.badge)}
      >
        {zoneLabel(kind, zone)}
        {zoneColor === 'green' && ' ✓'}
        {zoneColor === 'red' && ' ⚠'}
      </div>

      {subtitle && <div className="mt-2 text-xs text-text-muted">{subtitle}</div>}
    </div>
  );
}
