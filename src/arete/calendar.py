"""Compose Calendar dependencies without importing the coaching stack."""

import hashlib

from arete.config import config
from arete.services.calendar import CalendarService
from arete.services.calendar_models import CalendarError
from arete.services.calendar_provider import ClerkProvider
from arete.services.calendar_repository import CalendarRepository


def get_calendar_service(clerk_user_id: str) -> CalendarService:
    """The calendar of one signed-in account: its Google grant, its selection."""
    if not config.google_calendar_configured:
        raise CalendarError(
            "Google Calendar nécessite la connexion Clerk sur ce serveur.", 503
        )
    if not clerk_user_id:
        raise CalendarError(
            "Google Calendar nécessite un compte connecté avec Google.", 403
        )
    key = hashlib.sha256(
        f"clerk:{clerk_user_id}:{config.google_calendar_environment}".encode()
    ).hexdigest()
    return CalendarService(ClerkProvider(clerk_user_id), CalendarRepository(key))
