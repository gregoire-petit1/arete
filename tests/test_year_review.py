"""Year in review: totals, highlights, records against earlier years, streaks."""

from __future__ import annotations

import json
from datetime import date

import pytest

from arete.api.year_review import router
from arete.dataio.db import connect
from arete.services import year_review as yr

# Years no other test writes to: the shared test database keeps their rows.
YEAR = 2003
TODAY = date(2026, 10, 10)


def _efforts(**times: int) -> str:
    return json.dumps([{"name": n, "elapsed_time": t} for n, t in times.items()])


@pytest.fixture
def history():
    con = connect()
    con.execute(
        """
        INSERT INTO app.actual_sessions
            (user_id, date, sport, name, duration_sec, distance_m, ascent_m,
             source, rpe, best_efforts_json)
        VALUES
            (1, '2002-06-01', 'running', 'Ancien 5K', 1800, 6000, 20,
             'garmin_connect', 8, ?),
            (1, '2003-01-04', 'running', 'Footing', 3600, 10000, 100,
             'garmin_connect', 5, ?),
            (1, '2003-01-05', 'running', 'Sortie longue', 7200, 21100, 250,
             'strava', 6, ?),
            (1, '2003-03-10', 'cycling', 'Col', 12000, 60000, 1500,
             'garmin_connect', 8, NULL)
        """,
        [
            _efforts(**{"5K": 1500, "10K": 3000}),
            _efforts(**{"5k": 1450, "10K": 3100}),
            _efforts(**{"Half-Marathon": 6000}),
        ],
    )
    linked = con.execute(
        "SELECT id FROM app.actual_sessions WHERE date = '2003-03-10'"
    ).fetchone()[0]
    exercise = con.execute(
        "INSERT INTO app.exercises (name, category, primary_muscle) "
        "VALUES ('test-yr squat', 'squat', 'quads') RETURNING id"
    ).fetchone()[0]
    strength = []
    for day, link in (("2003-01-06", None), ("2003-03-10", linked)):
        strength.append(
            con.execute(
                "INSERT INTO app.strength_sessions "
                "(user_id, date, name, duration_min, overall_rpe, actual_session_id) "
                "VALUES (1, ?, 'test-yr force', 45, 7, ?) RETURNING id",
                [day, link],
            ).fetchone()[0]
        )
    for session_id in strength:
        se = con.execute(
            "INSERT INTO app.session_exercises (session_id, exercise_id) "
            "VALUES (?, ?) RETURNING id",
            [session_id, exercise],
        ).fetchone()[0]
        con.execute(
            "INSERT INTO app.exercise_sets "
            "(session_exercise_id, set_number, reps, weight_kg, is_warmup) "
            "VALUES (?, 1, 10, 40, TRUE), (?, 2, 5, 100, FALSE), (?, 3, 5, 100, FALSE)",
            [se, se, se],
        )
    con.close()
    yield
    con = connect()
    con.execute(
        "DELETE FROM app.exercise_sets WHERE session_exercise_id IN "
        "(SELECT id FROM app.session_exercises WHERE exercise_id = ?)",
        [exercise],
    )
    con.execute("DELETE FROM app.session_exercises WHERE exercise_id = ?", [exercise])
    con.execute("DELETE FROM app.strength_sessions WHERE name = 'test-yr force'")
    con.execute("DELETE FROM app.exercises WHERE id = ?", [exercise])
    con.execute(
        "DELETE FROM app.actual_sessions WHERE date BETWEEN '2002-01-01' AND '2003-12-31'"
    )
    con.close()


def test_totals_count_a_linked_strength_session_once(history):
    review = yr.year_review(YEAR, today=TODAY)
    assert review["complete"] is True
    assert review["end"] == "2003-12-31"
    totals = review["totals"]
    # Three activities and the strength session logged without one.
    assert totals["sessions"] == 4
    assert totals["duration_sec"] == 3600 + 7200 + 12000 + 45 * 60
    assert totals["distance_m"] == 91100
    assert totals["ascent_m"] == 1850
    sports = {s["sport"]: s for s in review["sports"]}
    assert sports["running"]["sessions"] == 2
    assert review["sports"][0]["sport"] == "cycling"  # most time first
    assert review["months"][0]["sessions"] == 3
    assert review["months"][2]["distance_m"] == 60000
    assert len(review["months"]) == 12
    assert YEAR in review["years"] and TODAY.year in review["years"]


