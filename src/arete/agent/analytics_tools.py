"""Analytics toolkit — narrow reads, instead of the 30-day page dump.

``get_page_context("analytics")`` answers with ``get_overview(period="30d")``:
eight DuckDB queries plus a 42-day EWMA, in one block, always the same window.
Fine to ground a first answer, useless to compare two periods or to look up
one number.

These tools wrap route functions that already exist, so the agent reads the
same values the pages render. Read-only. Each one validates its own bounds:
the routes get theirs from FastAPI ``Query`` metadata, which does nothing when
the function is called directly.
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import BaseTool, tool

from arete.agent.tools import MAX_TOOL_OUTPUT_CHARS

#: Mirrors the routes' own Query bounds — see api/metrics.py.
WORKLOAD_DAYS_RANGE = (7, 90)
FITNESS_DAYS_RANGE = (14, 120)
MAX_SESSIONS = 100
SPORT_TYPES = ("cardio", "strength", "mixed")


def _out(payload: Any) -> str:
    """Serialize a tool result, bounded like the page-source tool."""
    rendered = json.dumps(payload, ensure_ascii=False, default=str)
    if len(rendered) > MAX_TOOL_OUTPUT_CHARS:
        return json.dumps(
            {
                "error": (
                    f"Result too large for one read ({len(rendered)} chars). "
                    "Ask for a narrower window or a smaller limit."
                )
            }
        )
    return rendered


def _disambiguate_window(payload: dict[str, Any], days: int) -> dict[str, Any]:
    """Say which number is the window and which is the coverage.

    ``days_analyzed`` means "days that had data in them", but sitting next to
    a ``days`` argument it reads as the window — and models duly wrote "ACWR
    sur 5 jours" for a 28-day request. Renaming it at the tool boundary is
    cheaper and more reliable than asking the model to be careful.
    """
    out = dict(payload)
    out["window_days"] = days
    if "days_analyzed" in out:
        out["days_with_data"] = out.pop("days_analyzed")
    return out


def _error(message: str) -> str:
    return json.dumps({"error": message}, ensure_ascii=False)


def _guard(value: int, bounds: tuple[int, int], name: str) -> str | None:
    low, high = bounds
    if not low <= value <= high:
        return _error(f"{name} must be between {low} and {high}, got {value}")
    return None


@tool
def get_workload(days: int = 28) -> str:
    """Training load over a window: ACWR (injury-risk ratio), monotony, strain,
    acute and chronic load, each with its interpretation zone.

    Args:
        days: Window to analyze, 7 to 90 (default 28).
    """
    invalid = _guard(days, WORKLOAD_DAYS_RANGE, "days")
    if invalid:
        return invalid
    try:
        from arete.api.metrics import get_workload_metrics

        payload = get_workload_metrics(days=days).model_dump(mode="json")
        return _out(_disambiguate_window(payload, days))
    except Exception as exc:
        return _error(f"{type(exc).__name__}: {exc}")


@tool
def get_fitness(days: int = 42) -> str:
    """Fitness-fatigue model over a window: CTL (fitness), ATL (fatigue),
    TSB (form) with its zone, readiness and the weekly CTL ramp rate.

    Args:
        days: Window to analyze, 14 to 120 (default 42).
    """
    invalid = _guard(days, FITNESS_DAYS_RANGE, "days")
    if invalid:
        return invalid
    try:
        from arete.api.metrics import get_fitness_metrics

        payload = get_fitness_metrics(days=days).model_dump(mode="json")
        return _out(_disambiguate_window(payload, days))
    except Exception as exc:
        return _error(f"{type(exc).__name__}: {exc}")


@tool
def get_training_advice(sport_type: str = "mixed") -> str:
    """Rule-based training advice computed from the current workload and
    fitness: overall risk level, main concern, and prioritized recommendations
    with concrete actions. Deterministic, not LLM-generated — use it as a
    second opinion on your own reading of the numbers.

    Args:
        sport_type: cardio, strength or mixed (default mixed).
    """
    if sport_type not in SPORT_TYPES:
        return _error(f"sport_type must be one of {list(SPORT_TYPES)}")
    try:
        from arete.api.metrics import get_recommendations

        return _out(get_recommendations(sport_type=sport_type).model_dump(mode="json"))  # type: ignore[arg-type]
    except Exception as exc:
        return _error(f"{type(exc).__name__}: {exc}")


@tool
def get_personal_records(sport: str = "running") -> str:
    """All-time best efforts, from 400m to 50K (400m, 1/2 mile, 1K, 1 mile,
    2 mile, 5K, 10K, 15K, 10 mile, 20K, half-marathon, 30K, marathon, 50K),
    ordered by distance, with the date and session of each.

    Args:
        sport: Sport group, e.g. running or cycling (default running).
    """
    try:
        from arete.api.analytics import get_records

        return _out(get_records(sport=sport))
    except Exception as exc:
        return _error(f"{type(exc).__name__}: {exc}")


@tool
def list_recent_sessions(limit: int = 20, offset: int = 0) -> str:
    """Recent completed sessions, newest first: date, sport, name, duration,
    distance, average HR and pace, RPE and notes. Page backwards with offset
    to reach older sessions.

    Args:
        limit: How many sessions, 1 to 100 (default 20).
        offset: How many to skip, for paging back (default 0).
    """
    invalid = _guard(limit, (1, MAX_SESSIONS), "limit")
    if invalid:
        return invalid
    if offset < 0:
        return _error(f"offset must be 0 or more, got {offset}")
    try:
        from arete.api.analytics import list_sessions

        return _out(list_sessions(limit=limit, offset=offset))
    except Exception as exc:
        return _error(f"{type(exc).__name__}: {exc}")


ANALYTICS_TOOLS: list[BaseTool] = [
    get_workload,
    get_fitness,
    get_training_advice,
    get_personal_records,
    list_recent_sessions,
]

ANALYTICS_INSTRUCTIONS = """Toolkit `analytics` chargé — lecture ciblée des données d'entraînement:
- `get_workload(days?)`: ACWR, monotonie, strain sur une fenêtre (7-90 jours, défaut 28).
  La fenêtre demandée est `window_days`; `days_with_data` est le nombre de jours qui contenaient des données.
- `get_fitness(days?)`: CTL/ATL/TSB, forme, readiness, ramp rate (14-120 jours, défaut 42).
- `get_training_advice(sport_type?)`: recommandations déterministes (cardio|strength|mixed).
- `get_personal_records(sport?)`: records du 400m au 50K (400m, 1/2 mile, 1K, 1 mile, 2 mile, 5K, 10K, 15K, 10 mile, 20K, semi, 30K, marathon, 50K).
- `list_recent_sessions(limit?, offset?)`: séances récentes, `offset` pour remonter dans le temps.
  Le champ `name` est le titre lancé sur la montre, pas ce qui a été fait; `notes` et `rpe` viennent de l'athlète.
Préfère ces outils à `get_page_context('analytics')` dès que tu veux une fenêtre \
précise ou comparer deux périodes: appelle-les deux fois avec des `days` différents \
plutôt que de raisonner sur un seul bloc de 30 jours.
Chiffre toujours ce que tu avances: cite la valeur et la fenêtre sur laquelle tu la lis."""
