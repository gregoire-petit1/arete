import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import {
  RefreshCw,
  Server,
  Database,
  Brain,
  Cloud,
  CheckCircle,
  XCircle,
  LogOut,
  Download,
  Copy,
} from 'lucide-react';
import { FitDropzone, LoadingState, SystemAlert } from '@/components';
import { garminApi, healthApi, ragApi } from '@/lib/api';
import { cn, formatDuration } from '@/lib/utils';

export function MatrixPage() {
  const queryClient = useQueryClient();
  const [showLoginModal, setShowLoginModal] = useState(false);
  const [needsMfa, setNeedsMfa] = useState(false);
  const [alert, setAlert] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Queries
  const { data: health, isLoading: healthLoading, refetch: refetchHealth } = useQuery({
    queryKey: ['health'],
    queryFn: healthApi.check,
    retry: false,
  });

  const { data: syncStatus, isLoading: syncLoading, refetch: refetchSync } = useQuery({
    queryKey: ['syncStatus'],
    queryFn: garminApi.getSyncStatus,
    refetchInterval: 30000,
    retry: false,
  });

  const { data: collections } = useQuery({
    queryKey: ['ragCollections'],
    queryFn: ragApi.getCollections,
    retry: false,
  });

  // Mutations
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
        // MFA required - keep modal open, switch to MFA step
        setNeedsMfa(true);
        setAlert({ type: 'success', message: 'MFA CODE REQUIRED - CHECK YOUR DEVICE' });
      } else {
        setShowLoginModal(false);
        setNeedsMfa(false);
        setAlert({ type: 'success', message: 'GARMIN CONNECT AUTHENTICATED' });
        queryClient.invalidateQueries({ queryKey: ['syncStatus'] });
      }
    },
    onError: (error) => {
      setAlert({ type: 'error', message: `LOGIN FAILED: ${error}` });
    },
  });

  const logoutMutation = useMutation({
    mutationFn: garminApi.logout,
    onSuccess: () => {
      setAlert({ type: 'success', message: 'LOGGED OUT' });
      queryClient.invalidateQueries({ queryKey: ['syncStatus'] });
    },
  });

  const syncMutation = useMutation({
    mutationFn: (options: { start_date?: string; end_date?: string; download_fit?: boolean; max_activities?: number }) =>
      garminApi.syncActivities(options),
    onSuccess: (result) => {
      setAlert({ type: 'success', message: `SYNCED ${result.synced} ACTIVITIES` });
      queryClient.invalidateQueries({ queryKey: ['syncStatus'] });
      queryClient.invalidateQueries({ queryKey: ['actual'] });
    },
    onError: (error) => {
      setAlert({ type: 'error', message: `SYNC FAILED: ${error}` });
    },
  });

  const seedMutation = useMutation({
    mutationFn: ragApi.seedKnowledgeBase,
    onSuccess: () => {
      setAlert({ type: 'success', message: 'KNOWLEDGE BASE SEEDED' });
      queryClient.invalidateQueries({ queryKey: ['ragCollections'] });
    },
  });

  const handleRefresh = () => {
    refetchHealth();
    refetchSync();
    queryClient.invalidateQueries({ queryKey: ['ragCollections'] });
  };

  return (
    <div className="min-h-screen bg-void p-6">
      <div className="max-w-5xl mx-auto">
        {/* Alert */}
        {alert && (
          <motion.div
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            className="mb-4"
          >
            <SystemAlert
              type={alert.type}
              message={alert.message}
              onDismiss={() => setAlert(null)}
            />
          </motion.div>
        )}

        {/* Header */}
        <motion.header
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex justify-between items-center mb-8"
        >
          <h1 className="text-2xl font-display font-bold text-neon-cyan tracking-wider">
            THE MATRIX
          </h1>
          <button
            onClick={handleRefresh}
            className={cn(
              'flex items-center gap-2 px-4 py-2 rounded',
              'bg-abyss border border-text-muted/30',
              'text-text-secondary font-mono text-sm',
              'hover:border-neon-cyan/50 hover:text-neon-cyan transition-all duration-200'
            )}
          >
            <RefreshCw className="w-4 h-4" />
            REFRESH
          </button>
        </motion.header>

        {/* System Status */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass-panel p-4 mb-8"
        >
          <h3 className="text-sm font-mono text-text-muted mb-4 uppercase tracking-wider">
            SYSTEM STATUS
          </h3>
          <div className="space-y-3">
            <StatusRow
              icon={<Server className="w-4 h-4" />}
              label="API Health"
              status={health?.status === 'ok' ? 'online' : healthLoading ? 'loading' : 'offline'}
            />
            <StatusRow
              icon={<Database className="w-4 h-4" />}
              label="DuckDB"
              status={health?.database === 'connected' ? 'online' : 'offline'}
            />
            <StatusRow
              icon={<Brain className="w-4 h-4" />}
              label="ChromaDB (RAG)"
              status={health?.rag === 'connected' ? 'online' : 'offline'}
            />
            <StatusRow
              icon={<Cloud className="w-4 h-4" />}
              label="Garmin Connect"
              status={syncStatus?.garmin_authenticated ? 'online' : syncLoading ? 'loading' : 'offline'}
            />
          </div>
        </motion.div>

        {/* Garmin Sync Center */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.1 }}
          className="glass-panel p-4 mb-8"
        >
          <h3 className="text-sm font-mono text-text-muted mb-4 uppercase tracking-wider">
            GARMIN SYNC CENTER
          </h3>

          {syncStatus?.garmin_authenticated ? (
            <div className="space-y-4">
              {/* Connected status */}
              <div className="p-4 bg-abyss rounded border border-success-green/30">
                <div className="flex items-center justify-between">
                  <div>
                    <div className="text-sm text-success-green font-mono flex items-center gap-2">
                      <CheckCircle className="w-4 h-4" />
                      {syncStatus.user_email ? `Authenticated as ${syncStatus.user_email}` : 'Authenticated'}
                    </div>
                    <div className="text-xs text-text-muted mt-1">
                      Last sync: {syncStatus.last_sync || 'Never'}
                      {' │ '}
                      Activities synced: {syncStatus.activities_synced}
                    </div>
                  </div>
                  <div className="flex gap-2">
                    <button
                      onClick={() => syncMutation.mutate({ max_activities: 50, download_fit: true })}
                      disabled={syncMutation.isPending}
                      className={cn(
                        'px-3 py-1.5 rounded text-xs font-mono',
                        'bg-neon-cyan/10 border border-neon-cyan/30 text-neon-cyan',
                        'hover:bg-neon-cyan/20 transition-all duration-200',
                        syncMutation.isPending && 'opacity-50'
                      )}
                    >
                      {syncMutation.isPending ? 'SYNCING...' : 'SYNC NOW'}
                    </button>
                    <button
                      onClick={() => logoutMutation.mutate()}
                      className="px-3 py-1.5 rounded text-xs font-mono bg-danger-red/10 border border-danger-red/30 text-danger-red hover:bg-danger-red/20 transition-all"
                    >
                      <LogOut className="w-3 h-3" />
                    </button>
                  </div>
                </div>
              </div>

              {/* Sync Options */}
              <SyncOptionsForm onSync={(options) => syncMutation.mutate(options)} isLoading={syncMutation.isPending} />
            </div>
          ) : (
            <div className="space-y-4">
              <div className="p-4 bg-abyss rounded border border-text-muted/30 text-center">
                <XCircle className="w-8 h-8 text-danger-red mx-auto mb-2" />
                <div className="text-sm text-text-muted font-mono">NOT CONNECTED</div>
                <button
                  onClick={() => setShowLoginModal(true)}
                  className="mt-4 px-4 py-2 rounded text-sm font-mono bg-neon-cyan/10 border border-neon-cyan/30 text-neon-cyan hover:bg-neon-cyan/20 transition-all"
                >
                  [CONNECT]
                </button>
              </div>
            </div>
          )}

          {/* Divider */}
          <div className="my-6 flex items-center gap-4">
            <div className="flex-1 h-px bg-text-muted/20" />
            <span className="text-xs text-text-muted font-mono">OR</span>
            <div className="flex-1 h-px bg-text-muted/20" />
          </div>

          {/* Manual Upload */}
          <FitDropzone onUpload={async () => {}} />
        </motion.div>

        {/* Knowledge Base */}
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.2 }}
          className="glass-panel p-4 mb-8"
        >
          <h3 className="text-sm font-mono text-text-muted mb-4 uppercase tracking-wider">
            KNOWLEDGE BASE
          </h3>
          <table className="w-full text-sm font-mono">
            <thead>
              <tr className="text-text-muted text-left">
                <th className="pb-2">Collection</th>
                <th className="pb-2">Documents</th>
              </tr>
            </thead>
            <tbody>
              {collections?.collections.map((name) => (
                <tr key={name} className="border-t border-text-muted/10">
                  <td className="py-2 text-text-primary">{name}</td>
                  <td className="py-2 text-text-secondary">
                    {collections.document_counts[name] || 0}
                  </td>
                </tr>
              )) || (
                <tr>
                  <td colSpan={2} className="py-4 text-center text-text-muted">
                    No collections found
                  </td>
                </tr>
              )}
            </tbody>
          </table>
          <div className="mt-4 flex gap-2">
            <button
              onClick={() => seedMutation.mutate()}
              disabled={seedMutation.isPending}
              className="px-3 py-1.5 rounded text-xs font-mono bg-neon-purple/10 border border-neon-purple/30 text-neon-purple hover:bg-neon-purple/20 transition-all"
            >
              {seedMutation.isPending ? 'SEEDING...' : '[SEED KB]'}
            </button>
          </div>
        </motion.div>

        {/* Login Modal */}
        {showLoginModal && (
          <LoginModal
            onClose={() => {
              setShowLoginModal(false);
              setNeedsMfa(false);
            }}
            onLogin={(creds) => loginMutation.mutate(creds)}
            isLoading={loginMutation.isPending}
            needsMfa={needsMfa}
          />
        )}
      </div>
    </div>
  );
}

