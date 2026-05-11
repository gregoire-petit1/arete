import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { motion } from 'framer-motion';
import {
  User,
  Target,
  Watch,
  Database,
  Bell,
  Palette,
  Download,
  Save,
  Check,
  X,
  AlertTriangle,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { LoadingState } from '@/components';
import { settingsApi, type UserSettings } from '@/lib/api';

const TABS = [
  { id: 'profile', label: 'PROFILE', icon: User },
  { id: 'goals', label: 'GOALS', icon: Target },
  { id: 'connections', label: 'CONNECTIONS', icon: Watch },
  { id: 'data', label: 'DATA', icon: Database },
  { id: 'appearance', label: 'APPEARANCE', icon: Palette },
] as const;

type TabId = typeof TABS[number]['id'];

export function SettingsPage() {
  const [activeTab, setActiveTab] = useState<TabId>('profile');
  const queryClient = useQueryClient();

  // Fetch settings from API
  const { data: savedSettings, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: settingsApi.get,
  });

  // Local state for editing
  const [settings, setSettings] = useState<Omit<UserSettings, 'user_id'>>({
    display_name: 'HUNTER',
    email: null,
    timezone: 'Europe/Paris',
    weekly_training_goal: 6,
    rest_day_preference: ['monday'],
    fatigue_threshold: 85,
    fitness_goal: 'build',
    notifications_enabled: true,
    theme: 'dark',
  });

  // Sync local state with fetched settings
  useEffect(() => {
    if (savedSettings) {
      const { user_id, ...rest } = savedSettings;
      setSettings(rest);
    }
  }, [savedSettings]);

  const [hasChanges, setHasChanges] = useState(false);
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle');

  // Check for changes
  useEffect(() => {
    if (savedSettings) {
      const { user_id, ...saved } = savedSettings;
      const changed = JSON.stringify(saved) !== JSON.stringify(settings);
      setHasChanges(changed);
    }
  }, [settings, savedSettings]);

  // Save mutation
  const saveMutation = useMutation({
    mutationFn: settingsApi.update,
    onMutate: () => {
      setSaveStatus('saving');
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
      setSaveStatus('saved');
      setTimeout(() => setSaveStatus('idle'), 2000);
    },
    onError: () => {
      setSaveStatus('error');
      setTimeout(() => setSaveStatus('idle'), 3000);
    },
  });

  const updateSetting = <K extends keyof Omit<UserSettings, 'user_id'>>(
    key: K,
    value: Omit<UserSettings, 'user_id'>[K]
  ) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  const handleSave = () => {
    saveMutation.mutate(settings);
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-void p-6 flex items-center justify-center">
        <LoadingState message="Loading settings..." />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-void p-6">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <motion.header
          initial={{ opacity: 0, y: -20 }}
          animate={{ opacity: 1, y: 0 }}
          className="flex justify-between items-center mb-8"
        >
          <h1 className="text-2xl font-display font-bold text-text-primary tracking-wider">
            SETTINGS
          </h1>
          {hasChanges && (
            <motion.button
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              onClick={handleSave}
              disabled={saveStatus === 'saving'}
              className={cn(
                'flex items-center gap-2 px-4 py-2 rounded',
                'bg-success-green/20 border border-success-green/30',
                'text-success-green font-mono text-sm',
                'hover:bg-success-green/30 transition-all',
                'disabled:opacity-50 disabled:cursor-not-allowed'
              )}
            >
              {saveStatus === 'saving' ? (
                <>
                  <div className="w-4 h-4 border-2 border-success-green border-t-transparent rounded-full animate-spin" />
                  SAVING...
                </>
              ) : saveStatus === 'saved' ? (
                <>
                  <Check className="w-4 h-4" />
                  SAVED!
                </>
              ) : saveStatus === 'error' ? (
                <>
                  <X className="w-4 h-4 text-danger-red" />
                  ERROR
                </>
              ) : (
                <>
                  <Save className="w-4 h-4" />
                  SAVE CHANGES
                </>
              )}
            </motion.button>
          )}
        </motion.header>

        <div className="flex gap-6">
          {/* Sidebar */}
          <motion.nav
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            className="w-48 shrink-0"
          >
            <div className="space-y-1">
              {TABS.map((tab) => (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={cn(
                    'w-full flex items-center gap-3 px-4 py-3 rounded',
                    'text-sm font-mono transition-all text-left',
                    activeTab === tab.id
                      ? 'bg-neon-cyan/10 text-neon-cyan border border-neon-cyan/30'
                      : 'text-text-muted hover:text-text-secondary hover:bg-abyss'
                  )}
                >
                  <tab.icon className="w-4 h-4" />
                  {tab.label}
                </button>
              ))}
            </div>
          </motion.nav>

          {/* Content */}
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            className="flex-1 glass-panel p-6"
          >
            {activeTab === 'profile' && (
              <ProfileTab settings={settings} updateSetting={updateSetting} />
            )}
            {activeTab === 'goals' && (
              <GoalsTab settings={settings} updateSetting={updateSetting} />
            )}
            {activeTab === 'connections' && <ConnectionsTab />}
            {activeTab === 'data' && <DataTab />}
            {activeTab === 'appearance' && (
              <AppearanceTab settings={settings} updateSetting={updateSetting} />
            )}
          </motion.div>
        </div>
      </div>
    </div>
  );
}

