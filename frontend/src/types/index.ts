// ========================= //
// FITNESS & WORKLOAD TYPES //
// ========================= //

export interface StatBar {
  current: number;
  max: number;
  label: string;
  detail: string | null;
  source: string | null;
}

export interface PlayerStats {
  hp: StatBar;
  mp: StatBar;
  xp: StatBar;
  level: number;
  weeks_at_goal: number;
  weekly_goal_tss: number;
}

export interface FitnessMetrics {
  ctl: number;
  atl: number;
  tsb: number;
  form_zone: "fresh" | "optimal" | "grey" | "fatigued" | "exhausted";
  readiness_score: number;
  readiness_level: "high" | "moderate" | "low";
}

export interface WorkloadMetrics {
  acute_load: number;
  chronic_load: number;
  acwr: number;
  acwr_zone: "undertraining" | "optimal" | "high_risk" | "danger";
  monotony: number;
  strain: number;
}

// ========================= //
// SESSION TYPES            //
// ========================= //

export interface PlannedSession {
  id: number;
  date: string;
  sport: string;
  session_type: string;
  target_duration_min: number | null;
  target_distance_km: number | null;
  target_hr_zone: string | null;
  target_intensity: "easy" | "moderate" | "hard" | null;
  description: string | null;
  source: string;
  status: "pending" | "completed" | "skipped" | "modified";
}

export interface ActualSession {
  id: number;
  planned_session_id: number | null;
  date: string;
  start_time: string | null;
  sport: string;
  session_type: string | null;
  name: string | null;
  duration_sec: number;
  duration_min: string; // "MM:SS"
  moving_time_sec: number | null;
  distance_m: number | null;
  distance_km: number | null;
  avg_hr: number | null;
  max_hr: number | null;
  avg_pace_sec_km: number | null;
  avg_pace: string | null; // "MM:SS"
  ascent_m: number | null;
  calories: number | null;
  rpe: number | null;
  notes: string | null;
  source: string;
  garmin_activity_id: string | null;
  strava_activity_id: string | null;
  adherence_score: number | null;
}

export interface MatchSummary {
  total_planned: number;
  total_actual: number;
  total_matched: number;
  total_unmatched: number;
  adherence_rate: number; // 0-100, over sessions due in the window
  planned_due: number;
  completed: number;
  skipped: number;
  window_start: string | null;
  window_end: string | null;
}

// ========================= //
// STRENGTH MODULE TYPES    //
// ========================= //

export interface Exercise {
  id: number;
  name: string;
  category: string;
  primary_muscle: string;
  secondary_muscles: string[];
  equipment: string | null;
  is_unilateral: boolean;
  notes: string | null;
}

export interface ExerciseSet {
  id: number;
  set_number: number;
  reps: number | null;
  weight_kg: number | null;
  rpe: number | null;
  rir: number | null;
  rest_sec: number | null;
  tempo: string | null;
  is_warmup: boolean;
  is_failure: boolean;
  volume: number | null;
  estimated_1rm: number | null;
  notes: string | null;
}

export interface SessionExercise {
  id: number;
  order: number;
  exercise: Exercise;
  exercise_id?: number;
  target_sets: number | null;
  target_reps: number | null;
  target_rpe: number | null;
  sets: ExerciseSet[];
  total_volume: number;
  working_sets_count: number;
  avg_rpe: number | null;
  notes: string | null;
}

export interface StrengthSession {
  id: number;
  date: string;
  name: string | null;
  program: string | null;
  duration_min: number | null;
  overall_rpe: number | null;
  fatigue_level: number | null;
  sleep_quality: number | null;
  notes: string | null;
  total_volume: number;
  total_sets: number;
  exercises_count?: number;
  muscles_worked?: string[];
  exercises?: SessionExercise[];
  garmin_activity_id?: number | null;
}

export interface MuscleStat {
  muscle: string;
  /** French label, e.g. "Grands dorsaux". */
  label: string;
  volume: number;
  sets: number;
  /** 0 (untouched) to 4 (busiest region of the window). */
  level: number;
  previous_volume: number | null;
  last_trained: string | null;
}

