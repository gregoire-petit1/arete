import { useMemo, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Bot, Check, Dumbbell, Palette, Save, Target, Terminal, User, Watch, X } from 'lucide-react';
import { cn } from '@/lib/utils';
import { ErrorState, LoadingState } from '@/components';
import { Button, Spinner } from '@/components/ui';
import { settingsApi, type UserSettings } from '@/lib/api';
import {
  AppearanceTab,
  CoachTab,
  ConnectionsTab,
  DEFAULT_SETTINGS,
  GoalsTab,
  ProfileTab,
  SystemTab,
  WorkoutTab,
  type LocalSettings,
} from './settings/index';

const TABS = [
  { id: 'profile', label: 'PROFIL', icon: User },
  { id: 'goals', label: 'OBJECTIFS', icon: Target },
  { id: 'workout', label: 'NOTATION', icon: Dumbbell },
  { id: 'connections', label: 'CONNEXIONS', icon: Watch },
  { id: 'coach', label: 'COACH', icon: Bot },
  { id: 'appearance', label: 'APPARENCE', icon: Palette },
  { id: 'system', label: 'SYSTÈME', icon: Terminal },
] as const;

type TabId = (typeof TABS)[number]['id'];
type SaveStatus = 'idle' | 'saving' | 'saved' | 'error';

export function SettingsPage() {
  const [activeTab, setActiveTab] = useState<TabId>('profile');
  const queryClient = useQueryClient();

  const { data: savedSettings, isLoading, isError, refetch } = useQuery({
    queryKey: ['settings'],
    queryFn: settingsApi.get,
  });

  const [settings, setSettings] = useState<LocalSettings>(DEFAULT_SETTINGS);

  // Adopt fetched settings into local form state whenever the server copy changes
  const [syncedFrom, setSyncedFrom] = useState<UserSettings | null>(null);
  if (savedSettings && savedSettings !== syncedFrom) {
    setSyncedFrom(savedSettings);
    const { user_id, ...rest } = savedSettings;
    setSettings(rest);
  }

  const [saveStatus, setSaveStatus] = useState<SaveStatus>('idle');

  const hasChanges = useMemo(() => {
    if (!savedSettings) return false;
    const { user_id, ...saved } = savedSettings;
    return JSON.stringify(saved) !== JSON.stringify(settings);
  }, [settings, savedSettings]);

  const saveMutation = useMutation({
    mutationFn: settingsApi.update,
    onMutate: () => setSaveStatus('saving'),
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

  const updateSetting = <K extends keyof LocalSettings>(key: K, value: LocalSettings[K]) => {
    setSettings((prev) => ({ ...prev, [key]: value }));
  };

  if (isLoading) {
    return (
      <div className="min-h-screen bg-void p-6 flex items-center justify-center">
        <LoadingState message="CHARGEMENT DES RÉGLAGES…" />
      </div>
    );
  }

  if (isError) {
    return <ErrorState message="RÉGLAGES INDISPONIBLES" onRetry={() => refetch()} />;
  }

  const tabProps = { settings, updateSetting };

  return (
    <div className="min-h-screen bg-void p-6">
      <div className="max-w-4xl mx-auto">
        <header className="flex justify-between items-center mb-8 animate-fade-down">
          <h1 className="text-2xl font-sans font-bold text-text-primary tracking-wider">RÉGLAGES</h1>
          {hasChanges && (
            <Button
              variant="green"
              strong
              onClick={() => saveMutation.mutate(settings)}
              disabled={saveStatus === 'saving'}
              className="animate-scale-in"
            >
              <SaveStatusContent status={saveStatus} />
            </Button>
          )}
        </header>

        <div className="flex gap-6">
          <nav className="w-48 shrink-0 animate-fade-left">
            <div className="space-y-1">
              {TABS.map((tab) => (
                <button
                  key={tab.id}
                  type="button"
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
          </nav>

          <div key={activeTab} className="flex-1 glass-panel p-6 animate-fade-up">
            {activeTab === 'profile' && <ProfileTab {...tabProps} />}
            {activeTab === 'goals' && <GoalsTab {...tabProps} />}
            {activeTab === 'workout' && <WorkoutTab {...tabProps} />}
            {activeTab === 'connections' && <ConnectionsTab />}
            {activeTab === 'coach' && <CoachTab />}
            {activeTab === 'appearance' && <AppearanceTab {...tabProps} />}
            {activeTab === 'system' && <SystemTab />}
          </div>
        </div>
      </div>
    </div>
  );
}

function SaveStatusContent({ status }: { status: SaveStatus }) {
  switch (status) {
    case 'saving':
      return (
        <>
          <Spinner />
          ENREGISTREMENT…
        </>
      );
    case 'saved':
      return (
        <>
          <Check className="w-4 h-4" />
          ENREGISTRÉ
        </>
      );
    case 'error':
      return (
        <>
          <X className="w-4 h-4 text-danger-red" />
          ÉCHEC
        </>
      );
    default:
      return (
        <>
          <Save className="w-4 h-4" />
          ENREGISTRER
        </>
      );
  }
}
