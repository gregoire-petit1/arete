"""The briefing producer: one agent run a day, with a deterministic floor.

Called from two places — the scheduler after a successful sync, and
``GET /tips/daily`` when the day has no briefing yet. Both go through
``get_or_create_briefing``.

Sync on purpose. The scheduler already offloads blocking work with
an AnyIO worker and the API route is a plain ``def``, so staying
synchronous keeps this inside existing precedent instead of inventing a
blocking-DB-in-an-async-handler story the codebase does not have.

It never raises. A failed run is stored with ``status='failed'`` so it stays
visible, and the rule text is stored alongside so the dashboard always has
something concrete and numeric to show.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date

from arete.dataio.settings import get_user_settings
from arete.services.coaching_repository import Briefing, BriefingRepository

logger = logging.getLogger(__name__)

#: Bound on what we persist — a model that ignores "2 to 3 sentences" must not
#: push an essay into the dashboard card.
MAX_BRIEFING_CHARS = 1200


def briefing_enabled(user_id: int = 1) -> bool:
    """Whether the athlete wants a written briefing at all."""
    settings = get_user_settings(user_id) or {}
    return bool(settings.get("coach_briefing_enabled", True))


def _rule_floor(target_date: date) -> tuple[str, str]:
    """The deterministic tip and its priority — never raises."""
    from arete.services.coaching_rules import daily_rule_tip

    try:
        text, priority = daily_rule_tip(target_date)
        return text, priority
    except Exception:
        logger.warning("Rule-based tip failed", exc_info=True)
        return (
            "Pas assez de données pour un conseil aujourd'hui. "
            "Synchronise tes activités pour en avoir un.",
            "info",
        )


def generate_briefing(
    *,
    produce: Callable[[], str],
    trigger: str = "api",
    target_date: date | None = None,
    user_id: int = 1,
) -> Briefing:
    """Produce and persist one briefing. Never raises.

    The rule floor is computed first and always: it supplies the priority (the
    card's colour must not depend on a model) and it is the text we store when
    the agent is disabled or fails.
    """
    target_date = target_date or date.today()
    repo = BriefingRepository()
    rule_text, priority = _rule_floor(target_date)

    def store(text: str, source: str, status: str, error: str | None) -> Briefing:
        repo.create(
            text=text,
            briefing_date=target_date,
            priority=priority,
            source=source,
            status=status,
            error=error,
            trigger=trigger,
            user_id=user_id,
        )
        stored = repo.get_for_day(target_date, user_id=user_id)
        if stored is not None:
            return stored
        # Only reachable when we just stored a failure: hand back the floor.
        return Briefing(
            id=0,
            date=target_date,
            text=rule_text,
            priority=priority,
            source="rules",
            status="ok",
            error=error,
            trigger=trigger,
            created_at=None,
        )

    if not briefing_enabled(user_id):
        logger.info("Coach briefing disabled; storing the rule tip")
        return store(rule_text, "rules", "ok", None)

    try:
        text = produce()
    except Exception as exc:
        # A visible failure beats a silently empty card: the failed row is
        # kept for the audit view, and the floor is what gets served.
        logger.warning("Briefing agent run failed", exc_info=True)
        repo.create(
            text=rule_text,
            briefing_date=target_date,
            priority=priority,
            source="agent",
            status="failed",
            error=f"{type(exc).__name__}: {exc}"[:500],
            trigger=trigger,
            user_id=user_id,
        )
        return store(rule_text, "rules", "ok", None)

    logger.info("Briefing written by the agent (%d chars)", len(text))
    return store(text, "agent", "ok", None)


def get_or_create_briefing(
    *,
    produce: Callable[[], str],
    trigger: str = "api",
    target_date: date | None = None,
    user_id: int = 1,
) -> Briefing:
    """The day's briefing, producing it once if the day has none."""
    target_date = target_date or date.today()
    existing = BriefingRepository().get_for_day(target_date, user_id=user_id)
    if existing is not None:
        return existing
    return generate_briefing(
        produce=produce, trigger=trigger, target_date=target_date, user_id=user_id
    )