type LocalSettings = Omit<UserSettings, 'user_id'>;

function ProfileTab({
  settings,
  updateSetting,
}: {
  settings: LocalSettings;
  updateSetting: <K extends keyof LocalSettings>(key: K, value: LocalSettings[K]) => void;
}) {
  return (
    <div className="space-y-6">
      <h2 className="text-lg font-display text-text-primary mb-4">PROFILE SETTINGS</h2>

      <div className="space-y-4">
        <div>
          <label className="text-xs font-mono text-text-muted uppercase block mb-2">
            Display Name
          </label>
          <input
            type="text"
            value={settings.display_name}
            onChange={(e) => updateSetting('display_name', e.target.value)}
            className={cn(
              'w-full bg-abyss border border-text-muted/30 rounded px-4 py-2',
              'text-text-primary font-mono',
              'focus:border-neon-cyan/50 outline-none transition-colors'
            )}
          />
        </div>

        <div>
          <label className="text-xs font-mono text-text-muted uppercase block mb-2">
            Email
          </label>
          <input
            type="email"
            value={settings.email ?? ''}
            onChange={(e) => updateSetting('email', e.target.value || null)}
            className={cn(
              'w-full bg-abyss border border-text-muted/30 rounded px-4 py-2',
              'text-text-primary font-mono',
              'focus:border-neon-cyan/50 outline-none transition-colors'
            )}
          />
        </div>

        <div>
          <label className="text-xs font-mono text-text-muted uppercase block mb-2">
            Timezone
          </label>
          <select
            value={settings.timezone}
            onChange={(e) => updateSetting('timezone', e.target.value)}
            className={cn(
              'w-full bg-abyss border border-text-muted/30 rounded px-4 py-2',
              'text-text-primary font-mono',
              'focus:border-neon-cyan/50 outline-none transition-colors'
            )}
          >
            <option value="Europe/Paris">Europe/Paris (CET)</option>
            <option value="Europe/London">Europe/London (GMT)</option>
            <option value="America/New_York">America/New_York (EST)</option>
            <option value="America/Los_Angeles">America/Los_Angeles (PST)</option>
          </select>
        </div>
      </div>
    </div>
  );
}

