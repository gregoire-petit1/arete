import { createContext, useContext, useEffect, type ReactNode } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { settingsApi, type UserSettings } from '@/lib/api';

interface SettingsContextType {
  settings: UserSettings | null;
  isLoading: boolean;
  updateSettings: (settings: Omit<UserSettings, 'user_id'>) => Promise<void>;
}

const SettingsContext = createContext<SettingsContextType | null>(null);

const THEME_COLORS = {
  dark: {
    void: '#0A0A0F',
    abyss: '#12121A',
    shadow: '#1A1A24',
  },
  darker: {
    void: '#050508',
    abyss: '#0A0A0F',
    shadow: '#12121A',
  },
  abyss: {
    void: '#000000',
    abyss: '#050508',
    shadow: '#0A0A0F',
  },
} as const;

export function SettingsProvider({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient();

  const { data: settings, isLoading } = useQuery({
    queryKey: ['settings'],
    queryFn: settingsApi.get,
    staleTime: 1000 * 60 * 5, // 5 minutes
  });

  const mutation = useMutation({
    mutationFn: settingsApi.update,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings'] });
    },
  });

  // Apply theme when settings change
  useEffect(() => {
    if (settings?.theme) {
      const colors = THEME_COLORS[settings.theme];
      const root = document.documentElement;
      
      root.style.setProperty('--color-void', colors.void);
      root.style.setProperty('--color-abyss', colors.abyss);
      root.style.setProperty('--color-shadow', colors.shadow);
      
      // Also update body background
      document.body.style.backgroundColor = colors.void;
    }
  }, [settings?.theme]);

  const updateSettings = async (newSettings: Omit<UserSettings, 'user_id'>) => {
    await mutation.mutateAsync(newSettings);
  };

  return (
    <SettingsContext.Provider value={{ settings: settings ?? null, isLoading, updateSettings }}>
      {children}
    </SettingsContext.Provider>
  );
}

export function useSettings() {
  const context = useContext(SettingsContext);
  if (!context) {
    throw new Error('useSettings must be used within a SettingsProvider');
  }
  return context;
}
