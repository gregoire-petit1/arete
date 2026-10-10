"""Google Calendar operations and explicit, durable user approval."""

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from uuid import uuid4

from arete.services.calendar_models import (
    MAX_CALENDARS,
    MAX_EVENTS,
    MAX_PAGES,
    SCOPES,
    CalendarError,
    CalendarProposal,
    CalendarSelection,
    validate_window,
)
from arete.services.calendar_provider import ClerkProvider, GoogleCalendar
from arete.services.calendar_repository import CalendarRepository

logger = logging.getLogger(__name__)
VIRTUAL_CALENDAR_SUFFIX = "@group.v.calendar.google.com"
EVENT_FIELDS = "id,etag,status,summary,description,location,start,end,recurrence,recurringEventId,attendees,organizer,eventType,htmlLink,transparency"


def event_snapshot(event: dict) -> dict:
    return {
        key: event.get(key, "" if key in {"summary", "description", "location"} else {})
        for key in ("summary", "description", "location", "start", "end")
    }


def simple_event(event: dict) -> None:
    if (
        event.get("attendees")
        or event.get("recurrence")
        or event.get("eventType", "default") != "default"
    ):
        raise CalendarError(
            "Cette version modifie uniquement les événements simples sans invités, ou une occurrence isolée."
        )
    if event.get("status") == "cancelled":
        raise CalendarError("Événement déjà supprimé.", 409)


def matches_snapshot(event: dict, expected: dict) -> bool:
    """Google normalizes dateTime strings; compare instants, not their spelling."""
    if any(
        event.get(key, "") != expected.get(key, "")
        for key in ("summary", "description", "location")
    ):
        return False
    for key in ("start", "end"):
        actual, desired = event.get(key, {}), expected[key]
        if "date" in desired:
            if actual.get("date") != desired["date"]:
                return False
        else:
            try:
                if datetime.fromisoformat(actual["dateTime"]) != datetime.fromisoformat(
                    desired["dateTime"]
                ):
                    return False
            except (KeyError, ValueError):
                return False
    return True


