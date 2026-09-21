"""The briefing producer: one agent run a day, with a deterministic floor.

Called from two places — the scheduler after a successful sync, and
``GET /tips/daily`` when the day has no briefing yet. Both go through
``get_or_create_briefing``.

Sync on purpose. The scheduler already offloads blocking work with
``asyncio.to_thread`` and the API route is a plain ``def``, so staying
synchronous keeps this inside existing precedent instead of inventing a
blocking-DB-in-an-async-handler story the codebase does not have.

It never raises. A failed run is stored with ``status='failed'`` so it stays
visible, and the rule text is stored alongside so the dashboard always has
something concrete and numeric to show.
"""

from __future__ import annotations

import logging
from datetime import date

from arete.coach.repository import Briefing, BriefingRepository
from arete.dataio.settings import get_user_settings

logger = logging.getLogger(__name__)

#: The unattended run gets more room than a chat turn: search + load + three
#: to five metric reads + ledger read + ledger write is 10-14 steps, and
#: nobody is waiting on it.
BRIEFING_RECURSION_LIMIT = 40

#: Bound on what we persist — a model that ignores "2 to 3 sentences" must not
#: push an essay into the dashboard card.
MAX_BRIEFING_CHARS = 1200

BRIEFING_PROMPT = """Tu es le coach running/trail de l'athlète. Tu écris son \
briefing du matin, qu'il lira sur son tableau de bord sans pouvoir te répondre.

Méthode:
1. Charge le toolkit `analytics` (`search_toolkits` puis `load_toolkit`).
2. Lis sa charge et sa forme. Si un chiffre te surprend, regarde une autre \
fenêtre ou ses séances récentes avant de conclure.
3. Lis ton journal mémoire pour savoir ce que vous vous êtes déjà dit.
4. Écris le briefing, puis note dans ton journal ce que tu as retenu du jour.

Le briefing: 2 à 3 phrases, en français, à la deuxième personne. Cite les \
chiffres qui le justifient et la période sur laquelle tu les lis, en français \
courant ("sur 28 jours") — jamais un nom de champ ni une valeur brute d'outil. \
Termine par ce que l'athlète fait AUJOURD'HUI, concrètement. Pas de \
préambule, pas de liste, pas de formule creuse type "pense à bien récupérer". \
Pas de diagnostic médical.

Ta réponse finale est le briefing seul, rien d'autre."""


def briefing_enabled(user_id: int = 1) -> bool:
    """Whether the athlete wants a written briefing at all."""
    settings = get_user_settings(user_id) or {}
    return bool(settings.get("coach_briefing_enabled", True))


def _rule_floor(target_date: date) -> tuple[str, str]:
    """The deterministic tip and its priority — never raises."""
    from arete.api.ai_tips import daily_rule_tip

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


def _run_agent() -> str:
    """One agent run. Returns the briefing text; raises on any failure."""
    from arete.agent.agent import build_briefing_agent
    from arete.agent.context import AgentContext
    from arete.agent.filesystem import rotate_sessions_ledger

    # Before the run, not after: a briefing every morning grows the journal
    # the agent reads back on every turn, and the run should not be the one
    # paying for yesterday's overflow.
    rotate_sessions_ledger()

    graph = build_briefing_agent()
    result = graph.invoke(
        {"messages": [{"role": "user", "content": "Écris mon briefing du jour."}]},
        context=AgentContext(source={}),
        config={"recursion_limit": BRIEFING_RECURSION_LIMIT},
    )
    messages = result.get("messages", [])
    if not messages:
        raise RuntimeError("Agent returned no messages")
    text = (messages[-1].text or "").strip()
    if not text:
        raise RuntimeError("Agent returned an empty briefing")
    if len(text) > MAX_BRIEFING_CHARS:
        raise RuntimeError(
            f"Briefing too long for the dashboard card ({len(text)} chars)"
        )
    return text


def generate_briefing(
    *,
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
        text = _run_agent()
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
    trigger: str = "api",
    target_date: date | None = None,
    user_id: int = 1,
) -> Briefing:
    """The day's briefing, producing it once if the day has none."""
    target_date = target_date or date.today()
    existing = BriefingRepository().get_for_day(target_date, user_id=user_id)
    if existing is not None:
        return existing
    return generate_briefing(trigger=trigger, target_date=target_date, user_id=user_id)
