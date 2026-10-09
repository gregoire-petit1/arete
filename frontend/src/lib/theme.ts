export const THEMES = [
  { value: 'light', label: 'CLAIR', color: '#F4F7FA' },
  { value: 'dark', label: 'SOMBRE', color: '#0A0A0F' },
  { value: 'darker', label: 'PLUS SOMBRE', color: '#050508' },
  { value: 'abyss', label: 'ABYSSE', color: '#000000' },
] as const;

export type Theme = (typeof THEMES)[number]['value'];
const STORAGE_KEY = 'arete.theme.v1';

export function applyTheme(theme: Theme) {
  const selected = THEMES.find((item) => item.value === theme) ?? THEMES[1];
  document.documentElement.dataset.theme = selected.value;
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', selected.color);
}

/** Cache only saved preferences so reloads never restore an abandoned preview. */
export function cacheTheme(theme: Theme) {
  try {
    localStorage.setItem(STORAGE_KEY, theme);
  } catch (error) {
    console.warn('Could not cache the saved theme', error);
  }
}

export function initializeTheme() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    applyTheme(THEMES.find((item) => item.value === saved)?.value ?? 'dark');
  } catch (error) {
    console.warn('Could not read the saved theme', error);
    applyTheme('dark');
  }
}
