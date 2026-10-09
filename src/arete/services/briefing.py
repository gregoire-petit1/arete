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
import threading
from collections.abc import Callable
from datetime import date, timedelta

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


_WEEKDAYS = ("lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche")
_GOALS = {
    "build": "progresser (bloc de développement)",
    "peak": "affûtage avant un objectif",
    "maintenance": "maintien",
    "recovery": "récupération",
}


def _fmt(value: float | None, pattern: str) -> str:
    return pattern.format(value) if value is not None else "indisponible"


def _block(title: str, read: Callable[[], list[str]]) -> str:
    """One section of the facts; a failed read says so instead of failing."""
    try:
        lines = read()
    except Exception:
        logger.warning("Briefing facts: %s unavailable", title, exc_info=True)
        lines = ["indisponible"]
    return f"{title} :\n" + "\n".join(f"- {line}" for line in lines or ["aucune"])


def briefing_facts(target_date: date, rule_text: str) -> str:
    """Everything the briefing needs, computed here so the model needs no tool.

    The agent used to read its load and form through tools — at least three
    model requests and 99 s on the free tier — while the rule floor had just
    computed the same numbers. It never saw today's plan either.
    """
    from arete.garmin.readiness import compute_readiness
    from arete.garmin.repository import GarminRepository
    from arete.services.analytics import list_sessions
    from arete.services.coaching_rules import rule_facts

    def load() -> list[str]:
        facts = rule_facts(target_date)
        return [
            f"Charge aiguë/chronique (ACWR, sur 28 jours) : {_fmt(facts.acwr, '{:.2f}')}",
            f"Fraîcheur (TSB, modèle sur 42 jours) : {_fmt(facts.tsb, '{:+.0f}')}",
            "Préparation estimée par la charge : "
            + _fmt(facts.readiness_score, "{:.0f}/100"),
            f"Objectif de la période : {_GOALS.get(facts.fitness_goal, facts.fitness_goal)}",
        ]

    def garmin() -> list[str]:
        for offset, label in ((0, "cette nuit"), (1, "la nuit précédente")):
            score = compute_readiness(target_date - timedelta(days=offset))
            if score is not None:
                return [f"Préparation Garmin (VFC, sommeil) {label} : {score}/100"]
        return ["pas de mesure Garmin récente"]

    def planned() -> list[str]:
        sessions = GarminRepository().list_planned_sessions(
            start_date=target_date, end_date=target_date, status=None, limit=5
        )
        return [
            " — ".join(
                str(part)
                for part in (
                    s.session_type.value,
                    f"{s.target_duration_min} min" if s.target_duration_min else None,
                    s.target_hr_zone,
                    s.description,
                )
                if part
            )
            for s in sessions
        ]

    def recent() -> list[str]:
        rows = list_sessions(limit=3)["sessions"]
        return [
            ", ".join(
                part
                for part in (
                    f"{r['date']} {r['sport']} « {r['name'] or 'sans titre'} »",
                    f"{(r['duration_sec'] or 0) // 60} min",
                    f"{r['distance_m'] / 1000:.1f} km" if r["distance_m"] else None,
                    f"FC moy {r['avg_hr']:.0f}" if r["avg_hr"] else None,
                    f"allure {r['pace_display']}" if r["avg_pace_sec_km"] else None,
                    f"RPE {r['rpe']}" if r["rpe"] else None,
                    f"notes : {r['notes']}" if r["notes"] else None,
                )
                if part
            )
            for r in rows
        ]

    def yesterday() -> list[str]:
        previous = BriefingRepository().get_for_day(target_date - timedelta(days=1))
        return [previous.text] if previous else []

    weekday = _WEEKDAYS[target_date.weekday()]
    return "\n\n".join(
        [
            f"Nous sommes {weekday} {target_date.isoformat()}.",
            f"Conseil calculé par les règles : {rule_text}",
            _block("Charge et forme", load),
            _block("Récupération", garmin),
            _block("Séance(s) prévue(s) aujourd'hui", planned),
            _block("Dernières séances réalisées", recent),
            _block("Ton briefing d'hier", yesterday),
        ]
    )


def generate_briefing(
    *,
    produce: Callable[[str], str],
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
        text = produce(briefing_facts(target_date, rule_text))
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


#: Two tabs opening the dashboard at once must not pay for two briefings.
_produce_lock = threading.Lock()


def get_or_create_briefing(
    *,
    produce: Callable[[str], str],
    trigger: str = "api",
    target_date: date | None = None,
    user_id: int = 1,
) -> Briefing:
    """The day's briefing, producing it once if the day has none."""
    target_date = target_date or date.today()
    existing = BriefingRepository().get_for_day(target_date, user_id=user_id)
    if existing is not None:
        return existing
    with _produce_lock:
        existing = BriefingRepository().get_for_day(target_date, user_id=user_id)
        if existing is not None:
            return existing
        return generate_briefing(
            produce=produce, trigger=trigger, target_date=target_date, user_id=user_id
        )
