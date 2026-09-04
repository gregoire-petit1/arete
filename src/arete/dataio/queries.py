"""Shared SQL over ``app.actual_sessions``: sport groups and training-load series.

One definition of "what is a run", one TSS formula, one gap-filled daily
series. Used by metrics, analytics, tips and the Banister fit.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from datetime import date, timedelta

import duckdb

from arete.dataio.db import db_connection
from arete.features.fitness import DailyTSS
from arete.features.workload import DailyLoad

# Garmin sync writes "running"/"cycling"/..., Strava writes "run"/"ride"/...:
# both spellings coexist in the database, so every filter must accept both.
RUNNING_SPORTS: tuple[str, ...] = (
    "run",
    "running",
    "trail_run",
    "trail_running",
    "treadmill_running",
    "virtualrun",
    "virtual_run",
)
WALKING_SPORTS: tuple[str, ...] = ("walk", "walking", "hike", "hiking")
FOOT_SPORTS: tuple[str, ...] = RUNNING_SPORTS + WALKING_SPORTS
CYCLING_SPORTS: tuple[str, ...] = (
    "ride",
    "cycling",
    "virtual_ride",
    "indoor_cycling",
    "mountain_biking",
)
SPORT_GROUPS: dict[str, tuple[str, ...]] = {
    "running": RUNNING_SPORTS,
    "cycling": CYCLING_SPORTS,
}


def sql_in(values: Iterable[str]) -> str:
    """Render a tuple of literals for an ``IN (...)`` clause."""
    return ", ".join(f"'{v}'" for v in values)


# TSS estimate per session, best signal first:
# RPE -> Strava suffer score -> HR-based -> flat default (RPE 5 equivalent).
# (duration_min * intensity^2) / 0.36: 1 h at RPE 6 = 60 TSS, 1 h at RPE ~7.7 = 100 TSS.
TSS_EXPR = """
    CASE
      WHEN rpe IS NOT NULL THEN
        (COALESCE(duration_sec, 0) / 60.0) * POWER(rpe / 10.0, 2) / 0.36
      WHEN suffer_score IS NOT NULL THEN
        suffer_score * 0.8
      WHEN avg_hr IS NOT NULL THEN
        (COALESCE(duration_sec, 0) / 60.0) * POWER(LEAST(avg_hr, 200) / 180.0, 2) / 0.36
      ELSE
        (COALESCE(duration_sec, 0) / 60.0) * 0.25 / 0.36
    END
"""


def _days(start: date, end: date) -> Sequence[date]:
    return [start + timedelta(days=i) for i in range((end - start).days + 1)]


def daily_tss(
    con: duckdb.DuckDBPyConnection, start: date, end: date, user_id: int = 1
) -> list[DailyTSS]:
    """Daily TSS between two dates (inclusive), zeros for days without sessions."""
    rows = con.execute(
        f"""
        SELECT date, SUM({TSS_EXPR}) AS daily_tss
        FROM app.actual_sessions
        WHERE date >= ? AND date <= ? AND user_id = ?
        GROUP BY date
        """,
        [start, end, user_id],
    ).fetchall()
    by_date = {row[0]: float(row[1]) for row in rows}
    return [DailyTSS(date=d, tss=by_date.get(d, 0.0)) for d in _days(start, end)]


def daily_loads(
    con: duckdb.DuckDBPyConnection, start: date, end: date, user_id: int = 1
) -> list[DailyLoad]:
    """Daily duration/RPE loads between two dates, zeros for days without sessions."""
    rows = con.execute(
        """
        SELECT date,
               SUM(COALESCE(duration_sec, 0)) / 60.0 AS total_duration,
               AVG(COALESCE(rpe, 5)) AS avg_rpe
        FROM app.actual_sessions
        WHERE date >= ? AND date <= ? AND user_id = ?
        GROUP BY date
        """,
        [start, end, user_id],
    ).fetchall()
    by_date = {row[0]: (int(row[1]), float(row[2])) for row in rows}
    return [
        DailyLoad(date=d, duration_min=by_date[d][0], rpe=by_date[d][1])
        if d in by_date
        else DailyLoad(date=d, duration_min=0, rpe=0)
        for d in _days(start, end)
    ]


def weekly_tss(
    con: duckdb.DuckDBPyConnection, start: date, end: date, user_id: int = 1
) -> float:
    """Total TSS between two dates (inclusive)."""
    row = con.execute(
        f"""
        SELECT COALESCE(SUM({TSS_EXPR}), 0)
        FROM app.actual_sessions
        WHERE date >= ? AND date <= ? AND user_id = ?
        """,
        [start, end, user_id],
    ).fetchone()
    return float(row[0]) if row else 0.0


# Convenience wrappers for callers without a connection at hand.
def tss_history(days: int, end: date | None = None) -> list[DailyTSS]:
    end = end or date.today()
    with db_connection() as con:
        return daily_tss(con, end - timedelta(days=days), end)


def training_loads(days: int, end: date | None = None) -> list[DailyLoad]:
    end = end or date.today()
    with db_connection() as con:
        return daily_loads(con, end - timedelta(days=days), end)
