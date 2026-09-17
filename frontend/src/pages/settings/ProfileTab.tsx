import { Field, Input, Select } from '@/components/ui';
import type { SettingsTabProps } from './types';

export function ProfileTab({ settings, updateSetting }: SettingsTabProps) {
  return (
    <div className="space-y-6">
      <h2 className="text-lg font-sans text-text-primary mb-4">PROFIL</h2>

      <div className="space-y-4">
        <Field label="Nom affiché">
          <Input
            type="text"
            value={settings.display_name}
            onChange={(e) => updateSetting('display_name', e.target.value)}
          />
        </Field>

        <Field label="Adresse e-mail">
          <Input
            type="email"
            value={settings.email ?? ''}
            onChange={(e) => updateSetting('email', e.target.value || null)}
          />
        </Field>

        <Field label="Fuseau horaire">
          <Select value={settings.timezone} onChange={(e) => updateSetting('timezone', e.target.value)}>
            <option value="Europe/Paris">Europe/Paris (CET)</option>
            <option value="Europe/London">Europe/London (GMT)</option>
            <option value="America/New_York">America/New_York (EST)</option>
            <option value="America/Los_Angeles">America/Los_Angeles (PST)</option>
          </Select>
        </Field>
      </div>
    </div>
  );
}
