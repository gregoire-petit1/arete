import { cn } from '@/lib/utils';
import type { UserSettings } from '@/lib/api';
import { Field } from '@/components/ui';
import type { SettingsTabProps } from './types';

const DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'];
const DAY_LABEL: Record<string, string> = {
  monday: 'LUN',
  tuesday: 'MAR',
  wednesday: 'MER',
  thursday: 'JEU',
  friday: 'VEN',
  saturday: 'SAM',
  sunday: 'DIM',
};
const GOALS = [
  { value: 'maintenance', label: 'MAINTIEN', desc: 'Garder le niveau actuel' },
  { value: 'build', label: 'CONSTRUCTION', desc: 'Monter la charge progressivement' },
  { value: 'peak', label: 'AFFÛTAGE', desc: 'Être au pic le jour J' },
  { value: 'recovery', label: 'RÉCUPÉRATION', desc: 'Phase de récupération active' },
];

export function GoalsTab({ settings, updateSetting }: SettingsTabProps) {
  return (
    <div className="space-y-6">
      <h2 className="text-lg font-sans text-text-primary mb-4">OBJECTIFS</h2>

      <div className="space-y-6">
        <div>
          <label className="text-xs font-mono text-text-muted uppercase block mb-3">Objectif principal</label>
          <div className="grid grid-cols-2 gap-3">
            {GOALS.map((goal) => (
              <button
                key={goal.value}
                type="button"
                onClick={() => updateSetting('fitness_goal', goal.value as UserSettings['fitness_goal'])}
                className={cn(
                  'p-4 rounded border text-left transition-all',
                  settings.fitness_goal === goal.value
                    ? 'bg-neon-cyan/10 border-neon-cyan/50 text-neon-cyan'
                    : 'bg-abyss border-text-muted/20 text-text-muted hover:border-text-muted/40'
                )}
              >
                <div className="font-mono text-sm mb-1">{goal.label}</div>
                <div className="text-xs opacity-70 font-mono">{goal.desc}</div>
              </button>
            ))}
          </div>
        </div>

        <Field label="Séances par semaine visées">
          <div className="flex items-center gap-4">
            <input
              type="range"
              min="1"
              max="14"
              value={settings.weekly_training_goal}
              onChange={(e) => updateSetting('weekly_training_goal', parseInt(e.target.value))}
              className="flex-1"
            />
            <span className="text-xl font-mono text-neon-cyan w-12 text-center">
              {settings.weekly_training_goal}
            </span>
          </div>
        </Field>

        <div>
          <label className="text-xs font-mono text-text-muted uppercase block mb-3">Jours de repos préférés</label>
          <div className="flex flex-wrap gap-2">
            {DAYS.map((day) => (
              <button
                key={day}
                type="button"
                onClick={() => {
                  const current = settings.rest_day_preference;
                  const updated = current.includes(day)
                    ? current.filter((d) => d !== day)
                    : [...current, day];
                  updateSetting('rest_day_preference', updated);
                }}
                className={cn(
                  'px-3 py-1.5 rounded text-xs font-mono uppercase transition-all',
                  settings.rest_day_preference.includes(day)
                    ? 'bg-neon-purple/20 text-neon-purple border border-neon-purple/30'
                    : 'bg-abyss text-text-muted border border-text-muted/20 hover:border-text-muted/40'
                )}
              >
                {DAY_LABEL[day]}
              </button>
            ))}
          </div>
        </div>

        <Field
          label="Seuil de préparation (%)"
          hint="Au-dessus de ce score, le conseil du jour propose une séance dure"
        >
          <div className="flex items-center gap-4">
            <input
              type="range"
              min="50"
              max="100"
              value={settings.fatigue_threshold}
              onChange={(e) => updateSetting('fatigue_threshold', parseInt(e.target.value))}
              className="flex-1"
            />
            <span className="text-xl font-mono text-warning-orange w-12 text-center">
              {settings.fatigue_threshold}
            </span>
          </div>
        </Field>
      </div>
    </div>
  );
}
