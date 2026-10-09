import { useEffect, useLayoutEffect, type ReactNode } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { settingsApi } from '@/lib/api';

import { applyTheme, cacheTheme } from '@/lib/theme';

/** Applies the user's theme (from /settings) to the CSS variables. */
export function SettingsProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  useEffect(() => {
    if (typeof BroadcastChannel === 'undefined') return;
    const channel = new BroadcastChannel('arete-preferences');
    channel.onmessage = () => {
      client.invalidateQueries({ queryKey: ['game-preference'] });
      client.invalidateQueries({ queryKey: ['settings'] });
      client.invalidateQueries({ queryKey: ['game'] });
    };
    return () => channel.close();
  }, [client]);
  const { data: settings } = useQuery({
    queryKey: ['settings'],
    queryFn: settingsApi.get,
  });

  useLayoutEffect(() => {
    if (settings?.theme) {
      applyTheme(settings.theme);
      cacheTheme(settings.theme);
    }
  }, [settings?.theme]);

  return <>{children}</>;
}
