import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import { cn } from '@/lib/utils';

interface GarminLoginModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

export function GarminLoginModal({ isOpen, onClose, onSuccess }: GarminLoginModalProps) {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [mfaCode, setMfaCode] = useState('');
  const [needsMfa, setNeedsMfa] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loginMutation = useMutation({
    mutationFn: async (credentials: { email: string; password: string; mfa_code?: string }) => {
      const res = await fetch('/api/garmin/sync/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(credentials),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Login failed');
      return data;
    },
    onSuccess: (data) => {
      if (data.needs_mfa) {
        setNeedsMfa(true);
        setError(null);
      } else {
        queryClient.invalidateQueries({ queryKey: ['syncStatus'] });
        handleClose();
        onSuccess();
      }
    },
    onError: (err) => {
      setError(String(err));
    },
  });

  const handleClose = () => {
    setEmail('');
    setPassword('');
    setMfaCode('');
    setNeedsMfa(false);
    setError(null);
    onClose();
  };

  const handleSubmit = () => {
    setError(null);
    if (needsMfa) {
      loginMutation.mutate({ email: '', password: '', mfa_code: mfaCode });
    } else {
      loginMutation.mutate({ email, password });
    }
  };

  if (!isOpen) return null;

  const isLoading = loginMutation.isPending;

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="fixed inset-0 bg-void/80 backdrop-blur-sm flex items-center justify-center z-50"
      onClick={handleClose}
    >
      <motion.div
        initial={{ scale: 0.95 }}
        animate={{ scale: 1 }}
        className="glass-panel p-6 w-full max-w-md"
        onClick={(e) => e.stopPropagation()}
      >
        <h2 className="text-lg font-mono text-neon-cyan mb-4">
          GARMIN CONNECT — {needsMfa ? 'MFA Verification' : 'Authentication'}
        </h2>

        {needsMfa ? (
          <>
            <p className="text-sm font-mono text-text-muted mb-6">
              Enter the MFA code sent to your device.
            </p>
            <div className="space-y-4">
              <div>
                <label className="text-xs text-text-muted font-mono uppercase tracking-wider block mb-1">
                  [MFA_CODE]
                </label>
                <input
                  type="text"
                  value={mfaCode}
                  onChange={(e) => setMfaCode(e.target.value)}
                  className="w-full bg-shadow border border-neon-cyan/30 rounded px-3 py-2 text-text-primary font-mono text-center text-xl tracking-widest"
                  placeholder="000000"
                  maxLength={6}
                  autoFocus
                />
              </div>
            </div>
            <div className="mt-4 p-3 bg-neon-purple/10 border border-neon-purple/30 rounded">
              <p className="text-xs font-mono text-neon-purple">
                &gt; Check Garmin Connect app or email for verification code.
              </p>
            </div>
          </>
        ) : (
          <>
            <p className="text-sm font-mono text-text-muted mb-6">
              Connect your Garmin account to sync activities.
            </p>
            <div className="space-y-4">
              <div>
                <label className="text-xs text-text-muted font-mono uppercase tracking-wider block mb-1">
                  [EMAIL]
                </label>
                <input
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full bg-shadow border border-text-muted/30 rounded px-3 py-2 text-text-primary font-mono"
                  placeholder="your@email.com"
                />
              </div>
              <div>
                <label className="text-xs text-text-muted font-mono uppercase tracking-wider block mb-1">
                  [PASSWORD]
                </label>
                <input
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full bg-shadow border border-text-muted/30 rounded px-3 py-2 text-text-primary font-mono"
                  placeholder="••••••••"
                />
              </div>
            </div>
            <div className="mt-4 p-3 bg-warning-orange/10 border border-warning-orange/30 rounded">
              <p className="text-xs font-mono text-warning-orange">
                &gt; Credentials used once. Only session tokens stored.
              </p>
            </div>
          </>
        )}

        {error && (
          <div className="mt-4 p-3 bg-danger-red/10 border border-danger-red/30 rounded">
            <p className="text-xs font-mono text-danger-red">&gt; {error}</p>
          </div>
        )}

        <div className="mt-6 flex gap-3 justify-end">
          <button
            onClick={handleClose}
            className="px-4 py-2 rounded text-sm font-mono text-text-muted hover:text-text-primary transition-colors"
          >
            [CANCEL]
          </button>
          <button
            onClick={handleSubmit}
            disabled={isLoading || (needsMfa ? !mfaCode : !email || !password)}
            className={cn(
              'px-4 py-2 rounded text-sm font-mono',
              'bg-neon-cyan/10 border border-neon-cyan/30 text-neon-cyan',
              'hover:bg-neon-cyan/20 transition-all duration-200',
              (isLoading || (needsMfa ? !mfaCode : !email || !password)) && 'opacity-50'
            )}
          >
            {isLoading ? 'VERIFYING...' : needsMfa ? '[VERIFY]' : '[CONNECT]'}
          </button>
        </div>
      </motion.div>
    </motion.div>
  );
}
