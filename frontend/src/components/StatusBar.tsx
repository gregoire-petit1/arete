import { motion } from 'framer-motion';
import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface StatusBarProps {
  label: string;
  current: number;
  max: number;
  color: 'cyan' | 'purple' | 'gold' | 'green' | 'red';
  icon?: ReactNode;
  subtitle?: string;
  showPercentage?: boolean;
}

const colorMap = {
  cyan: {
    bar: 'bg-neon-cyan',
    text: 'text-neon-cyan',
    glow: 'shadow-[0_0_10px_rgba(0,240,255,0.5)]',
  },
  purple: {
    bar: 'bg-neon-purple',
    text: 'text-neon-purple',
    glow: 'shadow-[0_0_10px_rgba(157,78,221,0.5)]',
  },
  gold: {
    bar: 'bg-neon-gold',
    text: 'text-neon-gold',
    glow: 'shadow-[0_0_10px_rgba(255,215,0,0.5)]',
  },
  green: {
    bar: 'bg-success-green',
    text: 'text-success-green',
    glow: 'shadow-[0_0_10px_rgba(0,255,136,0.5)]',
  },
  red: {
    bar: 'bg-danger-red',
    text: 'text-danger-red',
    glow: 'shadow-[0_0_10px_rgba(255,59,59,0.5)]',
  },
};

export function StatusBar({
  label,
  current,
  max,
  color,
  icon,
  subtitle,
  showPercentage = true,
}: StatusBarProps) {
  const percentage = Math.min(100, Math.max(0, (current / max) * 100));
  const colors = colorMap[color];

  return (
    <motion.div
      initial={{ opacity: 0, x: -20 }}
      animate={{ opacity: 1, x: 0 }}
      className="flex items-center gap-2 sm:gap-4"
    >
      {/* Label */}
      <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
        {icon && <span className={colors.text}>{icon}</span>}
        <span className={cn('font-mono font-bold text-xs sm:text-sm', colors.text)}>{label}</span>
      </div>

      {/* Bar container */}
      <div className="flex-1 min-w-0 relative">
        <div className="h-3 sm:h-4 bg-shadow rounded-sm overflow-hidden border border-text-muted/20">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${percentage}%` }}
            transition={{ duration: 0.8, ease: 'easeOut' }}
            className={cn('h-full', colors.bar, colors.glow)}
          />
        </div>
      </div>

      {/* Values — compact on mobile */}
      <div className="shrink-0 text-right">
        <span className="font-mono text-xs sm:text-sm text-text-primary">
          <span className="hidden sm:inline">{current.toLocaleString()}/{max.toLocaleString()}</span>
          <span className="sm:hidden">{percentage.toFixed(0)}%</span>
        </span>
        {showPercentage && (
          <span className="hidden sm:inline font-mono text-xs text-text-muted ml-2">
            ({percentage.toFixed(0)}%)
          </span>
        )}
      </div>

      {/* Subtitle — hidden on mobile */}
      {subtitle && (
        <span className="hidden md:inline text-xs text-text-muted font-mono shrink-0">
          {subtitle}
        </span>
      )}
    </motion.div>
  );
}
