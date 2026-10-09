"""Compose Calendar dependencies without importing the coaching stack."""

import hashlib

from arete.config import config
from arete.services.calendar import CalendarService
from arete.services.calendar_models import CalendarError
from arete.services.calendar_provider import ConnectProvider
from arete.services.calendar_repository import CalendarRepository


def get_calendar_service() -> CalendarService:
    if not config.google_calendar_configured:
        raise CalendarError("Google Calendar n’est pas configuré sur ce serveur.", 503)
    key = hashlib.sha256(
        f"{config.google_calendar_connector}:{config.google_calendar_subject}:{config.google_calendar_environment}".encode()
    ).hexdigest()
    return CalendarService(
        ConnectProvider(
            config.google_calendar_connector,
            config.google_calendar_subject,
            lambda: config.vercel_connect_credential,
        ),
        CalendarRepository(key),
    )
