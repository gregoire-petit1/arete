// ========================= //
// FITNESS & WORKLOAD TYPES //
// ========================= //

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

export interface VolumeByMuscle {
  [muscle: string]: number;
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

export interface VolumeWeek {
  week: string;
  sports: Record<string, { hours: number; km: number }>;
  total_hours: number;
  total_km: number;
}
export interface VolumeResponse {
  weeks: VolumeWeek[];
}

export interface TrainingLoadPoint {
  date: string;
  ctl: number;
  atl: number;
  tsb: number;
  tss: number;
}
export interface TrainingLoadResponse {
  data: TrainingLoadPoint[];
}

export interface PaceActivity {
  date: string;
  pace_sec_km: number;
  pace_display: string;
  distance_km: number;
  name: string;
}
export interface PaceResponse {
  activities: PaceActivity[];
}

export interface HrZonesWeek {
  week: string;
  zones: Record<string, number>; // seconds per zone
}
export interface HrZonesResponse {
  weeks: HrZonesWeek[];
}

export interface SportShare {
  [key: string]: string | number;
  sport: string;
  hours: number;
  count: number;
  percentage: number;
}
export interface SportDistributionResponse {
  sports: SportShare[];
  total_hours: number;
}

export interface BestEffort {
  name: string;
  best_time_sec: number;
  best_time_display: string;
  date: string;
  activity_name: string;
}
export interface BestEffortsResponse {
  efforts: BestEffort[];
}

export interface CardiacEfficiencyWeek {
  week: string;
  efficiency: number | null;
  avg_hr: number;
  avg_pace: string | null;
  avg_pace_sec_km: number | null;
  n_runs: number;
}
export interface CardiacEfficiencyResponse {
  data: CardiacEfficiencyWeek[];
}

export interface HrPaceSession {
  date: string;
  sport: string;
  name: string | null;
  avg_hr: number;
  max_hr: number | null;
  pace_sec_km: number | null;
  pace_display: string | null;
  elevation_gain: number | null;
  distance_km: number | null;
  duration_sec: number | null;
}
export interface HrPaceScatterResponse {
  sessions: HrPaceSession[];
}

export interface HrDriftRun {
  id: number;
  date: string;
  name: string | null;
  distance_km: number | null;
  elevation_m: number | null;
  duration_min: number | null;
  avg_hr: number | null;
  avg_pace_sec_km: number | null;
  hr_drift_pct: number;
  pace_drift_pct: number;
  decoupling_pct: number;
  splits: unknown;
  run_type: string;
  drift_score: string;
  expected_decoupling_pct: number | null;
  drift_residual_pct: number | null;
  tags: string[];
}
export interface HrDriftBaseline {
  formula: string;
  coefficients: Record<string, number>;
  r_squared: number;
  n_samples: number;
}
export interface EffortBucket {
  n: number;
  avg_decoupling_pct: number | null;
  best_decoupling_pct: number | null;
  worst_decoupling_pct: number | null;
}
export interface HrDriftResponse {
  runs: HrDriftRun[];
  count: number;
  baseline: HrDriftBaseline | null;
  effort_buckets: Record<string, EffortBucket>;
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