class CalendarService:
    def __init__(self, provider: ClerkProvider, repository: CalendarRepository):
        self.provider, self.repo = provider, repository

    @contextmanager
    def operation(self, deadline: float | None = None) -> Iterator[GoogleCalendar]:
        if not self.repo.state()["enabled"]:
            raise CalendarError(
                "Connecte Google Calendar dans Réglages → Connexions.", 409
            )
        with self.provider.session(deadline) as http:
            yield GoogleCalendar(http, self.provider.token(http))

    def status(self) -> dict:
        state = self.repo.state()
        plan = self.repo.plan_state()
        return {
            "configured": True,
            "connected": state["enabled"],
            "selection": state["selection"],
            # What the browser asks Google for before calling connect().
            "scopes": SCOPES,
            # The training plan followed into one calendar (services/calendar_plan.py).
            "plan": {
                key: plan[key]
                for key in ("enabled", "calendar_id", "synced_at", "error", "events")
            },
        }

    def connect(self) -> dict:
        """Activate access once Google granted the calendar scopes.

        The browser asks Google first (Clerk's incremental consent); only a token
        carrying the scopes turns access on, with an empty selection as after
        any reconnection.
        """
        revision = self.repo.state()["revision"]
        with self.provider.session() as http:
            self.provider.token(http)
        self.repo.configure(
            enabled=True,
            selection={"readable": [], "writable": []},
            expected_revision=revision,
        )
        return self.status()

    def disconnect(self) -> dict:
        self.repo.configure(enabled=False, selection={"readable": [], "writable": []})
        # Its events stay in Google: without the grant Arete cannot remove them.
        self.repo.configure_plan(enabled=False)
        try:
            with self.provider.session() as http:
                self.provider.revoke(http)
        except CalendarError:
            return {
                "connected": False,
                "revoked": False,
                "warning": "Accès Arete désactivé. Révocation distante échouée : réessaie ou retire l’accès dans Google.",
            }
        return {"connected": False, "revoked": True}

    def calendars(self) -> list[dict]:
        with self.operation() as google:
            result: list[dict] = []
            page = None
            for _ in range(MAX_PAGES):
                data = google.call(
                    "GET",
                    "users/me/calendarList",
                    params={"maxResults": 100, **({"pageToken": page} if page else {})},
                )
                result.extend(
                    {
                        key: c.get(key)
                        for key in ("id", "summary", "timeZone", "accessRole")
                    }
                    for c in data.get("items", [])
                )
                if len(result) > MAX_EVENTS:
                    raise CalendarError("Liste de calendriers trop volumineuse.", 413)
                page = data.get("nextPageToken")
                if not page:
                    return result
        raise CalendarError("Liste de calendriers au-delà de 10 pages.", 413)

    def select(self, selection: CalendarSelection) -> dict:
        revision = self.repo.state()["revision"]
        with self.operation() as google:
            for calendar_id in selection.readable:
                self._calendar(
                    google,
                    calendar_id,
                    write=calendar_id in selection.writable,
                    selected=False,
                )
        self.repo.configure(
            enabled=True, selection=selection.model_dump(), expected_revision=revision
        )
        return self.status()

    def _calendar(
        self,
        google: GoogleCalendar,
        calendar_id: str,
        *,
        write: bool = False,
        selected: bool = True,
    ) -> dict:
        from urllib.parse import quote

        state = self.repo.state()
        permission = "writable" if write else "readable"
        if not state["enabled"]:
            raise CalendarError("Calendrier non autorisé dans les réglages Arete.", 403)
        allowed = state["selection"][permission]
        if selected and calendar_id not in allowed:
            raise CalendarError(
                "Calendrier non autorisé dans les réglages Arete. Identifiants "
                f"autorisés : {', '.join(allowed) or 'aucun'}.",
                403,
            )
        data = google.call(
            "GET", "users/me/calendarList/" + quote(calendar_id, safe="")
        )
        roles = {"owner", "writer"} if write else {"owner", "writer", "reader"}
        if data.get("accessRole") not in roles:
            raise CalendarError("Droits Google insuffisants sur ce calendrier.", 403)
        return data

    def _selected(self) -> list[str]:
        ids: list[str] = self.repo.state()["selection"]["readable"]
        if not ids:
            raise CalendarError(
                "Sélectionne d’abord les calendriers dans les réglages.", 409
            )
        assert len(ids) <= MAX_CALENDARS
        return ids

    def events(self, start: str, end: str, *, deadline: float | None = None) -> dict:
        validate_window(start, end)
        result: list[dict] = []
        selected_calendars: list[dict] = []
        pages = 0
        with self.operation(deadline) as google:
            writable = self.repo.state()["selection"]["writable"]
            for calendar_id in self._selected():
                calendar = self._calendar(google, calendar_id)
                selected_calendars.append(
                    {
                        "id": calendar_id,
                        "summary": calendar.get("summary", calendar_id),
                        "timezone": calendar.get("timeZone", "UTC"),
                        "writable": calendar_id in writable,
                    }
                )
                page = None
                for _ in range(MAX_PAGES):
                    pages += 1
                    if pages > MAX_PAGES:
                        raise CalendarError(
                            "Lecture au-delà de 10 pages. Réduis la période ou les calendriers.",
                            413,
                        )
                    data = google.call(
                        "GET",
                        google.events_path(calendar_id),
                        params={
                            "timeMin": start,
                            "timeMax": end,
                            "singleEvents": "true",
                            "orderBy": "startTime",
                            "maxResults": MAX_EVENTS,
                            "fields": f"nextPageToken,items({EVENT_FIELDS})",
                            **({"pageToken": page} if page else {}),
                        },
                    )
                    result.extend(
                        {
                            "calendar_id": calendar_id,
                            "calendar_name": calendar.get("summary", calendar_id),
                            "timezone": calendar.get("timeZone", "UTC"),
                            **event,
                        }
                        for event in data.get("items", [])
                    )
                    if len(result) > MAX_EVENTS:
                        raise CalendarError(
                            "Plus de 500 événements. Réduis la période.", 413
                        )
                    page = data.get("nextPageToken")
                    if not page:
                        break
                if page:
                    raise CalendarError(
                        "Lecture incomplète : pagination hors limites.", 413
                    )
        return {"calendars": selected_calendars, "events": result}

    def availability(
        self, start: str, end: str, *, deadline: float | None = None
    ) -> dict:
        validate_window(start, end)
        with self.operation(deadline) as google:
            selected = self._selected()
            for calendar_id in selected:
                self._calendar(google, calendar_id)
            # Google's virtual calendars (week numbers, holidays, birthdays) have
            # no free/busy data and answer notFound; they never make a slot busy.
            skipped = [c for c in selected if c.endswith(VIRTUAL_CALENDAR_SUFFIX)]
            ids = [c for c in selected if c not in skipped]
            if not ids:
                return {"calendars": {}, "skipped": skipped}
            result = google.call(
                "POST",
                "freeBusy",
                json={
                    "timeMin": start,
                    "timeMax": end,
                    "calendarExpansionMax": MAX_CALENDARS,
                    "items": [{"id": c} for c in ids],
                },
            )
            calendars = result.get("calendars", {})
            if set(calendars) != set(ids) or any(
                c.get("errors") for c in calendars.values()
            ):
                raise CalendarError(
                    "Disponibilités partiellement indisponibles ; aucune conclusion possible.",
                    502,
                )
            if sum(len(c.get("busy", [])) for c in calendars.values()) > MAX_EVENTS:
                raise CalendarError("Trop de créneaux. Réduis la période.", 413)
            return {**result, "skipped": skipped}

    def propose(
        self,
        proposal: CalendarProposal,
        thread_id: str,
        *,
        deadline: float | None = None,
    ) -> dict:
        if not thread_id:
            raise CalendarError("Conversation requise pour proposer une action.")
        revision = self.repo.state()["revision"]
        with self.operation(deadline) as google:
            calendar = self._calendar(google, proposal.calendar_id, write=True)
            before, etag = None, None
            if proposal.event_id:
                existing = google.call(
                    "GET", google.events_path(proposal.calendar_id, proposal.event_id)
                )
                simple_event(existing)
                before, etag = event_snapshot(existing), existing.get("etag")
                if not etag:
                    raise CalendarError("Version de l’événement manquante.", 502)
        action_id = uuid4().hex
        payload = {
            "operation": proposal.operation,
            "calendar_id": proposal.calendar_id,
            "calendar_name": calendar.get("summary", proposal.calendar_id),
            "timezone": calendar.get("timeZone", "UTC"),
            "event_id": proposal.event_id or uuid4().hex,
            "before": before,
            "after": proposal.event.google_body() if proposal.event else None,
            "etag": etag,
        }
        self.repo.add(action_id, revision, thread_id, payload)
        return self.repo.get(action_id)

    def decide(self, action_id: str, decision: str) -> dict:
        assert decision in {"approve", "reject"}, "Unknown approval decision"
        action = self.repo.get(action_id)
        if not self.repo.claim(action_id, decision):
            return self.repo.get(action_id)
        if decision == "reject":
            return self.repo.get(action_id)
        started_write = False
        try:
            with self.operation() as google:
                self._calendar(google, action["calendar_id"], write=True)
                path = google.events_path(action["calendar_id"], action["event_id"])
                if action["operation"] != "create":
                    current = google.call("GET", path)
                    simple_event(current)
                    if current.get("etag") != action["etag"]:
                        raise CalendarError(
                            "Événement modifié : nouvelle proposition nécessaire.", 412
                        )
                # Only the persisted proposal reaches Google; the decision has no arguments.
                state = self.repo.state()
                if not state["enabled"] or state["revision"] != action["revision"]:
                    raise CalendarError(
                        "Permissions modifiées pendant la validation.", 409
                    )
                started_write = True
                if action["operation"] == "create":
                    result = google.call(
                        "POST",
                        google.events_path(action["calendar_id"]),
                        json={"id": action["event_id"], **action["after"]},
                    )
                elif action["operation"] == "update":
                    result = google.call(
                        "PATCH", path, etag=action["etag"], json=action["after"]
                    )
                else:
                    result = google.call("DELETE", path, etag=action["etag"])
            self.repo.finish(
                action_id,
                "succeeded",
                {
                    "message": "Modification enregistrée dans Google Calendar.",
                    "event_id": action["event_id"],
                    "html_link": result.get("htmlLink"),
                },
            )
        except CalendarError as exc:
            status = "uncertain" if exc.uncertain and started_write else "failed"
            self.repo.finish(action_id, status, {"message": str(exc)})
        except Exception:
            # A database failure after Google committed must never cause a replay.
            logger.exception(
                "Calendar action %s failed after_write=%s", action_id, started_write
            )
            self.repo.finish(
                action_id,
                "uncertain" if started_write else "failed",
                {
                    "message": "Échec interne ; vérifie l’état avant toute nouvelle action."
                },
            )
        return self.repo.get(action_id)

    def verify(self, action_id: str) -> dict:
        action = self.repo.get(action_id)
        if action["status"] != "uncertain":
            return action
        with self.operation() as google:
            self._calendar(google, action["calendar_id"])
            try:
                current = google.call(
                    "GET", google.events_path(action["calendar_id"], action["event_id"])
                )
                absent = current.get("status") == "cancelled"
            except CalendarError as exc:
                if exc.status != 404:
                    raise
                absent, current = True, {}
        matches = (
            absent
            if action["operation"] == "delete"
            else not absent and matches_snapshot(current, action["after"])
        )
        self.repo.finish(
            action_id,
            "succeeded" if matches else "uncertain",
            {
                "message": "État attendu confirmé dans Google Calendar."
                if matches
                else "Résultat non confirmé. Vérifie dans Google Calendar ; aucune écriture rejouée."
            },
        )
        return self.repo.get(action_id)
