"""Analytics API: one overview per period, plus personal records.

``/analytics/overview`` answers four questions in one round-trip — how much did
I train, how hard, how efficiently, how well did I recover — so the page can
render every card without fanning out to a dozen endpoints.
"""

from __future__ import annotations

import json
import logging
from datetime import date

from fastapi import APIRouter, Query
from pydantic import BaseModel

from arete.dataio.db import connect, db_connection
from arete.dataio.queries import (
    RUNNING_SPORTS,
    SPORT_GROUPS,
    best_effort_rows,
    daily_metrics_range,
    drift_rows,
    earliest_session_date,
    efficiency_rows,
    pace_rows,
    sport_totals,
    training_loads,
    tss_history,
    volume_rows,
    zone_rows,
)
from arete.dataio.settings import athlete_zone_model
from arete.features import overview as ov
from arete.features.fitness import ctl_atl_series
from arete.features.periods import PeriodWindow, resolve_period
from arete.features.workload import (
    calculate_acute_load,
    calculate_acwr,
    calculate_chronic_load,
    get_acwr_zone,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])

#: Best-effort buckets, ascending by distance. These are the names the source
#: (Garmin/Strava) writes into ``best_efforts_json`` — matching is
#: case-insensitive because it is not consistent about it ("1K" and "5K" but
#: "1 mile", "50k"), and comparing spellings dropped every K distance from the
#: Records card.
EFFORT_NAMES = (
    "400m",
    "1/2 mile",
    "1K",
    "1 mile",
    "2 mile",
    "5K",
    "10K",
    "15K",
    "10 mile",
    "20K",
    "Half-Marathon",
    "30K",
    "Marathon",
    "50K",
)

#: Lookup from whatever spelling the data carries to the canonical name above.
_EFFORT_BY_KEY = {name.casefold(): name for name in EFFORT_NAMES}

# Two CTL time constants of history feed the EWMA before the first displayed day
CTL_WARMUP_DAYS = 84

ACWR_ZONE_FR = {
    "undertrained": "charge basse",
    "optimal": "zone optimale",
    "caution": "prudence",
    "danger": "zone à risque",
}

MIN_DRIFT_DURATION_SEC = 40 * 60


def _window(period: str) -> PeriodWindow:
    with db_connection() as con:
        earliest = earliest_session_date(con)
    return resolve_period(period, date.today(), earliest)


def _fetch_start(window: PeriodWindow) -> date:
    """First day to query: the previous window when there is one."""
    return window.prev_start or window.start


ACWR_HISTORY_DAYS = 28


def _acwr(target: date) -> tuple[float | None, str | None]:
    """Acute:chronic ratio on the last day of the window, with a French label."""
    loads = training_loads(days=ACWR_HISTORY_DAYS, end=target)
    value = calculate_acwr(
        calculate_acute_load(loads, target), calculate_chronic_load(loads, target)
    )
    if value is None:
        return None, None
    return round(value, 2), ACWR_ZONE_FR.get(get_acwr_zone(value).value)