export interface MuscleStatsResponse {
  days: number;
  start: string;
  end: string;
  muscles: MuscleStat[];
}

// ========================= //
// SYNC & STATUS TYPES      //
// ========================= //

export interface SyncStatus {
  garmin_authenticated: boolean;
  user_email: string | null;
  last_sync: string | null;
  activities_synced: number;
}

export interface SyncResult {
  synced: number;
  skipped: number;
  errors: string[];
  new_activities: ActualSession[];
}

// ========================= //
// WORKOUT PARSER            //
// ========================= //

export interface ParsedSet {
  set_number: number;
  reps: number | null; // null for failure sets
  weight_kg: number | null;
  rpe: number | null;
  is_warmup: boolean;
  is_failure: boolean;
}

export interface ParsedExercise {
  name: string;
  exercise_id: string | null;
  exercise_matched: boolean;
  sets: ParsedSet[];
  notes: string | null;
}

/** What POST /strength/sessions/transcribe answers for a dictated session. */
export interface WorkoutTranscription {
  /** French text, exactly as dictated. */
  transcript: string;
  /** Compact notation rebuilt from what the grammar read. */
  notation: string;
  /** Sentences left verbatim rather than guessed. */
  unparsed: string[];
  exercises: number;
  cost_usd: number | null;
}

export interface ParsedWorkout {
  success: boolean;
  date: string;
  name: string | null;
  exercises: ParsedExercise[];
  duration_min: number | null;
  overall_rpe: number | null;
  notes: string | null;
  session_id: number | null;
  message: string | null;
  /** Lines the grammar could not parse (LLM fallback disabled or failed). */
  unparsed_lines?: string[];
}

// ========================= //
// ANALYTICS                 //
// ========================= //

export type Period = '7d' | '30d' | '90d' | '6m' | '1y' | 'all';
export type Bucket = 'day' | 'week' | 'month';
export type Tone = 'good' | 'neutral' | 'warn' | 'bad';
/** Which direction of change is an improvement for this number. */
export type Better = 'up' | 'down' | 'neutral';

export interface Headline {
  value: number | null;
  unit: string;
  display: string;
  previous: number | null;
  delta: number | null;
  delta_pct: number | null;
  better: Better;
}

export interface Insight {
  text: string;
  tone: Tone;
}

/** A point of a card series: always a bucket, plus that card's own fields. */
export type SeriesPoint = { bucket: string } & Record<string, number | string | null>;

export interface Card {
  headline: Headline;
  secondary: Headline[];
  insight: Insight;
  series: SeriesPoint[];
}

export type CardKey =
  | 'volume'
  | 'pmc'
  | 'zones'
  | 'sports'
  | 'decoupling'
  | 'pace'
  | 'elevation'
  | 'cadence'
  | 'readiness'
  | 'hrv'
  | 'sleep'
  | 'resting_hr';

export interface HrZoneRange {
  zone: string;
  min: number;
  max: number | null;
}

export interface HrZoneModel {
  /** Which reference the zones are built on. */
  basis: 'lthr' | 'max_hr';
  reference: number;
  boundaries: number[];
  ranges: HrZoneRange[];
}

export interface OverviewResponse {
  hr_zone_model: HrZoneModel;
  period: Period;
  bucket: Bucket;
  start: string;
  end: string;
  prev_start: string | null;
  prev_end: string | null;
  cards: Record<CardKey, Card>;
}

/** The sports card series is per sport, not per bucket. */
export interface SportSlice {
  sport: string;
  hours: number;
  count: number;
  pct: number;
}

export interface PersonalRecord {
  name: string;
  time_sec: number;
  time_display: string;
  date: string;
  activity_name: string;
}
export interface RecordsResponse {
  records: PersonalRecord[];
}

export interface CardioSession {
  id: number;
  date: string;
  sport: string;
  name: string | null;
  duration_sec: number | null;
  distance_m: number | null;
  avg_hr: number | null;
  avg_pace_sec_km: number | null;
  pace_display: string | null;
  rpe: number | null;
  notes: string | null;
  source: string;
  calories: number | null;
}
export interface CardioSessionsResponse {
  sessions: CardioSession[];
}
