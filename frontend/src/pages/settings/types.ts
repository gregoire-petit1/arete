import type { UserSettings } from '@/lib/api';

export type LocalSettings = Omit<UserSettings, 'user_id'>;

export interface SettingsTabProps {
  settings: LocalSettings;
  updateSetting: <K extends keyof LocalSettings>(key: K, value: LocalSettings[K]) => void;
}

export const DEFAULT_SETTINGS: LocalSettings = {
  display_name: 'Athlète',
  email: null,
  timezone: 'Europe/Paris',
  weekly_training_goal: 6,
  rest_day_preference: ['monday'],
  fatigue_threshold: 85,
  fitness_goal: 'build',
  notifications_enabled: true,
  coach_briefing_enabled: true,
  auto_adapt_enabled: true,
  push_to_garmin_enabled: false,
  theme: 'dark',
  exercise_abbreviations: {},
  weekly_volume_target_kg: 20000,
  lthr: null,
  max_hr: null,
  threshold_pace_sec_km: null,
  lthr_measured_on: null,
};
