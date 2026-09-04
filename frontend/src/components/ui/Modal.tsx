import { useEffect, useState, type ReactNode } from 'react';
import { X } from 'lucide-react';
import { cn } from '@/lib/utils';

const EXIT_MS = 150;

interface ModalProps {
  open: boolean;
  onClose: () => void;
  children: ReactNode;
  /** Extra classes for the panel (width, max height...). */
  className?: string;
}

/**
 * Overlay + glass panel with CSS enter/exit transitions.
 * Stays mounted for EXIT_MS after `open` turns false so the exit animation plays.
 */
export function Modal({ open, onClose, children, className }: ModalProps) {
  // "Adjust state when a prop changes" pattern: detect the open -> closed edge during render.
  const [prevOpen, setPrevOpen] = useState(open);
  const [exiting, setExiting] = useState(false);
  if (open !== prevOpen) {
    setPrevOpen(open);
    if (!open) setExiting(true);
  }

  useEffect(() => {
    if (!exiting) return;
    const t = setTimeout(() => setExiting(false), EXIT_MS);
    return () => clearTimeout(t);
  }, [exiting]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);

  if (!open && !exiting) return null;
  const closing = !open;

  return (
    <div
      className={cn(
        'fixed inset-0 bg-void/80 backdrop-blur-sm z-50 flex items-center justify-center p-4',
        closing ? 'animate-fade-out' : 'animate-fade-in'
      )}
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        className={cn(
          'glass-panel p-6 w-full',
          closing ? 'animate-scale-out' : 'animate-scale-in',
          className
        )}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  );
}

interface ModalHeaderProps {
  title: ReactNode;
  icon?: ReactNode;
  /** Tailwind text color class for the title (default text-neon-cyan). */
  tone?: string;
  onClose?: () => void;
  className?: string;
}

export function ModalHeader({ title, icon, tone = 'text-neon-cyan', onClose, className }: ModalHeaderProps) {
  return (
    <div className={cn('flex items-center justify-between mb-6', className)}>
      <div className={cn('flex items-center gap-2', tone)}>
        {icon}
        <h3 className="text-lg font-sans">{title}</h3>
      </div>
      {onClose && (
        <button
          type="button"
          onClick={onClose}
          aria-label="Close"
          className="p-1 hover:bg-text-muted/20 rounded transition-colors"
        >
          <X className="w-5 h-5 text-text-muted" />
        </button>
      )}
    </div>
  );
}
