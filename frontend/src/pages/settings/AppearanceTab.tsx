import { cn } from '@/lib/utils';
import type { SettingsTabProps } from './types';
import { THEMES } from '@/lib/theme';
import { AreteWordmark } from '@/components/AreteBrand';

export function AppearanceTab({ settings, updateSetting }: SettingsTabProps) {
  return (
    <div className="space-y-6">
      <h2 className="text-lg font-sans text-text-primary mb-4">APPARENCE</h2>

      <div>
        <label className="text-xs font-mono text-text-muted uppercase block mb-3">Thème</label>
        <div className="flex flex-wrap gap-3" role="group" aria-label="Thème">
          {THEMES.map((theme) => (
            <button
              key={theme.value}
              type="button"
              aria-pressed={settings.theme === theme.value}
              onClick={() => updateSetting('theme', theme.value)}
              className={cn(
                'flex flex-col items-center gap-3 p-3 rounded-xl border transition-colors',
                settings.theme === theme.value
                  ? 'border-neon-cyan/50'
                  : 'border-text-muted/20 hover:border-text-muted/40'
              )}
            >
              {theme.value === 'pierre' || theme.value === 'prune' ? (
                <div className="flex h-24 w-44 items-center justify-center rounded-lg" style={{ backgroundColor: theme.color, color: theme.value === 'pierre' ? '#1C2927' : '#F2E8DA' }} aria-hidden="true">
                  <AreteWordmark />
                </div>
              ) : <div className="w-16 h-10 rounded border border-text-muted/20" style={{ backgroundColor: theme.color }} />}
              <span className="text-xs font-mono text-text-muted">{theme.label}</span>
            </button>
          ))}
        </div>
        <p className="mt-3 text-xs text-text-secondary">Aperçu immédiat. Enregistre pour conserver ce thème.</p>
      </div>
    </div>
  );
}
