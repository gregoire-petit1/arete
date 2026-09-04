import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Button, Modal } from '@/components/ui';

interface GarminLoginModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSuccess: () => void;
}

const FIELD = 'w-full bg-shadow border border-text-muted/30 rounded px-3 py-2 text-text-primary font-mono';
const LABEL = 'text-xs text-text-muted font-mono uppercase tracking-wider block mb-1';

export function GarminLoginModal({ isOpen, onClose, onSuccess }: GarminLoginModalProps) {
  const queryClient = useQueryClient();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [mfaCode, setMfaCode] = useState('');
  const [needsMfa, setNeedsMfa] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
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
      return data as { needs_mfa?: boolean };
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
    onError: (err) => setError(String(err)),
  });

  const handleClose = () => {
    setEmail('');
    setPassword('');
    setMfaCode('');
    setNeedsMfa(false);
    setShowPassword(false);
    setError(null);
    onClose();
  };

  const handleSubmit = () => {
    setError(null);
    if (needsMfa) loginMutation.mutate({ email: '', password: '', mfa_code: mfaCode });
    else loginMutation.mutate({ email, password });
  };

  const incomplete = needsMfa ? !mfaCode : !email || !password;

  return (
    <Modal open={isOpen} onClose={handleClose} className="max-w-md">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!incomplete && !loginMutation.isPending) handleSubmit();
        }}
      >
      <h2 className="text-lg font-mono text-neon-cyan mb-4">
        GARMIN CONNECT — {needsMfa ? 'MFA Verification' : 'Authentication'}
      </h2>

      {needsMfa ? (
        <>
          <p className="text-sm font-mono text-text-muted mb-6">Enter the MFA code sent to your device.</p>
          <div>
            <label className={LABEL}>[MFA_CODE]</label>
            <input
              type="text"
              value={mfaCode}
              onChange={(e) => setMfaCode(e.target.value)}
              className={`${FIELD} border-neon-cyan/30 text-center text-xl tracking-widest`}
              placeholder="000000"
              maxLength={6}
              autoFocus
            />
          </div>
          <div className="mt-4 p-3 bg-neon-purple/10 border border-neon-purple/30 rounded">
            <p className="text-xs font-mono text-neon-purple">
              &gt; Check Garmin Connect app or email for verification code.
            </p>
          </div>
        </>
      ) : (
        <>
          <p className="text-sm font-mono text-text-muted mb-6">Connect your Garmin account to sync activities.</p>
          <div className="space-y-4">
            <div>
              <label className={LABEL}>[EMAIL]</label>
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className={FIELD}
                placeholder="your@email.com"
                autoComplete="username"
                autoFocus
              />
            </div>
            <div>
              <label className={LABEL}>[PASSWORD]</label>
              <input
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className={FIELD}
                placeholder="••••••••"
                autoComplete="current-password"
              />
              <label className="mt-2 flex items-center gap-2 text-xs font-mono text-text-muted cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={showPassword}
                  onChange={(e) => setShowPassword(e.target.checked)}
                  className="accent-neon-cyan"
                />
                Show password
              </label>
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
        <Button variant="ghost" onClick={handleClose}>
          [CANCEL]
        </Button>
        <Button type="submit" disabled={incomplete} loading={loginMutation.isPending}>
          {loginMutation.isPending ? 'VERIFYING...' : needsMfa ? '[VERIFY]' : '[CONNECT]'}
        </Button>
      </div>
      </form>
    </Modal>
  );
}
