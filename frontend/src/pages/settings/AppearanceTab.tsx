import { applyTheme } from '@/lib/theme';
import { cn } from '@/lib/utils';
import type { LocalSettings, SettingsTabProps } from './types';

// Swatches mirror THEME_COLORS.void in lib/theme.ts
const THEMES: { value: LocalSettings['theme']; label: string; color: string }[] = [
  { value: 'dark', label: 'SOMBRE', color: 'bg-[#0A0A0F]' },
  { value: 'darker', label: 'PLUS SOMBRE', color: 'bg-[#050508]' },
  { value: 'abyss', label: 'ABYSSE', color: 'bg-[#000000]' },
];

export function AppearanceTab({ settings, updateSetting }: SettingsTabProps) {
  return (
    <div className="space-y-6">
      <h2 className="text-lg font-sans text-text-primary mb-4">APPARENCE</h2>

      <div>
        <label className="text-xs font-mono text-text-muted uppercase block mb-3">Thème</label>
        <div className="flex gap-3">
          {THEMES.map((theme) => (
            <button
              key={theme.value}
              type="button"
              onClick={() => {
                // Preview at once; Settings restores the saved theme if this is not saved.
                applyTheme(theme.value);
                updateSetting('theme', theme.value);
              }}
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
    </div>
  );
}
