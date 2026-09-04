import { cn } from '@/lib/utils';
import type { LocalSettings, SettingsTabProps } from './types';

// Swatches mirror THEME_COLORS.void in contexts/SettingsContext.tsx
const THEMES: { value: LocalSettings['theme']; label: string; color: string }[] = [
  { value: 'dark', label: 'DARK', color: 'bg-[#0A0A0F]' },
  { value: 'darker', label: 'DARKER', color: 'bg-[#050508]' },
  { value: 'abyss', label: 'ABYSS', color: 'bg-[#000000]' },
];

export function AppearanceTab({ settings, updateSetting }: SettingsTabProps) {
  return (
    <div className="space-y-6">
      <h2 className="text-lg font-sans text-text-primary mb-4">APPEARANCE</h2>

      <div>
        <label className="text-xs font-mono text-text-muted uppercase block mb-3">Theme</label>
        <div className="flex gap-3">
          {THEMES.map((theme) => (
            <button
              key={theme.value}
              type="button"
              onClick={() => updateSetting('theme', theme.value)}
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
