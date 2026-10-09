"""Tests for shared actual_sessions queries (temp DuckDB from conftest)."""

from __future__ import annotations

from datetime import date

from arete.dataio.db import connect
from arete.dataio.queries import (
    RUNNING_SPORTS,
    SPORT_GROUPS,
    daily_loads,
    daily_tss,
    daily_tss_by_date,
    sql_in,
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
        finally:
            con.execute("DELETE FROM app.actual_sessions WHERE source = 'test'")
            con.close()


def test_daily_tss_by_date_matches_the_gap_filled_series():
    con = connect()
    try:
        con.execute("DELETE FROM app.actual_sessions WHERE source = 'test'")
        _insert(con, date(2026, 1, 1), 3600, 6)
        _insert(con, date(2026, 1, 1), 1800, 8)
        _insert(con, date(2026, 1, 3), 1800, None)

        by_date = daily_tss_by_date(con)
        series = daily_tss(con, date(2026, 1, 1), date(2026, 1, 4))
        assert {t.date: t.tss for t in series if t.tss} == {
            d: tss
            for d, tss in by_date.items()
            if date(2026, 1, 1) <= d <= date(2026, 1, 4)
        }
    finally:
        con.execute("DELETE FROM app.actual_sessions WHERE source = 'test'")
        con.close()


def _set_thresholds(con, lthr, max_hr):
    con.execute(
        "INSERT INTO app.user_settings (user_id, lthr, max_hr) VALUES (1, ?, ?) "
        "ON CONFLICT (user_id) DO UPDATE SET lthr = EXCLUDED.lthr, max_hr = EXCLUDED.max_hr",
        [lthr, max_hr],
    )


def test_hr_tss_is_read_against_the_threshold():
    con = connect()
    saved = con.execute(
        "SELECT lthr, max_hr FROM app.user_settings WHERE user_id = 1"
    ).fetchone()
    day = date(2025, 2, 3)
    try:
        con.execute("DELETE FROM app.actual_sessions WHERE source = 'test'")
        con.execute(
            "INSERT INTO app.actual_sessions (user_id, date, sport, duration_sec, avg_hr, source)"
            " VALUES (1, ?, 'running', 3600, 170, 'test')",
            [day],
        )
        _set_thresholds(con, 170, None)  # 1 h at threshold = 100
        assert round(daily_tss(con, day, day)[0].tss) == 100
        _set_thresholds(con, None, 200)  # threshold derived: 0.9 x 200 = 180
        assert round(daily_tss(con, day, day)[0].tss) == round(100 * (170 / 180) ** 2)
    finally:
        con.execute("DELETE FROM app.actual_sessions WHERE source = 'test'")
        _set_thresholds(con, *(saved or (None, None)))
        con.close()


def test_strength_sessions_count_once():
    con = connect()
    day = date(2025, 2, 10)
    try:
        con.execute("DELETE FROM app.actual_sessions WHERE source = 'test'")
        con.execute("DELETE FROM app.strength_sessions WHERE name LIKE 'test-%'")
        con.execute(
            "INSERT INTO app.strength_sessions (user_id, date, name, duration_min, overall_rpe)"
            " VALUES (1, ?, 'test-free', 60, 6)",
            [day],
        )
        # Linked to a Garmin activity: that activity carries the load already.
        con.execute(
            "INSERT INTO app.strength_sessions"
            " (user_id, date, name, duration_min, overall_rpe, actual_session_id)"
            " VALUES (1, ?, 'test-linked', 60, 9, 999999)",
            [day],
        )
        # No duration: no load, and no say in the day's mean RPE.
        con.execute(
            "INSERT INTO app.strength_sessions (user_id, date, name, overall_rpe)"
            " VALUES (1, ?, 'test-undated', 10)",
            [day],
        )
        assert round(daily_tss(con, day, day)[0].tss) == 60  # 1 h @ RPE 6
        assert daily_tss_by_date(con)[day] == daily_tss(con, day, day)[0].tss
        load = daily_loads(con, day, day)[0]
        assert load.duration_min == 60 and load.rpe == 6
    finally:
        con.execute("DELETE FROM app.strength_sessions WHERE name LIKE 'test-%'")
        con.close()


def test_strava_sessions_never_reach_the_model():
    from arete.services.analytics import list_sessions

    con = connect()
    try:
        con.execute(
            "INSERT INTO app.actual_sessions (user_id, date, sport, duration_sec, name, source)"
            " VALUES (1, DATE '2099-12-31', 'running', 1800, 'strava-only', 'strava'),"
            " (1, DATE '2099-12-31', 'running', 1800, 'from-garmin', 'garmin_connect')"
        )
        page = [s["name"] for s in list_sessions(limit=5)["sessions"]]
        coach = [s["name"] for s in list_sessions(limit=5, for_model=True)["sessions"]]
        assert "strava-only" in page and "from-garmin" in page
        assert "strava-only" not in coach and "from-garmin" in coach
    finally:
        con.execute("DELETE FROM app.actual_sessions WHERE date = DATE '2099-12-31'")
        con.close()
