"""One fitness series and one readiness, whatever the surface reading them."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from arete.services import metrics

TODAY = date(2026, 10, 9)


def _history(days: int, tss: float = 60.0) -> dict[date, float]:
    # Rest every third day: a series with gaps, like real training.
    return {TODAY - timedelta(days=i): tss for i in range(days, 0, -1) if i % 3 != 0}


def test_fitness_series_and_model_agree():
    by_date = _history(300)
    model = metrics.fitness_model(by_date, TODAY)
    assert model is not None
    _day, ctl, atl = metrics.fitness_series(by_date, TODAY)[-1]
    assert model.ctl == pytest.approx(round(ctl, 1))
    assert model.atl == pytest.approx(round(atl, 1))


def test_the_model_reads_the_whole_history():
    # A long block, then six weeks off: an 84-day window would forget the block.
    by_date = {TODAY - timedelta(days=i): 80.0 for i in range(250, 120, -1)}
    model = metrics.fitness_model(by_date, TODAY)
    assert model is not None
    _day, ctl, _atl = metrics.fitness_series(by_date, TODAY)[-1]
    assert model.ctl == pytest.approx(round(ctl, 1))
    assert model.ctl > 1.0


def test_no_load_no_model():
    assert metrics.fitness_model({}, TODAY) is None
    assert metrics.fitness_model({TODAY: 0.0}, TODAY) is None
    assert metrics.fitness_series({}, TODAY) == []


def _garmin_rows(days: list[date]) -> list[tuple]:
    """``fetch_window`` rows: a 14-day baseline, then the measured nights."""
    rows = [
        (TODAY - timedelta(days=i), 60, 8 * 3600, 80, 25, 50) for i in range(16, 2, -1)
    ]
    rows += [(d, 65, 8 * 3600, 90, 20, 48) for d in days]
    return rows


def test_readiness_prefers_garmin_today_then_yesterday_then_model():
    model = metrics.fitness_model(_history(120), TODAY)
    assert model is not None

    today = metrics.current_readiness(TODAY, _garmin_rows([TODAY]), model)
    assert today is not None
    assert (today.source, today.measured_on) == ("garmin", TODAY)

    yesterday = TODAY - timedelta(days=1)
    previous = metrics.current_readiness(TODAY, _garmin_rows([yesterday]), model)
    assert previous is not None
    assert (previous.source, previous.measured_on) == ("garmin", yesterday)

    estimated = metrics.current_readiness(TODAY, _garmin_rows([]), model)
    assert estimated is not None
    assert estimated.source == "model" and estimated.measured_on is None
    assert estimated.score == pytest.approx(round(model.readiness_score, 1))

    assert metrics.current_readiness(TODAY, [], None) is None


def test_the_recovery_bar_says_where_the_number_comes_from():
    bar = metrics._recovery_bar(
        metrics.Readiness(score=72.0, source="garmin", measured_on=TODAY), TODAY
    )
    assert (bar.current, bar.source) == (72.0, "garmin")
    previous = metrics._recovery_bar(
        metrics.Readiness(
            score=70.0, source="garmin", measured_on=TODAY - timedelta(days=1)
        ),
        TODAY,
    )
    assert previous.source == "garmin_previous" and "08/10" in (previous.detail or "")
    assert metrics._recovery_bar(None, TODAY).source == "model"
