"""Compose Calendar dependencies without importing the coaching stack."""

import hashlib
import logging

from arete.config import config
from arete.dataio import plan_changes
from arete.services.calendar import CalendarService
from arete.services.calendar_models import CalendarError
from arete.services.calendar_plan import Budget, PlanSync
from arete.services.calendar_provider import ClerkProvider
from arete.services.calendar_repository import CalendarRepository

logger = logging.getLogger(__name__)


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


def plan_sync_services() -> list[CalendarService]:
    """The connections of this environment that follow the training plan.

    No user is signed in here (cron, after a response): the provider is
    rebuilt from the Clerk user id stored when the sync was turned on.
    """
    if not config.google_calendar_configured:
        return []
    services = []
    for key, clerk_user_id in CalendarRepository.plan_sync_accounts():
        service = get_calendar_service(clerk_user_id)
        # Another environment's connection (a preview) is its own business.
        if service.repo.key == key:
            services.append(service)
    return services


def sync_training_plan(budget: Budget) -> str:
    """Follow the plan into Google Calendar; best effort, never raises."""
    plan_changes.clear()  # this request's changes are covered by this run
    try:
        outcomes = [PlanSync(service).run(budget) for service in plan_sync_services()]
    except Exception:  # noqa: BLE001 - never fail the job or request around it
        logger.exception("Training plan calendar sync failed")
        return "failed"
    return ", ".join(outcomes) or "disabled"
