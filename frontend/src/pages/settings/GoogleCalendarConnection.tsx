import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { calendarApi, type CalendarSelection } from "@/lib/googleCalendar";
import { Button } from "@/components/ui";

export function GoogleCalendarConnection() {
  const cache = useQueryClient();
  const status = useQuery({
    queryKey: ["calendarStatus"],
    queryFn: calendarApi.status,
    retry: false,
  });
  const calendars = useQuery({
    queryKey: ["googleCalendars"],
    queryFn: calendarApi.calendars,
    enabled: status.data?.connected === true,
    retry: false,
  });
  const [draft, setDraft] = useState<CalendarSelection | null>(null);
  const [notice, setNotice] = useState(() => {
    const result = new URLSearchParams(window.location.search).get(
      "google_calendar",
    );
    return result === "connected"
      ? "Google Calendar connecté. Choisis les calendriers accessibles."
      : result === "error"
        ? "Connexion refusée, expirée ou indisponible. Tu peux réessayer."
        : "";
  });
  useEffect(() => {
    const url = new URL(window.location.href);
    const result = url.searchParams.get("google_calendar");
    if (!result) return;
    // The callback returns fixed status codes; no credentials enter browser storage.
    url.searchParams.delete("google_calendar");
    window.history.replaceState({}, "", url.pathname + url.search);
    void cache.invalidateQueries({ queryKey: ["calendarStatus"] });
  }, [cache]);
  const connect = useMutation({
    mutationFn: calendarApi.authorize,
    onSuccess: ({ url }) => {
      window.location.href = url;
    },
  });
  const disconnect = useMutation({
    mutationFn: calendarApi.disconnect,
    onSuccess: (result) => {
      setDraft(null);
      setNotice(result.warning || "Google Calendar déconnecté.");
      void cache.invalidateQueries({ queryKey: ["calendarStatus"] });
      void cache.invalidateQueries({ queryKey: ["calendarAction"] });
      cache.removeQueries({ queryKey: ["googleCalendars"] });
    },
  });
  const save = useMutation({
    mutationFn: calendarApi.select,
    onSuccess: (result) => {
      cache.setQueryData(["calendarStatus"], result);
      setDraft(null);
      setNotice("Calendriers enregistrés.");
      void cache.invalidateQueries({ queryKey: ["calendarAction"] });
    },
  });
  const selected = draft ??
    status.data?.selection ?? { readable: [], writable: [] };
  const error =
    status.error ||
    calendars.error ||
    connect.error ||
    disconnect.error ||
    save.error;
  const busy = connect.isPending || disconnect.isPending || save.isPending;
  return (
    <section
      aria-label="Connexion Google Calendar"
      className="space-y-3 rounded border border-text-muted/20 bg-abyss/50 p-4"
    >
      <div className="font-mono text-sm text-text-primary">Google Calendar</div>
      {error && (
        <p role="alert" className="break-words text-xs text-danger-red">
          {error.message}
        </p>
      )}
      {notice && (
        <p role="status" className="text-xs text-text-secondary">
          {notice}
        </p>
      )}
      {status.isPending ? (
        <p className="text-xs">Chargement…</p>
      ) : !status.data?.configured ? (
        <p className="text-xs text-text-muted">
          Connexion indisponible sur ce serveur.
        </p>
      ) : (
        <>
          <p className="text-xs text-text-muted">
            {status.data.connected
              ? "Connecté. Chaque modification proposée par le coach demande ta validation."
              : "Connecte ton compte puis choisis les calendriers accessibles au coach."}
          </p>
          <div className="flex gap-2">
            <Button size="sm" disabled={busy} onClick={() => connect.mutate()}>
              {status.data.connected
                ? "Reconnecter"
                : "Connecter Google Calendar"}
            </Button>
            {status.data.connected && (
              <Button
                size="sm"
                variant="danger"
                disabled={busy}
                onClick={() => disconnect.mutate()}
              >
                Déconnecter
              </Button>
            )}
            {disconnect.data?.revoked === false && (
              <Button
                size="sm"
                disabled={busy}
                onClick={() => disconnect.mutate()}
              >
                Réessayer la révocation
              </Button>
            )}
          </div>
          {status.data.connected && (
            <>
              <p className="text-xs text-text-muted">
                10 calendriers maximum. Aucun accès tant que la sélection n’est
                pas enregistrée.
              </p>
              {calendars.data?.map((calendar) => (
                <div
                  key={calendar.id}
                  className="flex flex-wrap items-center gap-3 border-t border-text-muted/10 py-2 text-xs"
                >
                  <span className="min-w-32 flex-1">{calendar.summary}</span>
                  <label>
                    <input
                      type="checkbox"
                      checked={selected.readable.includes(calendar.id)}
                      disabled={
                        busy || calendar.accessRole === "freeBusyReader"
                      }
                      onChange={(e) =>
                        setDraft({
                          readable: e.target.checked
                            ? [...selected.readable, calendar.id]
                            : selected.readable.filter(
                                (id) => id !== calendar.id,
                              ),
                          writable: selected.writable.filter(
                            (id) => id !== calendar.id,
                          ),
                        })
                      }
                    />{" "}
                    Lecture
                  </label>
                  <label>
                    <input
                      type="checkbox"
                      checked={selected.writable.includes(calendar.id)}
                      disabled={
                        busy ||
                        !selected.readable.includes(calendar.id) ||
                        !["owner", "writer"].includes(calendar.accessRole)
                      }
                      onChange={(e) =>
                        setDraft({
                          ...selected,
                          writable: e.target.checked
                            ? [...selected.writable, calendar.id]
                            : selected.writable.filter(
                                (id) => id !== calendar.id,
                              ),
                        })
                      }
                    />{" "}
                    Modification
                  </label>
                </div>
              ))}
              {calendars.isError && (
                <Button size="sm" onClick={() => void calendars.refetch()}>
                  Actualiser les calendriers
                </Button>
              )}
              <Button
                size="sm"
                disabled={busy || !draft || selected.readable.length > 10}
                onClick={() => save.mutate(selected)}
              >
                Enregistrer les calendriers
              </Button>
              {selected.readable.length > 10 && (
                <p role="alert" className="text-xs text-danger-red">
                  Sélectionne au maximum 10 calendriers.
                </p>
              )}
            </>
          )}
        </>
      )}
    </section>
  );
}
