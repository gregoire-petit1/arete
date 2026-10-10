"""Calendar contracts shared by the API, provider adapter and domain service."""

from contextlib import suppress
from datetime import date, datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, model_validator

MAX_CALENDARS = 10
MAX_WINDOW_DAYS = 31
MAX_EVENTS = 500
MAX_PAGES = 10
MAX_OPERATION_SECONDS = 60
HTTP_TIMEOUT_SECONDS = 15
ACTION_TTL_SECONDS = 900
MAX_PENDING_ACTIONS = 100
MAX_ACTION_CHARS = 10_000
MAX_RESPONSE_BYTES = 1_000_000
MAX_RESPONSE_CHUNKS = 1024
SCOPES = [
    "https://www.googleapis.com/auth/calendar.calendarlist.readonly",
    "https://www.googleapis.com/auth/calendar.events",
    "https://www.googleapis.com/auth/calendar.events.freebusy",
]


class CalendarError(Exception):
    def __init__(self, message: str, status: int = 400, *, uncertain: bool = False):
        super().__init__(message)
        self.status = status
        self.uncertain = uncertain


class CalendarSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    readable: list[str] = Field(default_factory=list, max_length=MAX_CALENDARS)
    writable: list[str] = Field(default_factory=list, max_length=MAX_CALENDARS)

    @model_validator(mode="after")
    def validate_selection(self):
        if len(set(self.readable)) != len(self.readable) or len(
            set(self.writable)
        ) != len(self.writable):
            raise ValueError("Calendriers dupliqués.")
        if not set(self.writable) <= set(self.readable):
            raise ValueError("Un calendrier modifiable doit être lisible.")
        if any(not c or len(c) > 1024 for c in self.readable):
            raise ValueError("Identifiant de calendrier invalide.")
        return self


class EventDraft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    summary: str = Field(min_length=1, max_length=300)
    start: str = Field(max_length=64)
    end: str = Field(max_length=64)
    timezone: str = Field(default="Europe/Paris", max_length=100)
    all_day: bool = False
    description: str = Field(default="", max_length=4000)
    location: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def validate_times(self):
        try:
            zone = ZoneInfo(self.timezone)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Fuseau horaire inconnu.") from exc
        if self.all_day:
            start, end = date.fromisoformat(self.start), date.fromisoformat(self.end)
        else:
            start, end = (
                datetime.fromisoformat(self.start),
                datetime.fromisoformat(self.end),
            )
            for instant in (start, end):
                if (
                    instant.tzinfo is None
                    or instant.astimezone(zone).utcoffset() != instant.utcoffset()
                ):
                    raise ValueError(
                        "Date avec décalage UTC correspondant au fuseau requise."
                    )
        if end <= start or end - start > timedelta(days=MAX_WINDOW_DAYS):
            raise ValueError("Durée invalide (maximum 31 jours, fin exclusive).")
        return self

    def google_body(self) -> dict:
        def point(value):
            return (
                {"date": value}
                if self.all_day
                else {"dateTime": value, "timeZone": self.timezone}
            )

        return {
            "summary": self.summary,
            "description": self.description,
            "location": self.location,
            "start": point(self.start),
            "end": point(self.end),
        }


class CalendarProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["create", "update", "delete"]
    calendar_id: str = Field(min_length=1, max_length=1024)
    event_id: str | None = Field(default=None, max_length=1024)
    event: EventDraft | None = None

    @model_validator(mode="after")
    def validate_operation(self):
        if (self.operation == "create") != (self.event_id is None):
            raise ValueError(
                "Identifiant requis uniquement pour modifier ou supprimer."
            )
        if (self.operation == "delete") != (self.event is None):
            raise ValueError("Contenu requis uniquement pour créer ou modifier.")
        return self


def validate_window(start: str, end: str) -> None:
    a: datetime | None = None
    b: datetime | None = None
    with suppress(ValueError):
        a, b = datetime.fromisoformat(start), datetime.fromisoformat(end)
    if a is None or b is None or a.tzinfo is None or b.tzinfo is None:
        raise CalendarError(
            "Dates invalides : horodatages ISO avec décalage UTC requis, ex. "
            f"2026-10-10T00:00:00+02:00 (reçu : start={start!r}, end={end!r})."
        )
    if not timedelta(0) < b - a <= timedelta(days=MAX_WINDOW_DAYS):
        raise CalendarError(
            "Période invalide : la fin doit suivre le début, 31 jours maximum."
        )
