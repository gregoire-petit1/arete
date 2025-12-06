import { motion } from 'framer-motion';
import { Loader2, AlertTriangle, WifiOff } from 'lucide-react';
import { cn } from '@/lib/utils';

interface LoadingStateProps {
  message?: string;
}

export function LoadingState({ message = 'SYNCHRONIZING DATA...' }: LoadingStateProps) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex flex-col items-center justify-center py-12"
    >
      <motion.div
        animate={{ rotate: 360 }}
        transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
      >
        <Loader2 className="w-8 h-8 text-neon-cyan" />
      </motion.div>
      <motion.span
        animate={{ opacity: [1, 0.5, 1] }}
        transition={{ duration: 1.5, repeat: Infinity }}
        className="mt-4 font-mono text-sm text-neon-cyan"
      >
        {message}
      </motion.span>
    </motion.div>
  );
}

interface ErrorStateProps {
  message?: string;
  onRetry?: () => void;
}

export function ErrorState({
  message = 'CONNECTION LOST',
  onRetry,
}: ErrorStateProps) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className="flex flex-col items-center justify-center py-12"
    >
      <div className="p-4 rounded-full bg-danger-red/20 mb-4">
        <WifiOff className="w-8 h-8 text-danger-red" />
      </div>
      <span className="font-mono text-sm text-danger-red mb-2">{message}</span>
      {onRetry && (
        <button
          onClick={onRetry}
          className={cn(
            'mt-4 px-4 py-2 font-mono text-sm',
            'bg-abyss border border-text-muted/30 rounded',
            'hover:border-neon-cyan/50 hover:text-neon-cyan',
            'transition-all duration-200'
          )}
        >
          [RETRY]
        </button>
      )}
    </motion.div>
  );
}

interface EmptyStateProps {
  message?: string;
  action?: string;
}

export function EmptyState({
  message = 'NO DATA AVAILABLE',
  action,
}: EmptyStateProps) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="flex flex-col items-center justify-center py-12 text-center"
    >
      <div className="p-4 rounded-full bg-shadow mb-4">
        <AlertTriangle className="w-8 h-8 text-text-muted" />
      </div>
      <span className="font-mono text-sm text-text-muted">{message}</span>
      {action && (
        <span className="mt-2 text-xs text-text-muted/70">{action}</span>
      )}
    </motion.div>
  );
}

interface SystemAlertProps {
  type: 'info' | 'warning' | 'error' | 'success';
  message: string;
  onDismiss?: () => void;
}

const alertStyles = {
  info: {
    bg: 'bg-neon-cyan/10',
    border: 'border-neon-cyan/30',
    text: 'text-neon-cyan',
  },
  warning: {
    bg: 'bg-warning-orange/10',
    border: 'border-warning-orange/30',
    text: 'text-warning-orange',
  },
  error: {
    bg: 'bg-danger-red/10',
    border: 'border-danger-red/30',
    text: 'text-danger-red',
  },
  success: {
    bg: 'bg-success-green/10',
    border: 'border-success-green/30',
    text: 'text-success-green',
  },
};

export function SystemAlert({ type, message, onDismiss }: SystemAlertProps) {
  const styles = alertStyles[type];

  return (
    <motion.div
      initial={{ opacity: 0, y: -10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      className={cn(
        'flex items-center justify-between p-3 rounded border',
        styles.bg,
        styles.border
      )}
    >
      <span className={cn('font-mono text-sm', styles.text)}>{message}</span>
      {onDismiss && (
        <button
          onClick={onDismiss}
          className={cn('ml-4 text-xs hover:underline', styles.text)}
        >
          [DISMISS]
        </button>
      )}
    </motion.div>
  );
}
