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
import { ApiError } from "@/lib/api";
import { calendarApi } from "@/lib/googleCalendar";
import { AUTH_DISABLED, AuthStateContext } from "@/components/auth/authState";
vi.mock("@/lib/googleCalendar", () => ({
  calendarApi: {
    status: vi.fn(),
    calendars: vi.fn(),
    select: vi.fn(),
    connect: vi.fn(),
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
const SCOPES = ["https://www.googleapis.com/auth/calendar.events"];
const grantGoogleScopes = vi.fn(async () => true);
function mount() {
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <AuthStateContext.Provider
        value={{ ...AUTH_DISABLED, enabled: true, grantGoogleScopes }}
      >
        <GoogleCalendarConnection />
      </AuthStateContext.Provider>
    </QueryClientProvider>,
  );
}
const disconnected = {
  configured: true,
  connected: false,
  selection: { readable: [], writable: [] },
  scopes: SCOPES,
};
const refused = new ApiError(409, '{"detail":"Autorise l’accès"}');
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
it("asks Google for the calendar scopes only when the server refuses", async () => {
  vi.mocked(calendarApi.status).mockResolvedValue(disconnected);
  vi.mocked(calendarApi.connect).mockRejectedValue(refused);
  mount();
  fireEvent.click(
    await screen.findByRole("button", { name: "Connecter Google Calendar" }),
  );
  await waitFor(() => expect(grantGoogleScopes).toHaveBeenCalledTimes(1));
  const [scopes, returnTo] = grantGoogleScopes.mock.calls[0] as unknown as [
    string[],
    string,
  ];
  expect(scopes).toEqual(SCOPES);
  expect(new URL(returnTo).searchParams.get("google_calendar")).toBe("granted");
  // The page is leaving for Google: no second attempt before it comes back.
  expect(calendarApi.connect).toHaveBeenCalledTimes(1);
});
it("connects directly when the scopes were already granted", async () => {
  vi.mocked(calendarApi.status).mockResolvedValue(disconnected);
  vi.mocked(calendarApi.connect).mockResolvedValue({
    ...disconnected,
    connected: true,
  });
  mount();
  fireEvent.click(
    await screen.findByRole("button", { name: "Connecter Google Calendar" }),
  );
  expect(await screen.findByText(/Google Calendar connecté/)).toBeTruthy();
  expect(grantGoogleScopes).not.toHaveBeenCalled();
});
it("back from a refused consent, says so without asking again", async () => {
  window.history.replaceState({}, "", "/settings?tab=connections&google_calendar=granted");
  vi.mocked(calendarApi.status).mockResolvedValue(disconnected);
  vi.mocked(calendarApi.connect).mockRejectedValue(refused);
  mount();
  expect(await screen.findByText(/non accordé/)).toBeTruthy();
  expect(calendarApi.connect).toHaveBeenCalledTimes(1);
  expect(grantGoogleScopes).not.toHaveBeenCalled();
  expect(window.location.search).toBe("?tab=connections");
});
