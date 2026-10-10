// @vitest-environment jsdom
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import { PlanCalendarSync } from "./PlanCalendarSync";
import {
  calendarApi,
  type CalendarStatus,
  type PlanSyncStatus,
} from "@/lib/googleCalendar";
vi.mock("@/lib/googleCalendar", () => ({
  calendarApi: { planSync: vi.fn(), removePlanEvents: vi.fn() },
}));
beforeEach(() => vi.clearAllMocks());
afterEach(cleanup);
const calendars = [
  { id: "personal", summary: "Personnel", timeZone: "Europe/Paris", accessRole: "owner" },
  { id: "arete", summary: "Arete", timeZone: "Europe/Paris", accessRole: "owner" },
  { id: "shared", summary: "Famille", timeZone: "Europe/Paris", accessRole: "owner" },
];
const off: PlanSyncStatus = {
  enabled: false,
  calendar_id: null,
  synced_at: null,
  error: null,
  events: 0,
};
function status(plan: Partial<PlanSyncStatus>): CalendarStatus {
  return {
    configured: true,
    connected: true,
    // "Famille" is readable only: never offered as the plan's calendar.
    selection: { readable: ["personal", "arete", "shared"], writable: ["personal", "arete"] },
    plan: { ...off, ...plan },
  };
}
function mount(current: CalendarStatus) {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <PlanCalendarSync status={current} calendars={calendars} />
    </QueryClientProvider>,
  );
}
it("turns the sync on for a writable calendar the athlete picked", async () => {
  vi.mocked(calendarApi.planSync).mockResolvedValue(status({ enabled: true }));
  mount(status({}));
  const select = screen.getByRole("combobox") as HTMLSelectElement;
  expect([...select.options].map((o) => o.textContent)).toEqual([
    "Personnel",
    "Arete",
  ]);
  expect(screen.getByText(/crée d’abord un calendrier « Arete »/)).toBeTruthy();
  fireEvent.change(select, { target: { value: "arete" } });
  expect(calendarApi.planSync).not.toHaveBeenCalled(); // off: nothing yet
  fireEvent.click(
    screen.getByRole("checkbox", { name: "Synchroniser le plan d’entraînement" }),
  );
  await waitFor(() =>
    expect(calendarApi.planSync).toHaveBeenCalledWith(
      { enabled: true, calendar_id: "arete" },
      expect.anything(),
    ),
  );
});
it("shows the last run, its count and its error", () => {
  mount(
    status({
      enabled: true,
      calendar_id: "arete",
      synced_at: "2026-10-10T06:00:00+00:00",
      events: 12,
      error: "Permission Google insuffisante.",
    }),
  );
  expect(screen.getByText(/12 événements dans Google Calendar/)).toBeTruthy();
  expect(screen.getByText(/dernière synchronisation le/)).toBeTruthy();
  expect(screen.getByRole("alert").textContent).toBe(
    "Permission Google insuffisante.",
  );
});
it("turning it off offers to remove the events it created", async () => {
  vi.mocked(calendarApi.planSync).mockResolvedValue(status({ events: 3 }));
  vi.mocked(calendarApi.removePlanEvents).mockResolvedValue(status({}));
  mount(status({ enabled: true, calendar_id: "arete", events: 3 }));
  expect(screen.queryByRole("button", { name: /Retirer/ })).toBeNull();
  fireEvent.click(
    screen.getByRole("checkbox", { name: "Synchroniser le plan d’entraînement" }),
  );
  await waitFor(() =>
    expect(calendarApi.planSync).toHaveBeenCalledWith(
      { enabled: false },
      expect.anything(),
    ),
  );
});
it("removes the events only on an explicit click", async () => {
  vi.mocked(calendarApi.removePlanEvents).mockResolvedValue(status({}));
  mount(status({ calendar_id: "arete", events: 3 }));
  expect(screen.getByText(/restent dans Google/)).toBeTruthy();
  expect(calendarApi.removePlanEvents).not.toHaveBeenCalled();
  fireEvent.click(
    screen.getByRole("button", { name: "Retirer les événements du plan" }),
  );
  await waitFor(() => expect(calendarApi.removePlanEvents).toHaveBeenCalled());
});