function GoalsTab({
  settings,
  updateSetting,
}: {
  settings: LocalSettings;
  updateSetting: <K extends keyof LocalSettings>(key: K, value: LocalSettings[K]) => void;
}) {
  const DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];
  const GOALS = [
    { value: 'maintenance', label: 'MAINTENANCE', desc: 'Maintain current fitness' },
    { value: 'build', label: 'BUILD', desc: 'Progressive overload' },
    { value: 'peak', label: 'PEAK', desc: 'Peak for event' },
    { value: 'recovery', label: 'RECOVERY', desc: 'Active recovery phase' },
  ];

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-display text-text-primary mb-4">TRAINING GOALS</h2>

      <div className="space-y-6">
        {/* Fitness Goal */}
        <div>
          <label className="text-xs font-mono text-text-muted uppercase block mb-3">
            Primary Goal
          </label>
          <div className="grid grid-cols-2 gap-3">
            {GOALS.map((goal) => (
              <button
                key={goal.value}
                onClick={() => updateSetting('fitness_goal', goal.value as UserSettings['fitness_goal'])}
                className={cn(
                  'p-4 rounded border text-left transition-all',
                  settings.fitness_goal === goal.value
                    ? 'bg-neon-cyan/10 border-neon-cyan/50 text-neon-cyan'
                    : 'bg-abyss border-text-muted/20 text-text-muted hover:border-text-muted/40'
                )}
              >
                <div className="font-mono text-sm mb-1">{goal.label}</div>
                <div className="text-xs opacity-70 font-mono">{goal.desc}</div>
              </button>
            ))}
          </div>
        </div>

        {/* Weekly Goal */}
        <div>
          <label className="text-xs font-mono text-text-muted uppercase block mb-2">
            Weekly Training Sessions Target
          </label>
          <div className="flex items-center gap-4">
            <input
              type="range"
              min="1"
              max="14"
              value={settings.weekly_training_goal}
              onChange={(e) => updateSetting('weekly_training_goal', parseInt(e.target.value))}
              className="flex-1"
            />
            <span className="text-xl font-mono text-neon-cyan w-12 text-center">
              {settings.weekly_training_goal}
            </span>
          </div>
        </div>

        {/* Rest Days */}
        <div>
          <label className="text-xs font-mono text-text-muted uppercase block mb-3">
            Preferred Rest Days
          </label>
          <div className="flex flex-wrap gap-2">
            {DAYS.map((day) => (
              <button
                key={day}
                onClick={() => {
                  const current = settings.rest_day_preference;
                  const updated = current.includes(day)
                    ? current.filter((d) => d !== day)
                    : [...current, day];
                  updateSetting('rest_day_preference', updated);
                }}
                className={cn(
                  'px-3 py-1.5 rounded text-xs font-mono uppercase transition-all',
                  settings.rest_day_preference.includes(day)
                    ? 'bg-neon-purple/20 text-neon-purple border border-neon-purple/30'
                    : 'bg-abyss text-text-muted border border-text-muted/20 hover:border-text-muted/40'
                )}
              >
                {day.slice(0, 3)}
              </button>
            ))}
          </div>
        </div>

        {/* Fatigue Threshold */}
        <div>
          <label className="text-xs font-mono text-text-muted uppercase block mb-2">
            Fatigue Alert Threshold (%)
          </label>
          <div className="flex items-center gap-4">
            <input
              type="range"
              min="50"
              max="100"
              value={settings.fatigue_threshold}
              onChange={(e) => updateSetting('fatigue_threshold', parseInt(e.target.value))}
              className="flex-1"
            />
            <span className="text-xl font-mono text-warning-orange w-12 text-center">
              {settings.fatigue_threshold}
            </span>
          </div>
          <p className="text-xs text-text-muted mt-1 font-mono">
            System will warn when fatigue exceeds this level
          </p>
        </div>
      </div>
    </div>
  );
}

