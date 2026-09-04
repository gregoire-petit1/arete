import type { UserSettings } from '@/lib/api';

export type LocalSettings = Omit<UserSettings, 'user_id'>;

export interface SettingsTabProps {
  settings: LocalSettings;
  updateSetting: <K extends keyof LocalSettings>(key: K, value: LocalSettings[K]) => void;
}

export const DEFAULT_SETTINGS: LocalSettings = {
  display_name: 'HUNTER',
  email: null,
  timezone: 'Europe/Paris',
  weekly_training_goal: 6,
  rest_day_preference: ['monday'],
  fatigue_threshold: 85,
  fitness_goal: 'build',
  notifications_enabled: true,
  theme: 'dark',
  exercise_abbreviations: {},
};
