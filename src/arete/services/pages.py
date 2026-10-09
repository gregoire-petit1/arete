"""Read the same domain data used by each UI page."""

from datetime import date, timedelta
from typing import Any


def _strength_sessions(**filters: Any) -> list[dict[str, Any]]:
    """Strength sessions as the Log lists them: no per-exercise detail."""
    from arete.strength.repository import StrengthRepository

    return [
        _without_nulls(
            {
                "date": s.date.isoformat(),
                "name": s.name,
                "program": s.program,
                "duration_min": s.duration_min,
                "overall_rpe": s.overall_rpe,
                "notes": s.notes,
            }
        )
        for s in StrengthRepository().list_sessions(**filters)
    ]


def _dashboard() -> dict[str, Any]:
    """What the Dashboard shows: the bars, today's plan and sessions, the briefing.

    The read used to stop at the bars, so "what do I do today?" asked from the
    Dashboard needed another tool call to find the plan on screen.
    """
    from arete.garmin.repository import GarminRepository
    from arete.services.analytics import list_sessions
    from arete.services.coaching_repository import BriefingRepository
    from arete.services.metrics import get_player_stats
    from arete.services.plan_repository import PlanDecisionRepository
    from arete.services.planning import _session_to_dict

    today = date.today()
    planned = GarminRepository().list_planned_sessions(
        start_date=today, end_date=today, status=None, limit=10
    )
    briefing = BriefingRepository().get_for_day(today)
    return {
        "player_stats": get_player_stats().model_dump(mode="json"),
        "planned_today": [_without_nulls(_session_to_dict(s)) for s in planned],
        "done_today": [
            s
            for s in list_sessions(limit=5, for_model=True)["sessions"]
            if s["date"] == today.isoformat()
        ],
        "strength_today": _strength_sessions(start_date=today, end_date=today),
        "briefing_today": briefing.text if briefing else None,
        # What the morning's readiness did to the plan, and why: "why did my
        # session change?" is answered from the page.
        "plan_decisions_today": [
            {
                "planned_session_id": d.planned_session_id,
                "decision": d.decision,
                "reason": d.reason,
                "reverted": d.reverted_at is not None,
            }
            for d in PlanDecisionRepository().list_for_day(today)
        ],
    }


def _analytics() -> dict[str, Any]:
    """The Analytics page as the coach needs it: what each card says.

    Every card carried a 30-point daily series for its chart, and the series
    were 84 % of the read — 9.7k of 11.6k tokens on real data, the zones card
    alone 3.1k. The model reasons from the headline, the comparison with the
    previous period and the card's own French insight; a trend over a chosen
    window is what the analytics toolkit is for.
    """
    from arete.services.analytics import get_overview

    overview = get_overview(period="30d")
    cards = {
        name: {k: v for k, v in card.items() if k != "series"}
        for name, card in overview.get("cards", {}).items()
    }
    return {
        "overview": {**overview, "cards": cards},
        "trends": "analytics toolkit: get_workload(days), get_fitness(days)",
    }


#: What a Planning page read covers: the week just gone and three ahead.
#: The whole plan used to be read at once, and a plan runs months out — 109
#: sessions to December on real data, 35k characters — so it overflowed the
#: read bound and the coach on the Planning page could not see the plan at
#: all. Anything further is one `list_planned` call away in the planning
#: toolkit.
PLANNING_PAST_DAYS = 7
PLANNING_AHEAD_DAYS = 21


def _without_nulls(row: dict[str, Any]) -> dict[str, Any]:
    """Drop empty fields: a null is a token spent saying nothing."""
    return {k: v for k, v in row.items() if v is not None and v != ""}


def _planning() -> dict[str, Any]:
    from arete.garmin.repository import GarminRepository
    from arete.services.planning import _session_to_dict

    today = date.today()
    start = today - timedelta(days=PLANNING_PAST_DAYS)
    end = today + timedelta(days=PLANNING_AHEAD_DAYS)
    # API default params are FastAPI Query objects; call with plain values.
    sessions = GarminRepository().list_planned_sessions(
        start_date=start, end_date=end, status=None, limit=200
    )
    rows = sorted(
        (_without_nulls(_session_to_dict(s)) for s in sessions),
        key=lambda row: row["date"],
    )
    return {
        "window": {"from": start.isoformat(), "to": end.isoformat()},
        "planned_sessions": rows,
        "beyond_the_window": "planning toolkit: list_planned(start_date, end_date)",
    }


def _log() -> dict[str, Any]:
    """Both tabs of the Log: cardio sessions and strength sessions."""
    from arete.services.analytics import list_sessions

    return {
        "recent_sessions": list_sessions(limit=20, offset=0, for_model=True),
        "recent_strength_sessions": _strength_sessions(limit=10),
    }


def _settings() -> dict[str, Any]:
    from arete.services.settings import get_settings

    # Identity stays out of the prompt: the coach has no use for it, and the
    # page data goes to the model provider (and to LangSmith when tracing).
    return {
        "settings": get_settings().model_dump(
            mode="json", exclude={"email", "display_name"}
        )
    }


def _profile() -> dict[str, Any]:
    from arete.services.gamification import snapshot

    state = snapshot()
    # The ledger and identity are deliberately not sent to the model.
    return {
        "player": {
            key: state[key]
            for key in (
                "enabled",
                "level",
                "rank",
                "xp",
                "shards",
                "sessions",
                "equipped",
                "week",
            )
        }
    }


_PAGE_FETCHERS = {
    "profile": _profile,
    "dashboard": _dashboard,
    "analytics": _analytics,
    "planning": _planning,
    "log": _log,
    "settings": _settings,
}


def get_page_data(page: str) -> dict[str, Any]:
    from arete.services.gamification import preference

    result = _PAGE_FETCHERS[page]()
    if preference()["enabled"]:
        result["coach_identity"] = (
            "Chiron — Coach Arete. Mentor grec calme et exigeant, distinct du personnage joueur. Explique les faits sans inventer de récompenses."
        )
    return result
