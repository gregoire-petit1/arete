import { fetchAPI } from "./api";

export interface CalendarSelection {
  readable: string[];
  writable: string[];
}
/** The training plan followed into one writable calendar. */
export interface PlanSyncStatus {
  enabled: boolean;
  calendar_id: string | null;
  /** ISO timestamp of the last run, whatever its outcome. */
  synced_at: string | null;
  /** French message of the last run's failure, null when it succeeded. */
  error: string | null;
  /** Events Arete created and still tracks (kept after turning it off). */
  events: number;
}
export interface CalendarStatus {
  configured: boolean;
  connected: boolean;
  selection: CalendarSelection;
  /** Google scopes to grant before connecting; absent when not configured. */
  scopes?: string[];
  /** Absent when Calendar is not configured on this server. */
  plan?: PlanSyncStatus;
}
export interface GoogleCalendarInfo {
  id: string;
  summary: string;
  timeZone: string;
  accessRole: string;
}
export interface CalendarEventSnapshot {
  summary: string;
  description: string;
  location: string;
  start: { date?: string; dateTime?: string; timeZone?: string };
  end: { date?: string; dateTime?: string; timeZone?: string };
}
export interface CalendarAction {
  id: string;
  thread_id: string;
  operation: "create" | "update" | "delete";
  calendar_id: string;
  calendar_name: string;
  timezone: string;
  before: CalendarEventSnapshot | null;
  after: CalendarEventSnapshot | null;
  status:
    | "pending"
    | "executing"
    | "succeeded"
    | "rejected"
    | "expired"
    | "invalidated"
    | "failed"
    | "uncertain";
  expires_at: string;
  result: { message?: string; html_link?: string };
}
const base = "/google-calendar";
const mutation = (method: string, body?: unknown): RequestInit => ({
  method,
  headers: { "X-Arete-Calendar": "1" },
  ...(body === undefined ? {} : { body: JSON.stringify(body) }),
});
export const calendarApi = {
  status: () => fetchAPI<CalendarStatus>(`${base}/status`),
  connect: () => fetchAPI<CalendarStatus>(`${base}/connect`, mutation("POST")),
  disconnect: () =>
    fetchAPI<{ connected: false; revoked: boolean; warning?: string }>(
      `${base}/disconnect`,
      mutation("POST"),
    ),
  calendars: () => fetchAPI<GoogleCalendarInfo[]>(`${base}/calendars`),
  select: (selection: CalendarSelection) =>
    fetchAPI<CalendarStatus>(`${base}/selection`, mutation("PUT", selection)),
  planSync: (body: { enabled: boolean; calendar_id?: string }) =>
    fetchAPI<CalendarStatus>(`${base}/plan-sync`, mutation("PUT", body)),
  removePlanEvents: () =>
    fetchAPI<CalendarStatus>(`${base}/plan-sync/remove`, mutation("POST")),
  action: (id: string) =>
    fetchAPI<CalendarAction>(`${base}/actions/${encodeURIComponent(id)}`),
  decide: (id: string, decision: "approve" | "reject") =>
    fetchAPI<CalendarAction>(
      `${base}/actions/${encodeURIComponent(id)}/decision`,
      mutation("POST", { decision }),
    ),
  verify: (id: string) =>
    fetchAPI<CalendarAction>(
      `${base}/actions/${encodeURIComponent(id)}/verify`,
      mutation("POST"),
    ),
};
