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
import { GoogleCalendarConnection } from "./GoogleCalendarConnection";
import { calendarApi } from "@/lib/googleCalendar";
vi.mock("@/lib/googleCalendar", () => ({
  calendarApi: {
    status: vi.fn(),
    calendars: vi.fn(),
    select: vi.fn(),
    authorize: vi.fn(),
    disconnect: vi.fn(),
  },
}));
beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(calendarApi.status).mockResolvedValue({
    configured: true,
    connected: true,
    selection: { readable: [], writable: [] },
  });
  vi.mocked(calendarApi.calendars).mockResolvedValue([
    {
      id: "personal",
      summary: "Personnel",
      timeZone: "Europe/Paris",
      accessRole: "owner",
    },
  ]);
});
afterEach(cleanup);
function mount() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <GoogleCalendarConnection />
    </QueryClientProvider>,
  );
}
it("starts without access and saves explicit read/write selection", async () => {
  vi.mocked(calendarApi.select).mockResolvedValue({
    configured: true,
    connected: true,
    selection: { readable: ["personal"], writable: ["personal"] },
  });
  mount();
  const read = await screen.findByRole("checkbox", { name: "Lecture" });
  expect((read as HTMLInputElement).checked).toBe(false);
  expect(
    (screen.getByRole("checkbox", { name: "Modification" }) as HTMLInputElement)
      .disabled,
  ).toBe(true);
  expect(screen.getByText("coche Lecture d’abord")).toBeTruthy();
  fireEvent.click(read);
  expect(screen.queryByText("coche Lecture d’abord")).toBeNull();
  fireEvent.click(screen.getByRole("checkbox", { name: "Modification" }));
  fireEvent.click(
    screen.getByRole("button", { name: "Enregistrer les calendriers" }),
  );
  await waitFor(() =>
    expect(calendarApi.select).toHaveBeenCalledWith(
      { readable: ["personal"], writable: ["personal"] },
      expect.anything(),
    ),
  );
});
it("shows revocation failure while local access is disabled", async () => {
  vi.mocked(calendarApi.disconnect).mockResolvedValue({
    connected: false,
    revoked: false,
    warning: "Révocation distante échouée.",
  });
  mount();
  fireEvent.click(await screen.findByRole("button", { name: "Déconnecter" }));
  expect(await screen.findByText("Révocation distante échouée.")).toBeTruthy();
  expect(
    screen.getByRole("button", { name: "Réessayer la révocation" }),
  ).toBeTruthy();
});
it("explains why a read-only Google calendar cannot be modified", async () => {
  vi.mocked(calendarApi.calendars).mockResolvedValue([
    {
      id: "weeks",
      summary: "Numéros de semaine",
      timeZone: "Europe/Paris",
      accessRole: "reader",
    },
  ]);
  mount();
  expect(await screen.findByText("lecture seule dans Google")).toBeTruthy();
});