def test_highlights_name_the_standout_sessions(history):
    highlights = yr.year_review(YEAR, today=TODAY)["highlights"]
    assert highlights["longest_distance"]["name"] == "Col"
    assert highlights["biggest_climb"]["ascent_m"] == 1500
    assert highlights["hardest"]["name"] == "Col"
    assert highlights["longest_duration"]["duration_sec"] == 12000


def test_best_efforts_are_records_only_against_earlier_years(history):
    review = yr.year_review(YEAR, today=TODAY)
    efforts = {e["name"]: e for e in review["best_efforts"]}
    assert efforts["5K"]["time_sec"] == 1450
    assert efforts["5K"]["previous_best_sec"] == 1500
    assert efforts["5K"]["is_pr"] is True
    assert efforts["10K"]["is_pr"] is False
    assert efforts["Half-Marathon"]["previous_best_sec"] is None
    assert efforts["Half-Marathon"]["is_pr"] is True
    assert review["pr_count"] == 2
    assert efforts["Half-Marathon"]["activity_name"] == "Sortie longue"


def test_strength_volume_counts_working_sets_of_every_session(history):
    strength = yr.year_review(YEAR, today=TODAY)["strength"]
    assert strength["sessions"] == 2
    assert strength["working_sets"] == 4
    assert strength["volume_kg"] == 2000.0
    assert strength["top_exercises"][0]["name"] == "test-yr squat"
    assert strength["top_exercises"][0]["max_weight_kg"] == 100
    months = yr.year_review(YEAR, today=TODAY)["months"]
    assert months[0]["strength_volume_kg"] == 1000.0


def test_fitness_curve_is_weekly_with_its_peak(history):
    fitness = yr.year_review(YEAR, today=TODAY)["fitness"]
    assert fitness["series"][-1]["date"] == "2003-12-31"
    assert all(
        date.fromisoformat(p["date"]).weekday() == 6 for p in fitness["series"][:-1]
    )
    assert fitness["peak"]["ctl"] >= fitness["end_ctl"]
    assert fitness["peak"]["date"].startswith("2003-03")


def test_an_empty_year_answers_zeros():
    review = yr.year_review(2001, today=TODAY)
    assert review["totals"]["sessions"] == 0
    assert review["highlights"]["hardest"] is None
    assert review["best_efforts"] == []
    assert review["fitness"]["series"] == []
    assert review["consistency"]["longest_day_streak"] == 0


def test_the_current_year_stops_today_and_the_future_is_refused():
    review = yr.year_review(TODAY.year, today=TODAY)
    assert review["end"] == TODAY.isoformat()
    assert review["complete"] is False
    with pytest.raises(ValueError):
        yr.year_review(TODAY.year + 1, today=TODAY)
    with pytest.raises(ValueError):
        yr.year_review(1999, today=TODAY)


def test_consistency_counts_weeks_the_period_touches():
    active = {date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 10)}
    out = yr.consistency(active, date(2024, 1, 1), date(2024, 1, 31))
    assert out["active_days"] == 4
    assert out["days"] == 31
    assert out["longest_day_streak"] == 3
    assert out["weeks"] == 5  # Monday 1, 8, 15, 22 and 29 January
    assert out["active_weeks"] == 2
    assert out["longest_week_streak"] == 2


def test_api_validates_the_year(router_client):
    client = router_client(router)
    assert client.get("/year-review", params={"year": 1999}).status_code == 422
    body = client.get("/year-review", params={"year": 2001}).json()
    assert body["year"] == 2001
    assert client.get("/year-review").json()["year"] == date.today().year