function StatusRow({
  icon,
  label,
  status,
  detail,
}: {
  icon: React.ReactNode;
  label: string;
  status: 'online' | 'offline' | 'loading';
  detail?: string;
}) {
  return (
    <div className="flex items-center gap-3">
      <span className="text-text-muted">{icon}</span>
      <span className="text-text-secondary flex-1">{label}</span>
      <div className="flex items-center gap-2">
        {status === 'loading' ? (
          <div className="w-3 h-3 rounded-full bg-warning-orange animate-pulse" />
        ) : status === 'online' ? (
          <div className="w-3 h-3 rounded-full bg-success-green" />
        ) : (
          <div className="w-3 h-3 rounded-full bg-danger-red" />
        )}
        <span
          className={cn(
            'text-xs font-mono uppercase',
            status === 'online' && 'text-success-green',
            status === 'offline' && 'text-danger-red',
            status === 'loading' && 'text-warning-orange'
          )}
        >
          {status === 'loading' ? 'CHECKING' : status.toUpperCase()}
        </span>
        {detail && (
          <span className="text-xs text-text-muted ml-2">({detail})</span>
        )}
      </div>
    </div>
  );
}

function SyncOptionsForm({
  onSync,
  isLoading,
}: {
  onSync: (options: { start_date?: string; end_date?: string; download_fit?: boolean; max_activities?: number }) => void;
  isLoading: boolean;
}) {
  const [days, setDays] = useState(30);
  const [downloadFit, setDownloadFit] = useState(true);
  const [maxActivities, setMaxActivities] = useState(50);

  const handleSync = () => {
    const startDate = new Date();
    startDate.setDate(startDate.getDate() - days);
    onSync({
      start_date: startDate.toISOString().split('T')[0],
      download_fit: downloadFit,
      max_activities: maxActivities,
    });
  };

  return (
    <div className="p-4 bg-abyss rounded border border-text-muted/20">
      <div className="grid grid-cols-2 gap-4 text-sm">
        <div>
          <label className="text-xs text-text-muted font-mono block mb-1">
            📅 Date range
          </label>
          <select
            value={days}
            onChange={(e) => setDays(Number(e.target.value))}
            className="w-full bg-shadow border border-text-muted/30 rounded px-2 py-1 text-text-primary font-mono"
          >
            <option value={7}>Last 7 days</option>
            <option value={30}>Last 30 days</option>
            <option value={90}>Last 90 days</option>
            <option value={365}>Last year</option>
          </select>
        </div>
        <div>
          <label className="text-xs text-text-muted font-mono block mb-1">
            📊 Max activities
          </label>
          <input
            type="number"
            value={maxActivities}
            onChange={(e) => setMaxActivities(Number(e.target.value))}
            className="w-full bg-shadow border border-text-muted/30 rounded px-2 py-1 text-text-primary font-mono"
          />
        </div>
        <div className="col-span-2 flex items-center gap-2">
          <input
            type="checkbox"
            id="downloadFit"
            checked={downloadFit}
            onChange={(e) => setDownloadFit(e.target.checked)}
            className="accent-neon-cyan"
          />
          <label htmlFor="downloadFit" className="text-xs text-text-muted font-mono">
            ⬇️ Download FIT files
          </label>
        </div>
      </div>
      <button
        onClick={handleSync}
        disabled={isLoading}
        className={cn(
          'mt-4 w-full px-4 py-2 rounded text-sm font-mono',
          'bg-neon-cyan/10 border border-neon-cyan/30 text-neon-cyan',
          'hover:bg-neon-cyan/20 transition-all duration-200',
          isLoading && 'opacity-50'
        )}
      >
        {isLoading ? 'SYNCING...' : '[START SYNC]'}
      </button>
    </div>
  );
}

function LoginModal({
  onClose,
  onLogin,
  isLoading,
  needsMfa,
}: {
  onClose: () => void;
  onLogin: (creds: { email: string; password: string; mfa_code?: string }) => void;
  isLoading: boolean;
  needsMfa: boolean;
}) {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [mfaCode, setMfaCode] = useState('');

  const handleSubmit = () => {
    if (needsMfa) {
      onLogin({ email: '', password: '', mfa_code: mfaCode });
    } else {
      onLogin({ email, password });
    }
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      className="fixed inset-0 bg-void/80 backdrop-blur-sm flex items-center justify-center z-50"
      onClick={onClose}
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

        <div className="mt-6 flex gap-3 justify-end">
          <button
            onClick={onClose}
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
