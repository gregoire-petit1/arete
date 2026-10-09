import { useLayoutEffect, type ReactNode } from 'react';
import { useQuery } from '@tanstack/react-query';
import { settingsApi } from '@/lib/api';

import { applyTheme, cacheTheme } from '@/lib/theme';

/** Applies the user's theme (from /settings) to the CSS variables. */
export function SettingsProvider({ children }: { children: ReactNode }) {
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
