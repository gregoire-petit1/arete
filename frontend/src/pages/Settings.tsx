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
  Terminal,
  RefreshCw,
  Server,
  Brain,
  Cloud,
  CheckCircle,
  XCircle,
  LogOut,
} from 'lucide-react';
import { cn } from '@/lib/utils';
import { LoadingState, GarminLoginModal, SystemAlert } from '@/components';
import { settingsApi, garminApi, healthApi, ragApi, type UserSettings } from '@/lib/api';

const TABS = [
  { id: 'profile', label: 'PROFILE', icon: User },
  { id: 'goals', label: 'GOALS', icon: Target },
  { id: 'connections', label: 'CONNECTIONS', icon: Watch },
  { id: 'data', label: 'DATA', icon: Database },
  { id: 'appearance', label: 'APPEARANCE', icon: Palette },
  { id: 'system', label: 'SYSTEM', icon: Terminal },
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
            {activeTab === 'connections' && (
              <ConnectionsTab onGoToSystem={() => setActiveTab('system')} />
            )}
            {activeTab === 'data' && <DataTab />}
            {activeTab === 'appearance' && (
              <AppearanceTab settings={settings} updateSetting={updateSetting} />
            )}
            {activeTab === 'system' && <SystemTab />}
          </motion.div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Sub-components (module-level)
// ---------------------------------------------------------------------------

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

function ConnectionsTab({ onGoToSystem }: { onGoToSystem: () => void }) {
  const { data: syncStatus } = useQuery({
    queryKey: ['garminSyncStatus'],
    queryFn: async () => {
      const res = await fetch('/api/garmin/sync/status');
      if (!res.ok) return null;
      return res.json();
    },
  });

  const connections = [
    {
      id: 'garmin',
      name: 'Garmin Connect',
      icon: Watch,
      status: syncStatus?.garmin_authenticated ? 'connected' : 'disconnected',
      email: syncStatus?.user_email || null,
    },
    {
      id: 'runalyze',
      name: 'Runalyze',
      icon: Database,
      status: 'disconnected',
      email: null,
    },
    {
      id: 'strava',
      name: 'Strava',
      icon: Target,
      status: 'disconnected',
      email: null,
    },
  ];

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-display text-text-primary mb-4">CONNECTED SERVICES</h2>

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
            </div>
            {conn.status === 'connected' ? (
              <div className="flex items-center gap-1 text-xs text-success-green">
                <Check className="w-4 h-4" />
                Connected
              </div>
            ) : (
              <span className="text-xs font-mono text-text-muted">
                {conn.id === 'garmin' ? 'Not connected' : 'Coming Soon'}
              </span>
            )}
          </div>
        ))}
      </div>

      <button
        onClick={onGoToSystem}
        className={cn(
          'w-full px-4 py-3 rounded text-sm font-mono',
          'bg-neon-cyan/10 border border-neon-cyan/30 text-neon-cyan',
          'hover:bg-neon-cyan/20 transition-all'
        )}
      >
        Manage connections in System tab
      </button>
    </div>
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

// ---------------------------------------------------------------------------
// System tab (absorbed from Matrix.tsx)
// ---------------------------------------------------------------------------