function ConnectionsTab() {
  const queryClient = useQueryClient();
  const [showLoginModal, setShowLoginModal] = useState(false);
  const [needsMfa, setNeedsMfa] = useState(false);
  const [connectionAlert, setConnectionAlert] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

  // Fetch real Garmin sync status
  const { data: syncStatus } = useQuery({
    queryKey: ['garminSyncStatus'],
    queryFn: async () => {
      const res = await fetch('/api/garmin/sync/status');
      if (!res.ok) return null;
      return res.json();
    },
  });

  // Login mutation
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
        setConnectionAlert({ type: 'success', message: 'MFA code required - check your device' });
      } else {
        setShowLoginModal(false);
        setNeedsMfa(false);
        setConnectionAlert({ type: 'success', message: 'Garmin Connect authenticated!' });
        queryClient.invalidateQueries({ queryKey: ['garminSyncStatus'] });
      }
    },
    onError: (error) => {
      setConnectionAlert({ type: 'error', message: `Login failed: ${error}` });
    },
  });

  // Logout mutation
  const logoutMutation = useMutation({
    mutationFn: async () => {
      const res = await fetch('/api/garmin/sync/logout', { method: 'POST' });
      if (!res.ok) {
        const data = await res.json();
        throw new Error(data.detail || 'Logout failed');
      }
      return res.json();
    },
    onSuccess: () => {
      setConnectionAlert({ type: 'success', message: 'Disconnected from Garmin' });
      queryClient.invalidateQueries({ queryKey: ['garminSyncStatus'] });
    },
    onError: (error) => {
      setConnectionAlert({ type: 'error', message: `Logout failed: ${error}` });
    },
  });

  const formatLastSync = (dateStr: string | null) => {
    if (!dateStr) return null;
    const date = new Date(dateStr);
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60));
    if (diffHours < 1) return 'Just now';
    if (diffHours < 24) return `${diffHours} hours ago`;
    const diffDays = Math.floor(diffHours / 24);
    if (diffDays === 1) return 'Yesterday';
    return `${diffDays} days ago`;
  };

  const handleLogin = (creds: { email: string; password: string; mfa_code?: string }) => {
    loginMutation.mutate(creds);
  };

  const handleDisconnect = (serviceId: string) => {
    if (serviceId === 'garmin') {
      logoutMutation.mutate();
    }
  };

  const connections = [
    {
      id: 'garmin',
      name: 'Garmin Connect',
      icon: Watch,
      status: syncStatus?.garmin_authenticated ? 'connected' : 'disconnected',
      lastSync: formatLastSync(syncStatus?.last_sync),
      email: syncStatus?.user_email || null,
    },
    {
      id: 'runalyze',
      name: 'Runalyze',
      icon: Database,
      status: 'disconnected', // Not implemented yet
      lastSync: null,
    },
    {
      id: 'strava',
      name: 'Strava',
      icon: Target,
      status: 'disconnected',
      lastSync: null,
    },
  ];

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-display text-text-primary mb-4">CONNECTED SERVICES</h2>

      {/* Connection Alert */}
      {connectionAlert && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
          className={cn(
            'p-3 rounded flex items-center justify-between text-sm',
            connectionAlert.type === 'success'
              ? 'bg-success-green/10 border border-success-green/30 text-success-green'
              : 'bg-danger-red/10 border border-danger-red/30 text-danger-red'
          )}
        >
          <span>{connectionAlert.message}</span>
          <button onClick={() => setConnectionAlert(null)} className="hover:opacity-70">
            <X className="w-4 h-4" />
          </button>
        </motion.div>
      )}

      <div className="space-y-3">
        {connections.map((conn) => (
          <div
            key={conn.id}
            className={cn(
              'flex items-center gap-4 p-4 rounded',
              'bg-abyss/50 border',
              conn.status === 'connected' ? 'border-success-green/30' : 'border-text-muted/20'
            )}
          >
            <conn.icon className="w-6 h-6 text-text-muted" />
            <div className="flex-1">
              <div className="font-mono text-sm text-text-primary">{conn.name}</div>
              {conn.email && (
                <div className="text-xs text-neon-cyan">{conn.email}</div>
              )}
              {conn.lastSync && (
                <div className="text-xs text-text-muted">Last sync: {conn.lastSync}</div>
              )}
            </div>
            {conn.status === 'connected' ? (
              <>
                <div className="flex items-center gap-1 text-xs text-success-green">
                  <Check className="w-4 h-4" />
                  Connected
                </div>
                <button
                  onClick={() => handleDisconnect(conn.id)}
                  disabled={logoutMutation.isPending}
                  className="text-xs font-mono text-danger-red hover:underline disabled:opacity-50"
                >
                  {logoutMutation.isPending ? 'Disconnecting...' : 'Disconnect'}
                </button>
              </>
            ) : (
              <button
                onClick={() => conn.id === 'garmin' && setShowLoginModal(true)}
                disabled={conn.id !== 'garmin'}
                className={cn(
                  'px-4 py-1.5 rounded text-xs font-mono',
                  conn.id === 'garmin'
                    ? 'bg-neon-cyan/10 border border-neon-cyan/30 text-neon-cyan hover:bg-neon-cyan/20 transition-all'
                    : 'bg-text-muted/10 border border-text-muted/20 text-text-muted cursor-not-allowed'
                )}
              >
                {conn.id === 'garmin' ? 'Connect' : 'Coming Soon'}
              </button>
            )}
          </div>
        ))}
      </div>

      {/* Login Modal */}
      {showLoginModal && (
        <GarminLoginModal
          onClose={() => {
            setShowLoginModal(false);
            setNeedsMfa(false);
          }}
          onLogin={handleLogin}
          isLoading={loginMutation.isPending}
          needsMfa={needsMfa}
        />
      )}
    </div>
  );
}

