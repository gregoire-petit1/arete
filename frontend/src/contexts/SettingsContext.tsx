import { useEffect, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { settingsApi } from '@/lib/api';

const THEME_COLORS = {
  dark: { void: '#0A0A0F', abyss: '#12121A', shadow: '#1A1A24' },
  darker: { void: '#050508', abyss: '#0A0A0F', shadow: '#12121A' },
  abyss: { void: '#000000', abyss: '#050508', shadow: '#0A0A0F' },
} as const;

/** Applies the user's theme (from /settings) to the CSS variables. */
export function SettingsProvider({ children }: { children: ReactNode }) {
  const { data: settings } = useQuery({
    queryKey: ['settings'],
    queryFn: settingsApi.get,
  });

  useEffect(() => {
    if (settings?.theme) {
      const colors = THEME_COLORS[settings.theme];
      const root = document.documentElement;
      root.style.setProperty('--color-void', colors.void);
      root.style.setProperty('--color-abyss', colors.abyss);
      root.style.setProperty('--color-shadow', colors.shadow);
      document.body.style.backgroundColor = colors.void;
    }
  }, [settings?.theme]);

  return <>{children}</>;
}