function SystemTab() {
  const queryClient = useQueryClient();
  const [showLoginModal, setShowLoginModal] = useState(false);
  const [alert, setAlert] = useState<{ type: 'success' | 'error'; message: string } | null>(null);

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
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-display text-text-primary">SYSTEM</h2>
        <button
          onClick={handleRefresh}
          className={cn(
            'flex items-center gap-2 px-3 py-1.5 rounded',
            'bg-abyss border border-text-muted/30',
            'text-text-secondary font-mono text-xs',
            'hover:border-neon-cyan/50 hover:text-neon-cyan transition-all duration-200'
          )}
        >
          <RefreshCw className="w-3 h-3" />
          REFRESH
        </button>
      </div>

      {/* Alert */}
      {alert && (
        <motion.div
          initial={{ opacity: 0, y: -10 }}
          animate={{ opacity: 1, y: 0 }}
        >
          <SystemAlert
            type={alert.type}
            message={alert.message}
            onDismiss={() => setAlert(null)}
          />
        </motion.div>
      )}

      {/* System Status */}
      <div className="p-4 bg-abyss/50 rounded border border-text-muted/20">
        <h3 className="text-xs font-mono text-text-muted mb-3 uppercase tracking-wider">
          STATUS
        </h3>
        <div className="space-y-2">
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
      </div>

      {/* Garmin Sync Center */}
      <div className="p-4 bg-abyss/50 rounded border border-text-muted/20">
        <h3 className="text-xs font-mono text-text-muted mb-3 uppercase tracking-wider">
          GARMIN SYNC CENTER
        </h3>

        {syncStatus?.garmin_authenticated ? (
          <div className="space-y-4">
            <div className="p-3 rounded border border-success-green/30">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm text-success-green font-mono flex items-center gap-2">
                    <CheckCircle className="w-4 h-4" />
                    {syncStatus.user_email ? `Authenticated as ${syncStatus.user_email}` : 'Authenticated'}
                  </div>
                  <div className="text-xs text-text-muted mt-1 font-mono">
                    Last sync: {syncStatus.last_sync || 'Never'}
                    {' | '}
                    Activities: {syncStatus.activities_synced}
                  </div>
                </div>
                <div className="flex gap-2">
                  <button
                    onClick={() => syncMutation.mutate({ max_activities: 50, download_fit: true })}
                    disabled={syncMutation.isPending}
                    className={cn(
                      'px-3 py-1.5 rounded text-xs font-mono',
                      'bg-neon-cyan/10 border border-neon-cyan/30 text-neon-cyan',
                      'hover:bg-neon-cyan/20 transition-all',
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

            <SyncOptionsForm onSync={(options) => syncMutation.mutate(options)} isLoading={syncMutation.isPending} />
          </div>
        ) : (
          <div className="p-4 rounded border border-text-muted/30 text-center">
            <XCircle className="w-6 h-6 text-danger-red mx-auto mb-2" />
            <div className="text-sm text-text-muted font-mono">NOT CONNECTED</div>
            <button
              onClick={() => setShowLoginModal(true)}
              className="mt-3 px-4 py-2 rounded text-sm font-mono bg-neon-cyan/10 border border-neon-cyan/30 text-neon-cyan hover:bg-neon-cyan/20 transition-all"
            >
              [CONNECT]
            </button>
          </div>
        )}
      </div>

      {/* Knowledge Base */}
      <div className="p-4 bg-abyss/50 rounded border border-text-muted/20">
        <h3 className="text-xs font-mono text-text-muted mb-3 uppercase tracking-wider">
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
            {collections?.collections.map((name: string) => (
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
        <button
          onClick={() => seedMutation.mutate()}
          disabled={seedMutation.isPending}
          className="mt-3 px-3 py-1.5 rounded text-xs font-mono bg-neon-purple/10 border border-neon-purple/30 text-neon-purple hover:bg-neon-purple/20 transition-all"
        >
          {seedMutation.isPending ? 'SEEDING...' : '[SEED KB]'}
        </button>
      </div>

      {/* Login Modal */}
      <GarminLoginModal
        isOpen={showLoginModal}
        onClose={() => setShowLoginModal(false)}
        onSuccess={() => {
          setShowLoginModal(false);
          setAlert({ type: 'success', message: 'GARMIN CONNECT AUTHENTICATED' });
          queryClient.invalidateQueries({ queryKey: ['syncStatus'] });
        }}
      />
    </div>
  );
}

function StatusRow({
  icon,
  label,
  status,
}: {
  icon: React.ReactNode;
  label: string;
  status: 'online' | 'offline' | 'loading';
}) {
  return (
    <div className="flex items-center gap-3">
      <span className="text-text-muted">{icon}</span>
      <span className="text-text-secondary font-mono flex-1">{label}</span>
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
    <div className="p-3 rounded border border-text-muted/20">
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <label className="text-xs text-text-muted font-mono block mb-1">Date range</label>
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
          <label className="text-xs text-text-muted font-mono block mb-1">Max activities</label>
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
            id="systemDownloadFit"
            checked={downloadFit}
            onChange={(e) => setDownloadFit(e.target.checked)}
            className="accent-neon-cyan"
          />
          <label htmlFor="systemDownloadFit" className="text-xs text-text-muted font-mono">
            Download FIT files
          </label>
        </div>
      </div>
      <button
        onClick={handleSync}
        disabled={isLoading}
        className={cn(
          'mt-3 w-full px-4 py-2 rounded text-sm font-mono',
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
