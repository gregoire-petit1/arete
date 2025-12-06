import { motion } from 'framer-motion';
import { Signal, AlertTriangle } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useEffect, useState } from 'react';

interface SystemMessageProps {
  title?: string;
  content: string;
  priority?: number;
  actions?: string[];
  isLoading?: boolean;
  warnings?: string[];
  onAccept?: () => void;
}

export function SystemMessage({
  title = 'SYSTÈME DIT :',
  content,
  priority,
  actions,
  isLoading = false,
  warnings,
  onAccept,
}: SystemMessageProps) {
  const [displayedText, setDisplayedText] = useState('');
  const [isTyping, setIsTyping] = useState(true);

  // Typing effect
  useEffect(() => {
    if (isLoading) {
      setDisplayedText('');
      setIsTyping(true);
      return;
    }

    let index = 0;
    setDisplayedText('');
    setIsTyping(true);

    const interval = setInterval(() => {
      if (index < content.length) {
        setDisplayedText(content.slice(0, index + 1));
        index++;
      } else {
        setIsTyping(false);
        clearInterval(interval);
      }
    }, 20);

    return () => clearInterval(interval);
  }, [content, isLoading]);

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      animate={{ opacity: 1, scale: 1 }}
      className="glass-panel border-2 border-neon-purple/50 p-6"
    >
      {/* Header */}
      <div className="flex items-center gap-3 mb-4">
        <motion.div
          animate={isTyping ? { opacity: [1, 0.5, 1] } : { opacity: 1 }}
          transition={{ duration: 1, repeat: isTyping ? Infinity : 0 }}
        >
          <Signal className="w-5 h-5 text-neon-purple" />
        </motion.div>
        <span className="font-mono text-sm text-neon-purple uppercase tracking-wider">
          {isLoading ? '▶ INCOMING TRANSMISSION...' : title}
        </span>
        {priority && priority <= 2 && (
          <span className="px-2 py-0.5 bg-danger-red/20 text-danger-red text-xs font-mono rounded">
            PRIORITY {priority}
          </span>
        )}
      </div>

      {/* Content */}
      <div className="text-text-primary font-mono leading-relaxed min-h-[60px]">
        {isLoading ? (
          <motion.span
            animate={{ opacity: [1, 0.5, 1] }}
            transition={{ duration: 0.8, repeat: Infinity }}
            className="text-text-muted"
          >
            Analyzing data streams...
          </motion.span>
        ) : (
          <>
            {displayedText}
            {isTyping && (
              <motion.span
                animate={{ opacity: [1, 0] }}
                transition={{ duration: 0.5, repeat: Infinity }}
                className="text-neon-cyan"
              >
                ▌
              </motion.span>
            )}
          </>
        )}
      </div>

      {/* Warnings */}
      {warnings && warnings.length > 0 && (
        <div className="mt-4 space-y-2">
          {warnings.map((warning, idx) => (
            <div
              key={idx}
              className="flex items-center gap-2 text-warning-orange text-sm"
            >
              <AlertTriangle className="w-4 h-4" />
              <span>{warning}</span>
            </div>
          ))}
        </div>
      )}

      {/* Actions */}
      {actions && actions.length > 0 && !isTyping && (
        <div className="mt-4 pt-4 border-t border-text-muted/20">
          <div className="text-xs text-text-muted font-mono mb-2">
            SUGGESTED ACTIONS:
          </div>
          <ul className="space-y-1">
            {actions.map((action, idx) => (
              <li
                key={idx}
                className="text-sm text-text-secondary font-mono flex items-center gap-2"
              >
                <span className="text-neon-cyan">›</span>
                {action}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Accept Button */}
      {onAccept && !isTyping && (
        <motion.button
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          whileHover={{ scale: 1.02 }}
          whileTap={{ scale: 0.98 }}
          onClick={onAccept}
          className={cn(
            'mt-4 px-4 py-2 bg-neon-cyan/20 border border-neon-cyan/50',
            'text-neon-cyan font-mono text-sm rounded',
            'hover:bg-neon-cyan/30 hover:shadow-[0_0_20px_rgba(0,240,255,0.3)]',
            'transition-all duration-300'
          )}
        >
          [ACCEPTER QUÊTE]
        </motion.button>
      )}
    </motion.div>
  );
}
