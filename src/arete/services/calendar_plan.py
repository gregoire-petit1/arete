"""The training plan, followed into the one Google calendar the athlete chose.

A standing, revocable authorization given in Settings replaces the per-card
approval of coach proposals, which stays unchanged. Arete writes only from the
plan, only into the chosen calendar of the account's writable selection, and
only events it created: each carries ``extendedProperties.private`` markers
and a client-chosen id derived from the session, so a retry after a lost
response finds its event instead of adding a second one. No model request.

Each run is bounded (deadline, writes) and reconciles from Google's current
state rather than replaying a write: it lists the calendar's Arete events,
updates with the listed ETag, and leaves the rest to the next trigger.
"""

import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from time import monotonic
from zoneinfo import ZoneInfo

from arete.services.calendar import CalendarService
from arete.services.calendar_models import MAX_PAGES, CalendarError
from arete.services.calendar_provider import GoogleCalendar

logger = logging.getLogger(__name__)

#: Sessions shown: today and the next 28 days, pending or modified.
WINDOW_DAYS = 28
#: Passes per run: another request may ask for one while a run holds the lease.
MAX_PASSES = 3
#: The lease outlives the run's deadline, so a crashed run frees it anyway.
LEASE_MARGIN_SECONDS = 30
#: No write starts closer than this to the deadline.
MIN_WRITE_SECONDS = 3
ACTIVE = ("pending", "modified")
PARTIAL = "Synchronisation partielle (limite atteinte) : la suite au prochain passage."
INTERNAL = "Échec interne de la synchronisation ; elle reprendra au prochain passage."
FOOTER = "Séance du plan Arete. Modifie-la dans Arete : la synchronisation remplace les changements faits ici."

SESSION_LABELS = {
    "recovery": "Récupération",
    "endurance": "Endurance",
    "tempo": "Seuil",
    "intervals": "Fractionné",
    "long_run": "Sortie longue",
    "strength": "Musculation",
    "hypertrophy": "Musculation",
    "power": "Musculation",
    "deload": "Décharge",
    "cross_training": "Cross-training",
    "race": "Course",
}
SPORT_LABELS = {
    "running": "Course",
    "cycling": "Vélo",
    "swimming": "Natation",
    "walking": "Marche",
    "hiking": "Randonnée",
}


@dataclass(frozen=True)
class Budget:
    seconds: float
    writes: int


#: After the response of a request that changed the plan.
AFTER_PLAN_WRITE = Budget(seconds=20, writes=25)
#: Turning the sync on, or removing its events, from Settings.
SETTINGS = Budget(seconds=20, writes=25)
#: The daily sync (Vercel cron or the in-process scheduler).
DAILY = Budget(seconds=40, writes=60)


@dataclass(frozen=True)
class PlanRow:
    id: int
    date: date
    sport: str
    session_type: str
    duration_min: int | None
    distance_km: float | None
    intensity: str | None
    description: str | None
    status: str
    event_id: str | None
    calendar_id: str | None
    etag: str | None
    digest: str | None


def event_body(row: PlanRow, zone: str, prefix: str, at: time | None = None) -> dict:
    """The Google event of a session: all-day without a time of day.

    Planned sessions carry no time of day yet, so the sync always passes
    ``at=None``; a timed event lasts the target duration (60 min by default).
    """
    label = SESSION_LABELS.get(row.session_type, "Séance")
    sport = SPORT_LABELS.get(row.sport)
    parts = [sport] if sport and sport != label else []
    parts.append(label)
    if row.duration_min:
        parts.append(f"{row.duration_min} min")
    elif row.distance_km:
        parts.append(f"{row.distance_km:g} km")
    if at is None:
        start: dict = {"date": row.date.isoformat()}
        end: dict = {"date": (row.date + timedelta(days=1)).isoformat()}
    else:
        begin = datetime.combine(row.date, at, ZoneInfo(zone))
        finish = begin + timedelta(minutes=row.duration_min or 60)
        start = {"dateTime": begin.isoformat(), "timeZone": zone}
        end = {"dateTime": finish.isoformat(), "timeZone": zone}
    description = (row.description or "").strip()
    return {
        "summary": " · ".join(parts),
        "description": f"{description}\n\n{FOOTER}" if description else FOOTER,
        "start": start,
        "end": end,
        # An all-day reminder must not make the whole day busy.
        "transparency": "transparent" if at is None else "opaque",
        "extendedProperties": {
            "private": {"arete_tag": prefix, "arete_session_id": str(row.id)}
        },
    }