@router.get("/overview")
def get_overview(period: str = Query("30d")):
    """Every analytics card for one period, with the previous one as reference."""
    window = _window(period)
    start = _fetch_start(window)

    with db_connection() as con:
        sessions = volume_rows(con, start, window.end)
        zones = zone_rows(con, start, window.end)
        sports_cur = sport_totals(con, window.start, window.end)
        sports_prev = (
            sport_totals(con, window.prev_start, window.prev_end)
            if window.prev_start and window.prev_end
            else []
        )
        paces = pace_rows(con, start, window.end)
        drifts = drift_rows(con, start, window.end, MIN_DRIFT_DURATION_SEC)
        efficiency = efficiency_rows(con, start, window.end)
        health = daily_metrics_range(con, start, window.end)

    tss_days = (window.end - start).days + 1
    pmc_series = ctl_atl_series(tss_history(days=tss_days + CTL_WARMUP_DAYS))
    acwr, acwr_zone = _acwr(window.end)

    recovery = ov.build_recovery_cards(health, window)
    return {
        "hr_zone_model": athlete_zone_model().as_dict(),
        "period": window.period,
        "bucket": window.bucket,
        "start": window.start.isoformat(),
        "end": window.end.isoformat(),
        "prev_start": window.prev_start.isoformat() if window.prev_start else None,
        "prev_end": window.prev_end.isoformat() if window.prev_end else None,
        "cards": {
            "volume": ov.build_volume_card(sessions, window, RUNNING_SPORTS),
            "pmc": ov.build_pmc_card(pmc_series, window, acwr, acwr_zone),
            "zones": ov.build_zones_card(zones, window),
            "sports": ov.build_sports_card(sports_cur, sports_prev),
            "decoupling": ov.build_decoupling_card(drifts, efficiency, window),
            "pace": ov.build_pace_card(paces, window),
            **recovery,
        },
    }


@router.get("/records")
def get_records(sport: str = Query("running")):
    """All-time best efforts for the usual distances."""
    sports = SPORT_GROUPS.get(sport, RUNNING_SPORTS)
    with db_connection() as con:
        rows = best_effort_rows(con, sports)

    bests: dict[str, dict] = {}
    for efforts_json, row_date, activity_name in rows:
        efforts = (
            json.loads(efforts_json) if isinstance(efforts_json, str) else efforts_json
        )
        if not isinstance(efforts, list):
            continue
        for effort in efforts:
            name = _EFFORT_BY_KEY.get(str(effort.get("name", "")).casefold())
            elapsed = effort.get("elapsed_time", 0)
            if name is None or elapsed <= 0:
                continue
            if name not in bests or elapsed < bests[name]["time_sec"]:
                bests[name] = {
                    "name": name,
                    "time_sec": elapsed,
                    "time_display": ov.format_hms(elapsed),
                    "date": str(row_date),
                    "activity_name": activity_name or "",
                }

    return {"records": [bests[n] for n in EFFORT_NAMES if n in bests]}


# ---------- Session CRUD ----------


class SessionUpdate(BaseModel):
    rpe: int | None = None
    notes: str | None = None


@router.patch("/sessions/{session_id}")
def update_session(session_id: int, body: SessionUpdate):
    """Update RPE and/or notes for an actual session."""
    con = connect(read_only=False)
    try:
        updates = []
        values: list = []
        if body.rpe is not None:
            updates.append("rpe = ?")
            values.append(body.rpe)
        if body.notes is not None:
            updates.append("notes = ?")
            values.append(body.notes)
        if not updates:
            return {"success": True}

        values.append(session_id)
        con.execute(
            f"UPDATE app.actual_sessions SET {', '.join(updates)} WHERE id = ?",
            values,
        )
        return {"success": True}
    finally:
        con.close()


@router.get("/sessions")
def list_sessions(limit: int = 20, offset: int = 0):
    """List recent actual sessions (for Log page)."""
    with db_connection() as con:
        rows = con.execute(
            """
            SELECT id, date, sport, name, duration_sec, distance_m,
                   avg_hr, avg_pace_sec_km, rpe, notes, source, calories
            FROM app.actual_sessions
            WHERE user_id = 1
            ORDER BY date DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            [limit, offset],
        ).fetchall()

    sessions = []
    for r in rows:
        sessions.append(
            {
                "id": r[0],
                "date": str(r[1]),
                "sport": r[2],
                "name": r[3],
                "duration_sec": r[4],
                "distance_m": r[5],
                "avg_hr": r[6],
                "avg_pace_sec_km": r[7],
                "pace_display": ov.format_pace(r[7]),
                "rpe": r[8],
                "notes": r[9],
                "source": r[10],
                "calories": r[11],
            }
        )
    return {"sessions": sessions}
