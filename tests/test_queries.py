"""Tests for shared actual_sessions queries (temp DuckDB from conftest)."""

from __future__ import annotations

from datetime import date

from arete.dataio.db import connect
from arete.dataio.queries import (
    RUNNING_SPORTS,
    SPORT_GROUPS,
    daily_loads,
    daily_tss,
    sql_in,
    weekly_tss,
)


def _insert(con, day: date, duration_sec: int, rpe: int | None, sport: str = "run"):
    con.execute(
        """
        INSERT INTO app.actual_sessions (user_id, date, sport, session_type, duration_sec, rpe, source)
        VALUES (1, ?, ?, 'x', ?, ?, 'test')
        """,
        [day, sport, duration_sec, rpe],
    )


class TestSportGroups:
    def test_both_spellings_present(self):
        assert {"run", "running", "trail_run"} <= set(RUNNING_SPORTS)
        assert {"ride", "cycling"} <= set(SPORT_GROUPS["cycling"])

    def test_sql_in(self):
        assert sql_in(("a", "b")) == "'a', 'b'"


class TestSeries:
    def test_daily_series_are_gap_filled_and_consistent(self):
        con = connect()
        try:
            con.execute("DELETE FROM app.actual_sessions WHERE source = 'test'")
            _insert(con, date(2026, 1, 1), 3600, 6)  # 1 h @ RPE 6 = 60 TSS
            _insert(con, date(2026, 1, 3), 1800, None)  # no RPE -> default chain

            tss = daily_tss(con, date(2026, 1, 1), date(2026, 1, 4))
            assert [t.date.day for t in tss] == [1, 2, 3, 4]
            assert round(tss[0].tss) == 60
            assert tss[1].tss == 0.0 and tss[3].tss == 0.0
            assert tss[2].tss > 0

            loads = daily_loads(con, date(2026, 1, 1), date(2026, 1, 4))
            assert loads[0].duration_min == 60 and loads[0].rpe == 6
            assert loads[1].duration_min == 0

            assert round(weekly_tss(con, date(2026, 1, 1), date(2026, 1, 4))) == round(
                sum(t.tss for t in tss)
            )
        finally:
            con.execute("DELETE FROM app.actual_sessions WHERE source = 'test'")
            con.close()
