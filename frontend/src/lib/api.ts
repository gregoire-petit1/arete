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

  getPlayerStats: () =>
    fetchAPI<{
      hp: { current: number; max: number; label: string };
      mp: { current: number; max: number; label: string };
      xp: { current: number; max: number; label: string };
      level: number;
    }>("/metrics/player-stats"),
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

  // Sync endpoints
  getSyncStatus: () =>
    fetchAPI<import("@/types").SyncStatus>("/garmin/sync/status"),

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

  parseWorkout: (text: string, date?: string, save = false) =>
    fetchAPI<import("@/types").ParsedWorkout>("/strength/sessions/parse", {
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
// HEALTH API               //
// ========================= //

export const healthApi = {
  check: () =>
    fetchAPI<{ status: string; database: string }>("/health"),
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
  getVolume: (period = "30d", sport = "all") =>
    fetchAPI<import("@/types").VolumeResponse>(
      `/analytics/volume?period=${period}&sport=${sport}`
    ),
  getTrainingLoad: (period = "90d") =>
    fetchAPI<import("@/types").TrainingLoadResponse>(
      `/analytics/training-load?period=${period}`
    ),
  getPace: (period = "90d", sport = "running") =>
    fetchAPI<import("@/types").PaceResponse>(
      `/analytics/pace?period=${period}&sport=${sport}`
    ),
  getHrZones: (period = "30d") =>
    fetchAPI<import("@/types").HrZonesResponse>(
      `/analytics/hr-zones?period=${period}`
    ),
  getSportDistribution: (period = "90d") =>
    fetchAPI<import("@/types").SportDistributionResponse>(
      `/analytics/sport-distribution?period=${period}`
    ),
  getBestEfforts: (sport = "running") =>
    fetchAPI<import("@/types").BestEffortsResponse>(
      `/analytics/best-efforts?sport=${sport}`
    ),
  getCardiacEfficiency: (period = "90d") =>
    fetchAPI<import("@/types").CardiacEfficiencyResponse>(
      `/analytics/cardiac-efficiency?period=${period}`
    ),
  getHrPaceScatter: (period = "90d") =>
    fetchAPI<import("@/types").HrPaceScatterResponse>(
      `/analytics/hr-pace-scatter?period=${period}`
    ),
  getHrDrift: (period = "1y", minDurationMin = 40) =>
    fetchAPI<import("@/types").HrDriftResponse>(
      `/analytics/hr-drift?period=${period}&min_duration_min=${minDurationMin}`
    ),
  getSessions: (limit = 20, offset = 0) =>
    fetchAPI<import("@/types").CardioSessionsResponse>(
      `/analytics/sessions?limit=${limit}&offset=${offset}`
    ),
  updateSession: (id: number, data: { rpe?: number; notes?: string }) =>
    fetchAPI<{ success: boolean }>(`/analytics/sessions/${id}`, {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
};

// ========================= //
// GARMIN HEALTH API         //
// ========================= //

export const garminHealthApi = {
  getStatus: () =>
    fetchAPI<{
      tokens_present: boolean;
      days_stored: number;
      first_date: string | null;
      last_date: string | null;
      last_sync: string | null;
    }>("/garmin/health/status"),

  sync: (start: string, end: string) =>
    fetchAPI<{ start: string; end: string; days_synced: number; days_failed: number; errors: string[] }>(
      `/garmin/health/sync?start=${start}&end=${end}`,
      { method: "POST" }
    ),

  getDaily: (date: string) =>
    fetchAPI<{
      date: string;
      hrv_weekly_avg: number | null;
      hrv_last_night: number | null;
      hrv_status: string | null;
      sleep_duration_sec: number | null;
      sleep_score: number | null;
      body_battery_high: number | null;
      stress_avg: number | null;
      stress_max: number | null;
      steps: number | null;
      readiness_score: number | null;
    }>(`/garmin/health/daily?date=${date}`),

  getRange: (start: string, end: string) =>
    fetchAPI<{
      start: string;
      end: string;
      days: Array<{
        date: string;
        hrv_last_night: number | null;
        hrv_weekly_avg: number | null;
        sleep_score: number | null;
        sleep_duration_sec: number | null;
        body_battery_high: number | null;
        body_battery_low: number | null;
        stress_avg: number | null;
        resting_hr: number | null;
        readiness_score: number | null;
        steps: number | null;
      }>;
    }>(`/garmin/health/range?start=${start}&end=${end}`),
};

export const settingsApi = {
  get: () => fetchAPI<UserSettings>("/settings"),

  update: (settings: Omit<UserSettings, "user_id">) =>
    fetchAPI<UserSettings>("/settings", {
      method: "PUT",
      body: JSON.stringify(settings),
    }),
};