def digest(body: dict, calendar_id: str) -> str:
    return hashlib.sha256(
        json.dumps([calendar_id, body], sort_keys=True).encode()
    ).hexdigest()[:32]


def owner(event: dict, prefix: str) -> int | None:
    """The session an event belongs to, or None when Arete did not create it."""
    private = (event.get("extendedProperties") or {}).get("private") or {}
    session_id = str(private.get("arete_session_id", ""))
    if (
        private.get("arete_tag") != prefix
        or not session_id.isdigit()
        or event.get("id") != prefix + session_id
    ):
        return None
    return int(session_id)


class _Spend:
    """A run's write allowance, checked before each write."""

    def __init__(self, budget: Budget):
        self.deadline = monotonic() + budget.seconds
        self.writes = budget.writes

    def __call__(self) -> bool:
        if self.writes <= 0 or self.deadline - monotonic() < MIN_WRITE_SECONDS:
            return False
        self.writes -= 1
        return True


@dataclass(frozen=True)
class _Run:
    """What one pass writes with: Google, its allowance, its ids and calendars."""

    google: GoogleCalendar
    spend: _Spend
    prefix: str
    writable: list[str]


class PlanSync:
    def __init__(self, calendar: CalendarService, today: date | None = None):
        self.calendar, self.repo = calendar, calendar.repo
        self.today = today  # tests pin the day; otherwise the athlete's today

    def configure(self, enabled: bool, calendar_id: str | None) -> dict:
        """The standing authorization: on with a writable target, or off."""
        if not enabled:
            self.repo.configure_plan(enabled=False)
            return self.calendar.status()
        if not calendar_id:
            raise CalendarError("Choisis le calendrier du plan.", 400)
        with self.calendar.operation() as google:
            self.calendar._calendar(google, calendar_id, write=True)
        self.repo.configure_plan(
            enabled=True,
            calendar_id=calendar_id,
            clerk_user_id=self.calendar.provider.clerk_user_id,
        )
        self.run(SETTINGS)
        return self.calendar.status()

    def run(self, budget: Budget) -> str:
        """One bounded run; records its outcome on the connection, never raises
        a Google error (they are the status Settings shows)."""
        if not self.repo.claim_plan_sync(budget.seconds + LEASE_MARGIN_SECONDS):
            return "busy"  # the holder runs one more pass for this change
        spend = _Spend(budget)
        error: str | None = INTERNAL
        outcome = "failed"
        try:
            for _ in range(MAX_PASSES):
                self.repo.begin_plan_pass()
                if not self._pass(spend):
                    error, outcome = PARTIAL, "partial"
                    break
                if self.repo.release_plan_sync(error=None, force=False):
                    return "synced"
            else:
                error, outcome = None, "synced"
        except CalendarError as exc:
            error = str(exc)
        except Exception:
            logger.exception("Training plan calendar sync failed")
        self.repo.release_plan_sync(error=error, force=True)
        return outcome

    def remove(self) -> dict:
        """Delete the events Arete synced; bounded, so it may need a retry."""
        if self.repo.plan_state()["enabled"]:
            raise CalendarError("Désactive d’abord la synchronisation du plan.", 409)
        spend = _Spend(SETTINGS)
        writable = self.repo.state()["selection"]["writable"]
        with self.calendar.operation(spend.deadline) as google:
            run = _Run(google, spend, self.repo.event_prefix(), writable)
            for session_id, event_id, calendar_id in self.repo.synced_events():
                if not self._remove(run, session_id, calendar_id, event_id):
                    break
        return self.calendar.status()

    def _pass(self, spend: _Spend) -> bool:
        """Reconcile once; False when the budget ran out before the end."""
        state = self.repo.plan_state()
        target = state["calendar_id"]
        if not (state["connected"] and state["enabled"] and target):
            return True
        zone = self.repo.timezone()
        today = self.today or datetime.now(ZoneInfo(zone)).date()
        # Yesterday's session keeps its event one more day, so the morning's
        # Garmin sync can mark it completed before it leaves the window.
        yesterday, last = today - timedelta(days=1), today + timedelta(days=WINDOW_DAYS)
        rows = [PlanRow(*r) for r in self.repo.plan_sessions(today, last, yesterday)]
        with self.calendar.operation(spend.deadline) as google:
            self.calendar._calendar(google, target, write=True)
            run = _Run(google, spend, self.repo.event_prefix(), state["writable"])
            since = datetime.combine(yesterday, time(), ZoneInfo(zone))
            listed = self._listed(run, target, since)
            for row in rows:
                current = listed.pop(run.prefix + str(row.id), None)
                if today <= row.date <= last and row.status in ACTIVE:
                    if not self._follow(run, zone, target, row, current):
                        return False
                elif row.status == "completed" or (
                    row.date == yesterday and row.status in ACTIVE
                ):
                    continue  # its event stays
                elif row.event_id and not self._remove(
                    run, row.id, row.calendar_id, row.event_id, current
                ):
                    return False
            # Arete's events whose session was deleted (or never recorded).
            orphans = {int(owner(e, run.prefix) or 0): e for e in listed.values()}
            statuses = self.repo.session_statuses(list(orphans))
            for session_id, event in orphans.items():
                if statuses.get(session_id) == "completed":
                    continue
                if not spend():
                    return False
                self._delete(run, target, event)
                if session_id in statuses:
                    self.repo.record_event(session_id, None, None, None, None)
        return True

    @staticmethod
    def _listed(run: _Run, target: str, since: datetime) -> dict[str, dict]:
        """This connection's live events in the target calendar from ``since``."""
        events: dict[str, dict] = {}
        page = None
        for _ in range(MAX_PAGES):
            data = run.google.call(
                "GET",
                run.google.events_path(target),
                params={
                    "privateExtendedProperty": f"arete_tag={run.prefix}",
                    "timeMin": since.isoformat(),
                    "maxResults": 250,
                    "fields": "nextPageToken,items(id,etag,status,extendedProperties)",
                    **({"pageToken": page} if page else {}),
                },
            )
            for event in data.get("items", []):
                if event.get("status") != "cancelled" and owner(event, run.prefix):
                    events[event["id"]] = event
            page = data.get("nextPageToken")
            if not page:
                return events
        raise CalendarError("Trop d’événements Arete dans le calendrier du plan.", 413)

    def _follow(
        self, run: _Run, zone: str, target: str, row: PlanRow, current: dict | None
    ) -> bool:
        """Create or update a session's event; False when out of budget."""
        # The target calendar changed: the old event leaves with it.
        if (
            row.event_id
            and row.calendar_id != target
            and not self._remove(run, row.id, row.calendar_id, row.event_id)
        ):
            return False
        event_id = run.prefix + str(row.id)
        body = event_body(row, zone, run.prefix)
        wanted = digest(body, target)
        if current is not None and wanted == row.digest and row.event_id == event_id:
            if current.get("etag") != row.etag:
                # Edited in Google only: kept until the session itself changes.
                self.repo.record_event(
                    row.id, target, event_id, current.get("etag"), wanted
                )
            return True
        if not run.spend():
            return False
        google, path = run.google, run.google.events_path(target, event_id)
        if current is not None:
            result = google.call("PUT", path, etag=current.get("etag"), json=body)
        else:
            try:
                result = google.call(
                    "POST", google.events_path(target), json={"id": event_id, **body}
                )
            except CalendarError as exc:
                if exc.status != 409:
                    raise
                # The id exists: our create whose response was lost, or an
                # event deleted earlier (Google keeps the id, and a deleted
                # event may come back with nothing but it). Never another's.
                existing = google.call("GET", path)
                deleted = existing.get("status") == "cancelled"
                if not deleted and owner(existing, run.prefix) != row.id:
                    logger.warning("Event id %s is not Arete's; left alone", event_id)
                    return True
                result = google.call(
                    "PUT",
                    path,
                    etag=existing.get("etag"),
                    json={**body, "status": "confirmed"},
                )
        self.repo.record_event(row.id, target, event_id, result.get("etag"), wanted)
        return True

    def _remove(
        self,
        run: _Run,
        session_id: int,
        calendar_id: str | None,
        event_id: str,
        current: dict | None = None,
    ) -> bool:
        """Delete a session's event and forget it; False when out of budget."""
        if calendar_id and calendar_id in run.writable:
            if current is None:
                try:
                    current = run.google.call(
                        "GET", run.google.events_path(calendar_id, event_id)
                    )
                except CalendarError as exc:
                    if exc.status not in (404, 410):
                        raise
            if (
                current
                and current.get("status") != "cancelled"
                and owner(current, run.prefix) == session_id
            ):
                if not run.spend():
                    return False
                self._delete(run, calendar_id, current)
        # Otherwise gone already, not Arete's, or in a calendar Arete may no
        # longer write: forget it without touching Google.
        self.repo.record_event(session_id, None, None, None, None)
        return True

    @staticmethod
    def _delete(run: _Run, calendar_id: str, event: dict) -> None:
        try:
            run.google.call(
                "DELETE",
                run.google.events_path(calendar_id, event["id"]),
                etag=event.get("etag"),
            )
        except CalendarError as exc:
            if exc.status not in (404, 410):
                raise
