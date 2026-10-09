import type { UserSettings } from './api';

export type Theme = UserSettings['theme'];

export const THEME_COLORS: Record<Theme, { void: string; abyss: string; shadow: string }> = {
  dark: { void: '#0A0A0F', abyss: '#12121A', shadow: '#1A1A24' },
  darker: { void: '#050508', abyss: '#0A0A0F', shadow: '#12121A' },
  abyss: { void: '#000000', abyss: '#050508', shadow: '#0A0A0F' },
};

/** Writes a theme's background colors to the CSS variables. */
export function applyTheme(theme: Theme): void {
  const colors = THEME_COLORS[theme];
  const root = document.documentElement;
  root.style.setProperty('--color-void', colors.void);
  root.style.setProperty('--color-abyss', colors.abyss);
  root.style.setProperty('--color-shadow', colors.shadow);
  document.body.style.backgroundColor = colors.void;
}
