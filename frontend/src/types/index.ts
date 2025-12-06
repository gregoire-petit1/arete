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

export interface Recommendation {
  priority: number;
  type: string;
  message: string;
  actions?: string[];
}

export interface RecommendationsResponse {
  recommendations: Recommendation[];
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
  garmin_activity_id: string | null;
  date: string;
  sport: string;
  activity_type: string | null;
  duration_seconds: number;
  distance_meters: number | null;
  avg_hr: number | null;
  max_hr: number | null;
  avg_power: number | null;
  normalized_power: number | null;
  tss: number | null;
  rpe: number | null;
  fit_file_path: string | null;
  analysis_json: string | null;
  llm_summary: string | null;
  matched_planned_id: number | null;
  created_at: string;
}

export interface SessionLogRow {
  id: number;
  date: string;
  sport: string;
  /** Duration in seconds (matches ActualSession) */
  duration_seconds: number;
  rpe: number | null;
  tss: number | null;
  notes: string | null;
}

export interface SessionLogResponse {
  rows: SessionLogRow[];
  total: number;
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
// ACTIVITY ANALYSIS        //
// ========================= //

export interface WorkoutInterval {
  start_time: string;
  end_time: string;
  duration_seconds: number;
  distance_meters: number | null;
  avg_hr: number | null;
  max_hr: number | null;
  avg_pace_per_km: string | null;
  avg_cadence: number | null;
  interval_type: "warmup" | "work" | "recovery" | "cooldown";
}

export interface WorkoutStructure {
  warmup_duration: number | null;
  main_intervals: WorkoutInterval[];
  cooldown_duration: number | null;
  total_work_time: number;
  total_rest_time: number;
}

export interface DerivedMetrics {
  hr_drift_percent: number | null;
  pace_cv: number | null;
  cadence_avg: number | null;
  power_normalized: number | null;
  decoupling: number | null;
}

export interface ActivityAnalysis {
  session_id: number;
  workout_structure: WorkoutStructure | null;
  derived_metrics: DerivedMetrics;
  analysis_timestamp: string;
}

// ========================= //
// STRENGTH MODULE TYPES    //
// ========================= //

export interface Exercise {
  id: number;
  name: string;
  category: "compound" | "isolation" | "cardio" | "mobility";
  muscle_primary: string;
  muscle_secondary: string[] | null;
  equipment: string | null;
  is_custom: boolean;
}

export interface ExerciseSet {
  id: number;
  session_id: number;
  exercise_id: number;
  set_number: number;
  reps: number | null;
  weight_kg: number | null;
  rpe: number | null;
  rest_seconds: number | null;
  is_warmup: boolean;
  is_failure: boolean;
  notes: string | null;
  estimated_1rm: number | null;
}

export interface StrengthSession {
  id: number;
  date: string;
  name: string | null;
  program: string | null;
  duration_minutes: number | null;
  overall_rpe: number | null;
  fatigue_level: number | null;
  notes: string | null;
  total_volume: number;
  total_sets: number;
  exercises: ExerciseSet[];
}

export interface PersonalRecord {
  exercise_id: number;
  exercise_name: string;
  weight_kg: number;
  reps: number;
  estimated_1rm: number;
  date: string;
  trend: "up" | "down" | "plateau";
  trend_value: number;
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

// ========================= //
// RAG / CHAT TYPES         //
// ========================= //

export interface RAGQueryRequest {
  query: string;
  acwr?: number;
  acwr_zone?: string;
  tsb?: number;
  form_zone?: string;
  ctl?: number;
  experience?: string;
  primary_sport?: string;
  fatigue?: number;
}

export interface RAGSource {
  id: string;
  collection: string;
  relevance: number;
  content?: string;
}

export interface RAGQueryRequest {
  query: string;
  acwr?: number;
  acwr_zone?: string;
  tsb?: number;
  form_zone?: string;
  ctl?: number;
  monotony?: number;
  strain?: number;
  experience?: "beginner" | "intermediate" | "advanced" | "elite";
  primary_sport?: string;
  fatigue?: number;
}

export interface RAGSource {
  id: string;
  collection: string;
  relevance: number;
}

export interface RAGMetadata {
  sources_retrieved: RAGSource[];
  context_summary?: {
    intent: string;
    risk_level: number;
    metrics: Record<string, number | string | null>;
    profile: {
      experience: string;
      sport: string;
      fatigue: number;
    };
  };
  rag_enabled: boolean;
}

// Session plan response type
export interface RAGSessionPlan {
  type: "session_plan";
  titre: string;
  sections: Array<{
    nom: string;
    contenu: string;
    duree: string;
  }>;
  cibles: {
    fc?: string;
    allure?: string;
    rpe?: string;
  };
  charge_prevue: string;
  justification: string;
  sources_utilisees: string[];
  avertissements: string[];
  _metadata?: RAGMetadata;
}

// Exercise info response type
export interface RAGExerciseInfo {
  type: "exercise_info";
  exercice: string;
  muscles_principaux: string[];
  muscles_secondaires: string[];
  description: string;
  conseils: string[];
  variantes: string[];
  sources_utilisees: string[];
  _metadata?: RAGMetadata;
}

// Analysis response type
export interface RAGAnalysis {
  type: "analysis";
  titre: string;
  resume: string;
  points_cles: Array<{
    label: string;
    valeur: string;
    interpretation: "bon" | "attention" | "alerte";
  }>;
  recommandations: string[];
  sources_utilisees: string[];
  _metadata?: RAGMetadata;
}

// General response type
export interface RAGGeneral {
  type: "general";
  reponse: string;
  points_cles: string[];
  sources_utilisees: string[];
  _metadata?: RAGMetadata;
}

// Union type for all RAG responses
export type RAGResponse =
  | RAGSessionPlan
  | RAGExerciseInfo
  | RAGAnalysis
  | RAGGeneral;

// ========================= //
// USER TYPES               //
// ========================= //

export interface UserProfile {
  id: number;
  name: string;
  email: string;
  experience_level: "beginner" | "intermediate" | "advanced" | "elite";
  primary_sport: string;
  secondary_sports: string[];
  weekly_hours_target: number;
  created_at: string;
}
