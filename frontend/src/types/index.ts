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
  duration_minutes: number | null;
  description: string | null;
  target_tss: number | null;
  source: string;
  status: "pending" | "completed" | "skipped";
  matched_actual_id: number | null;
  adherence_score: number | null;
  created_at: string;
}

export interface ActualSession {
  id: number;
  planned_session_id: number | null;
  garmin_activity_id?: string | null;
  date: string;
  sport: string;
  activity_type?: string | null;
  session_type?: string | null;
  duration_seconds?: number;
  duration_min?: string | null;
  distance_meters?: number | null;
  distance_km?: number | null;
  avg_hr: number | null;
  max_hr: number | null;
  avg_pace?: string | null;
  avg_power?: number | null;
  normalized_power?: number | null;
  ascent_m?: number | null;
  calories?: number | null;
  tss?: number | null;
  rpe?: number | null;
  source?: string | null;
  fit_file_path?: string | null;
  analysis_json?: string | null;
  llm_summary?: string | null;
  matched_planned_id?: number | null;
  adherence_score?: number | null;
  created_at?: string;
}

export interface MatchSummary {
  total_planned: number;
  total_actual: number;
  matched: number;
  unmatched_planned: number;
  unmatched_actual: number;
  completion_rate: number;
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
  runalyze_configured: boolean;
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