// Garmin Login Modal Component
function GarminLoginModal({
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

function DataTab() {
  return (
    <div className="space-y-6">
      <h2 className="text-lg font-display text-text-primary mb-4">DATA MANAGEMENT</h2>

      <div className="space-y-4">
        {/* Export */}
        <div className="p-4 rounded bg-abyss/50 border border-text-muted/20">
          <div className="flex items-center gap-3 mb-2">
            <Download className="w-5 h-5 text-neon-cyan" />
            <div>
              <div className="font-mono text-sm text-text-primary">Export Data</div>
              <div className="text-xs text-text-muted font-mono">Download all your training data</div>
            </div>
          </div>
          <div className="flex gap-2 mt-3">
            <button
              className={cn(
                'px-3 py-1.5 rounded text-xs font-mono',
                'bg-neon-cyan/10 border border-neon-cyan/30 text-neon-cyan',
                'hover:bg-neon-cyan/20 transition-all'
              )}
            >
              Export CSV
            </button>
            <button
              className={cn(
                'px-3 py-1.5 rounded text-xs font-mono',
                'bg-neon-cyan/10 border border-neon-cyan/30 text-neon-cyan',
                'hover:bg-neon-cyan/20 transition-all'
              )}
            >
              Export JSON
            </button>
          </div>
        </div>

        {/* Danger Zone */}
        <div className="p-4 rounded bg-danger-red/5 border border-danger-red/30">
          <div className="flex items-center gap-3 mb-2">
            <AlertTriangle className="w-5 h-5 text-danger-red" />
            <div>
              <div className="font-mono text-sm text-danger-red">Danger Zone</div>
              <div className="text-xs text-text-muted font-mono">Irreversible actions</div>
            </div>
          </div>
          <div className="flex gap-2 mt-3">
            <button
              className={cn(
                'px-3 py-1.5 rounded text-xs font-mono',
                'bg-danger-red/10 border border-danger-red/30 text-danger-red',
                'hover:bg-danger-red/20 transition-all'
              )}
            >
              Clear Cache
            </button>
            <button
              className={cn(
                'px-3 py-1.5 rounded text-xs font-mono',
                'bg-danger-red/10 border border-danger-red/30 text-danger-red',
                'hover:bg-danger-red/20 transition-all'
              )}
            >
              Delete All Data
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

function AppearanceTab({
  settings,
  updateSetting,
}: {
  settings: LocalSettings;
  updateSetting: <K extends keyof LocalSettings>(key: K, value: LocalSettings[K]) => void;
}) {
  const THEMES = [
    { value: 'dark', label: 'DARK', color: 'bg-[#0a0f1a]' },
    { value: 'darker', label: 'DARKER', color: 'bg-[#050810]' },
    { value: 'abyss', label: 'ABYSS', color: 'bg-[#000000]' },
  ];

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-display text-text-primary mb-4">APPEARANCE</h2>

      <div className="space-y-6">
        {/* Theme */}
        <div>
          <label className="text-xs font-mono text-text-muted uppercase block mb-3">
            Theme
          </label>
          <div className="flex gap-3">
            {THEMES.map((theme) => (
              <button
                key={theme.value}
                onClick={() => updateSetting('theme', theme.value as LocalSettings['theme'])}
                className={cn(
                  'flex flex-col items-center gap-2 p-3 rounded border transition-all',
                  settings.theme === theme.value
                    ? 'border-neon-cyan/50'
                    : 'border-text-muted/20 hover:border-text-muted/40'
                )}
              >
                <div className={cn('w-16 h-10 rounded', theme.color)} />
                <span className="text-xs font-mono text-text-muted">{theme.label}</span>
              </button>
            ))}
          </div>
        </div>

        {/* Notifications */}
        <div>
          <label className="text-xs font-mono text-text-muted uppercase block mb-3">
            Notifications
          </label>
          <button
            onClick={() => updateSetting('notifications_enabled', !settings.notifications_enabled)}
            className={cn(
              'flex items-center gap-3 p-4 rounded border w-full',
              settings.notifications_enabled
                ? 'bg-success-green/10 border-success-green/30'
                : 'bg-abyss border-text-muted/20'
            )}
          >
            <Bell
              className={cn(
                'w-5 h-5',
                settings.notifications_enabled ? 'text-success-green' : 'text-text-muted'
              )}
            />
            <div className="flex-1 text-left">
              <div className="font-mono text-sm text-text-primary">Push Notifications</div>
              <div className="text-xs text-text-muted font-mono">Receive alerts and reminders</div>
            </div>
            <div
              className={cn(
                'w-12 h-6 rounded-full transition-all relative',
                settings.notifications_enabled ? 'bg-success-green' : 'bg-text-muted/30'
              )}
            >
              <div
                className={cn(
                  'absolute top-1 w-4 h-4 rounded-full bg-white transition-all',
                  settings.notifications_enabled ? 'left-7' : 'left-1'
                )}
              />
            </div>
          </button>
        </div>
      </div>
    </div>
  );
}
