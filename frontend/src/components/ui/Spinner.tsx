import { cn } from '@/lib/utils';

interface SpinnerProps {
  className?: string;
}

/** Ring spinner in the current text color. */
export function Spinner({ className }: SpinnerProps) {
  return (
    <span
      aria-hidden
      className={cn(
        'inline-block w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin',
        className
      )}
    />
  );
}
