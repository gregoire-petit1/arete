"""The periodised plan: invariants a coach would check by hand."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from arete.features.plan_generator import (
    LONG_RUN_CAP,
    PEAK_MINUTES,
    PlanError,
    PlanInputs,
    generate_plan,
)
from arete.features.running import training_paces

START = date(2026, 10, 12)  # a Monday
MARATHON = START + timedelta(weeks=15, days=6)  # a Sunday, 16 weeks out


def _plan(**kw):
    values = {
        "start": START,
        "race_date": MARATHON,
        "distance_km": 42.195,
        "weekly_minutes_now": 240,
        "sessions_per_week": 4,
        "rest_days": frozenset({0}),
        "paces": training_paces(50.0),
        "race_name": "Marathon de test",
    }
    values.update(kw)
    return generate_plan(PlanInputs(**values))


def test_phases_run_base_build_specific_taper_race():
    weeks = _plan()
    phases = [w.phase for w in weeks]
    assert len(weeks) == 16
    assert phases[-1] == "race" and phases[-2] == "taper"
    assert phases[-6:-2] == ["specific"] * 4
    assert phases.index("build") > phases.index("base")


def test_sessions_respect_the_week_the_rest_days_and_the_race():
    weeks = _plan()
    sessions = [s for w in weeks for s in w.sessions]
    assert all(s.date.weekday() != 0 for s in sessions)  # Monday is rest
    assert all(START <= s.date <= MARATHON for s in sessions)
    assert all(len(w.sessions) <= 4 for w in weeks)
    race = sessions[-1]
    assert (race.date, race.session_type, race.distance_km) == (
        MARATHON,
        "race",
        42.195,
    )
    assert len({s.date for s in sessions}) == len(sessions)  # one session a day


def test_volume_grows_gently_with_a_lighter_fourth_week_and_a_taper():
    weeks = _plan()
    loading = [w for w in weeks if w.phase in ("base", "build", "specific")]
    for previous, week in zip(loading, loading[1:], strict=False):
        if not week.recovery and not previous.recovery:
            assert week.minutes <= previous.minutes * 1.08 + 1
    assert [w.recovery for w in loading][3] is True
    assert max(w.minutes for w in weeks) <= PEAK_MINUTES["marathon"]
    assert weeks[-2].minutes < max(w.minutes for w in loading)
    assert weeks[-1].minutes < weeks[-2].minutes


def test_long_runs_are_capped_and_quality_avoids_the_day_before():
    weeks = _plan()
    for week in weeks:
        longs = [s for s in week.sessions if s.session_type == "long_run"]
        for long in longs:
            assert long.duration_min <= LONG_RUN_CAP["marathon"]
            day_before = long.date - timedelta(days=1)
            assert not any(
                s.date == day_before and s.session_type in ("tempo", "intervals")
                for s in week.sessions
            )


def test_descriptions_carry_the_paces():
    sessions = [s for w in _plan() for s in w.sessions]
    tempo = next(s for s in sessions if s.description.startswith("Seuil"))
    assert "/km" in tempo.description
    no_paces = [s for w in _plan(paces=None) for s in w.sessions]
    assert all("/km" not in s.description for s in no_paces)


def test_a_10k_next_week_is_just_race_week():
    race = START + timedelta(days=5)
    weeks = _plan(race_date=race, distance_km=10, sessions_per_week=3)
    assert [w.phase for w in weeks] == ["race"]
    assert weeks[0].sessions[-1].session_type == "race"


@pytest.mark.parametrize(
    ("overrides", "message"),
    [
        ({"race_date": START - timedelta(days=1)}, "passée"),
        ({"race_date": START + timedelta(weeks=30)}, "24 semaines"),
        ({"rest_days": frozenset(range(6))}, "deux jours"),
    ],
)
def test_impossible_plans_say_why(overrides, message):
    with pytest.raises(PlanError, match=message):
        _plan(**overrides)


def test_a_lighter_week_keeps_a_light_quality_session():
    weeks = _plan()
    recovery = next(w for w in weeks if w.recovery)
    quality = [s for s in recovery.sessions if s.session_type in ("tempo", "intervals")]
    assert len(quality) == 1 and "2×8'" in quality[0].description


def test_easy_paces_read_fastest_first():
    footing = next(
        s for w in _plan() for s in w.sessions if s.description.startswith("Footing")
    )
    fast, slow = (
        footing.description.split("(")[1].rstrip(")").replace("/km", "").split(" à ")
    )
    assert fast < slow
