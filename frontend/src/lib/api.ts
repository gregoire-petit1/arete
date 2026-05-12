const API_BASE = "/api";

async function fetchAPI<T>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const response = await fetch(`${API_BASE}${endpoint}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options?.headers,
    },
  });

  if (!response.ok) {
    const error = await response.text();
    throw new Error(`API Error ${response.status}: ${error}`);
  }

  return response.json();
}

// ========================= //
// METRICS API              //
// ========================= //

export const metricsApi = {
  getFitness: () =>
    fetchAPI<import("@/types").FitnessMetrics>("/metrics/fitness"),

  getWorkload: () =>
    fetchAPI<import("@/types").WorkloadMetrics>("/metrics/workload"),

  getRecommendations: () =>
    fetchAPI<import("@/types").RecommendationsResponse>(
      "/metrics/recommendations"
    ),

  getPlayerStats: () =>
    fetchAPI<{
      hp: { current: number; max: number; label: string };
      mp: { current: number; max: number; label: string };
      xp: { current: number; max: number; label: string };
      level: number;
    }>("/metrics/player-stats"),
};

// ========================= //
// LOG API                  //
// ========================= //

export const logApi = {
  getRecent: (n = 10) =>
    fetchAPI<import("@/types").SessionLogResponse>(`/log/recent?n=${n}`),

  getByDateRange: (start: string, end: string) =>
    fetchAPI<import("@/types").SessionLogResponse>(
      `/log?start=${start}&end=${end}`
    ),
};

// ========================= //
// GARMIN API               //
// ========================= //

export interface PlannedSessionCreate {
  date: string;
  sport?: string;
  session_type: string;
  target_duration_min?: number;
  target_distance_km?: number;
  target_hr_zone?: string;
  target_intensity?: string;
  description?: string;
  source?: string;
}

export const garminApi = {
  getPlanned: (startDate?: string, endDate?: string) => {
    const params = new URLSearchParams();
    if (startDate) params.set("start_date", startDate);
    if (endDate) params.set("end_date", endDate);
    return fetchAPI<import("@/types").PlannedSession[]>(
      `/garmin/planned?${params}`
    );
  },

  createPlanned: (session: PlannedSessionCreate) =>
    fetchAPI<import("@/types").PlannedSession>("/garmin/planned", {
      method: "POST",
      body: JSON.stringify(session),
    }),

  deletePlanned: (id: number) =>
    fetchAPI<void>(`/garmin/planned/${id}`, { method: "DELETE" }),

  getActual: (unmatchedOnly = false) => {
    const params = new URLSearchParams();
    if (unmatchedOnly) params.set("unmatched_only", "true");
    return fetchAPI<import("@/types").ActualSession[]>(
      `/garmin/actual?${params}`
    );
  },

  getSummary: () => fetchAPI<import("@/types").MatchSummary>("/garmin/summary"),

  uploadFit: async (file: File, autoMatch = true) => {
    const formData = new FormData();
    formData.append("file", file);
    const response = await fetch(
      `${API_BASE}/garmin/upload-fit?auto_match=${autoMatch}`,
      {
        method: "POST",
        body: formData,
      }
    );
    if (!response.ok) {
      const error = await response.text();
      throw new Error(`Upload Error: ${error}`);
    }
    return response.json();
  },

  analyzeSession: (sessionId: number, detailed = false, force = false) =>
    fetchAPI<import("@/types").ActivityAnalysis>(
      `/garmin/actual/${sessionId}/analyze?detailed=${detailed}&force=${force}`,
      { method: "POST" }
    ),

  // Sync endpoints
  getSyncStatus: () =>
    fetchAPI<import("@/types").SyncStatus>("/garmin/sync/status"),

  login: (credentials?: { email: string; password: string }) =>
    fetchAPI<{ status: string; user_email: string }>("/garmin/sync/login", {
      method: "POST",
      body: credentials ? JSON.stringify(credentials) : undefined,
    }),

  logout: () =>
    fetchAPI<{ status: string }>("/garmin/sync/logout", { method: "POST" }),

  syncActivities: (options: {
    start_date?: string;
    end_date?: string;
    download_fit?: boolean;
    max_activities?: number;
  }) =>
    fetchAPI<import("@/types").SyncResult>("/garmin/sync/activities", {
      method: "POST",
      body: JSON.stringify(options),
    }),
};

// ========================= //
// STRENGTH API             //
// ========================= //

export const strengthApi = {
  getExercises: (filters?: {
    category?: string;
    muscle?: string;
    search?: string;
  }) => {
    const params = new URLSearchParams();
    if (filters?.category) params.set("category", filters.category);
    if (filters?.muscle) params.set("muscle", filters.muscle);
    if (filters?.search) params.set("search", filters.search);
    return fetchAPI<import("@/types").Exercise[]>(
      `/strength/exercises?${params}`
    );
  },

  getSessions: (limit = 50) =>
    fetchAPI<import("@/types").StrengthSession[]>(
      `/strength/sessions?limit=${limit}`
    ),

  getSession: (id: number) =>
    fetchAPI<import("@/types").StrengthSession>(`/strength/sessions/${id}`),

  deleteSession: (id: number) =>
    fetchAPI<{ message: string }>(`/strength/sessions/${id}`, {
      method: "DELETE",
    }),

  createSession: (session: {
    date: string;
    name?: string | null;
    program?: string | null;
    duration_min?: number | null;
    overall_rpe?: number | null;
    fatigue_level?: number | null;
    notes?: string | null;
    exercises?: Array<{
      exercise_id: number;
      order: number;
      sets?: Array<{
        set_number: number;
        reps: number;
        weight_kg?: number;
        rpe?: number;
      }>;
    }>;
  }) =>
    fetchAPI<import("@/types").StrengthSession>("/strength/sessions", {
      method: "POST",
      body: JSON.stringify(session),
    }),

  parseWorkout: (text: string, date?: string, save = false) =>
    fetchAPI<{
      success: boolean;
      date: string;
      name: string | null;
      exercises: Array<{
        name: string;
        exercise_id: string | null;
        exercise_matched: boolean;
        sets: Array<{
          set_number: number;
          reps: number | null; // null for failure sets
          weight_kg: number | null;
          rpe: number | null;
          is_warmup: boolean;
          is_failure: boolean;
        }>;
        notes: string | null;
      }>;
      duration_min: number | null;
      overall_rpe: number | null;
      notes: string | null;
      session_id: number | null;
      message: string | null;
    }>("/strength/sessions/parse", {
      method: "POST",
      body: JSON.stringify({ text, date, save }),
    }),

  getVolumeByMuscle: (startDate?: string, endDate?: string) => {
    const params = new URLSearchParams();
    if (startDate) params.set("start_date", startDate);
    if (endDate) params.set("end_date", endDate);
    return fetchAPI<import("@/types").VolumeByMuscle>(
      `/strength/stats/volume-by-muscle?${params}`
    );
  },

  getExercisePRs: (exerciseId: number) =>
    fetchAPI<import("@/types").PersonalRecord[]>(
      `/strength/exercises/${exerciseId}/prs`
    ),

  // Garmin linking
  getGarminCandidates: (sessionId: number) =>
    fetchAPI<{
      candidates: Array<{
        id: number;
        date: string;
        sport: string;
        activity_type: string;
        duration_seconds: number;
        source: string;
      }>;
      session_date: string;
    }>(`/strength/sessions/${sessionId}/garmin-candidates`),

  linkToGarmin: (sessionId: number, garminActivityId: number | null) =>
    fetchAPI<{ message: string }>(
      `/strength/sessions/${sessionId}/link-garmin`,
      {
        method: "POST",
        body: JSON.stringify({ garmin_activity_id: garminActivityId }),
      }
    ),
};

// ========================= //
// RAG API                  //
// ========================= //

export const ragApi = {
  query: (request: import("@/types").RAGQueryRequest) =>
    fetchAPI<import("@/types").RAGResponse>("/rag/query", {
      method: "POST",
      body: JSON.stringify(request),
    }),

  getCollections: () =>
    fetchAPI<{
      collections: string[];
      document_counts: Record<string, number>;
    }>("/rag/collections"),

  seedKnowledgeBase: () =>
    fetchAPI<{ status: string }>("/rag/seed", { method: "POST" }),
};

// ========================= //
// HEALTH API               //
// ========================= //

export const healthApi = {
  check: () =>
    fetchAPI<{ status: string; database: string; rag: string }>("/health"),
};

// ========================= //
// SETTINGS API             //
// ========================= //

export interface UserSettings {
  user_id: number;
  display_name: string;
  email: string | null;
  timezone: string;
  weekly_training_goal: number;
  rest_day_preference: string[];
  fatigue_threshold: number;
  fitness_goal: "maintenance" | "build" | "peak" | "recovery";
  notifications_enabled: boolean;
  theme: "dark" | "darker" | "abyss";
  exercise_abbreviations: Record<string, string>;
}

export const tipsApi = {
  getDaily: () =>
    fetchAPI<{
      tip: string;
      priority: "info" | "warning" | "alert";
      generated_at: string;
    }>("/tips/daily"),

  getPostSession: (
    sessionType: "strength" | "cardio",
    sessionId: number
  ) =>
    fetchAPI<{ feedback: string; highlights: string[] }>("/tips/post-session", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_type: sessionType,
        session_id: sessionId,
      }),
    }),
};

// ========================= //
// STRAVA API              //
// ========================= //

export const stravaApi = {
  getStatus: () =>
    fetchAPI<{
      connected: boolean;
      athlete_name: string | null;
      athlete_id: number | null;
    }>("/strava/status"),

  getAuthorizeUrl: () =>
    fetchAPI<{ url: string }>("/strava/authorize"),

  sync: (days = 30) =>
    fetchAPI<{
      success: boolean;
      imported: number;
      skipped: number;
      errors: string[];
    }>("/strava/sync", {
      method: "POST",
      body: JSON.stringify({ days }),
    }),

  disconnect: () =>
    fetchAPI<{ success: boolean }>("/strava/disconnect", { method: "DELETE" }),
};

// ========================= //
// ANALYTICS API             //
// ========================= //

export const analyticsApi = {
  getVolume: (period = '30d', sport = 'all') =>
    fetchAPI<any>(`/analytics/volume?period=${period}&sport=${sport}`),
  getTrainingLoad: (period = '90d') =>
    fetchAPI<any>(`/analytics/training-load?period=${period}`),
  getPace: (period = '90d', sport = 'running') =>
    fetchAPI<any>(`/analytics/pace?period=${period}&sport=${sport}`),
  getHrZones: (period = '30d') =>
    fetchAPI<any>(`/analytics/hr-zones?period=${period}`),
  getSportDistribution: (period = '90d') =>
    fetchAPI<any>(`/analytics/sport-distribution?period=${period}`),
  getBestEfforts: (sport = 'running') =>
    fetchAPI<any>(`/analytics/best-efforts?sport=${sport}`),
  getSessions: (limit = 20, offset = 0) =>
    fetchAPI<any>(`/analytics/sessions?limit=${limit}&offset=${offset}`),
  updateSession: (id: number, data: { rpe?: number; notes?: string }) =>
    fetchAPI<any>(`/analytics/sessions/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),
};

export const settingsApi = {
  get: () => fetchAPI<UserSettings>("/settings"),

  update: (settings: Omit<UserSettings, "user_id">) =>
    fetchAPI<UserSettings>("/settings", {
      method: "PUT",
      body: JSON.stringify(settings),
    }),
};
