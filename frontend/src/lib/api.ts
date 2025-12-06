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

export const garminApi = {
  getPlanned: (startDate?: string, endDate?: string) => {
    const params = new URLSearchParams();
    if (startDate) params.set("start_date", startDate);
    if (endDate) params.set("end_date", endDate);
    return fetchAPI<import("@/types").PlannedSession[]>(
      `/garmin/planned?${params}`
    );
  },

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

  createSession: (session: Partial<import("@/types").StrengthSession>) =>
    fetchAPI<import("@/types").StrengthSession>("/strength/sessions", {
      method: "POST",
      body: JSON.stringify(session),
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
