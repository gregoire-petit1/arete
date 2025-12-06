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
      className="flex items-center gap-4"
    >
      {/* Label */}
      <div className="flex items-center gap-2 min-w-[60px]">
        {icon && <span className={colors.text}>{icon}</span>}
        <span className={cn('font-mono font-bold text-sm', colors.text)}>{label}</span>
      </div>

      {/* Bar container */}
      <div className="flex-1 relative">
        <div className="h-4 bg-shadow rounded-sm overflow-hidden border border-text-muted/20">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${percentage}%` }}
            transition={{ duration: 0.8, ease: 'easeOut' }}
            className={cn('h-full', colors.bar, colors.glow)}
          />
        </div>
      </div>

      {/* Values */}
      <div className="w-[160px] text-right shrink-0">
        <span className="font-mono text-sm text-text-primary">
          {current.toLocaleString()}/{max.toLocaleString()}
        </span>
        {showPercentage && (
          <span className="font-mono text-xs text-text-muted ml-2">
            ({percentage.toFixed(0)}%)
          </span>
        )}
      </div>

      {/* Subtitle */}
      {subtitle && (
        <span className="text-xs text-text-muted font-mono w-[100px] text-right shrink-0">
          {subtitle}
        </span>
      )}
    </motion.div>
  );
}
