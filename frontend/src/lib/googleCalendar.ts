import { fetchAPI } from "./api";

export interface CalendarSelection {
  readable: string[];
  writable: string[];
}
export interface CalendarStatus {
  configured: boolean;
  connected: boolean;
  selection: CalendarSelection;
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
  authorize: () =>
    fetchAPI<{ url: string }>(`${base}/authorize`, mutation("POST")),
  disconnect: () =>
    fetchAPI<{ connected: false; revoked: boolean; warning?: string }>(
      `${base}/disconnect`,
      mutation("POST"),
    ),
  calendars: () => fetchAPI<GoogleCalendarInfo[]>(`${base}/calendars`),
  select: (selection: CalendarSelection) =>
    fetchAPI<CalendarStatus>(`${base}/selection`, mutation("PUT", selection)),
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
