"""VDOT against Daniels' published tables (Daniels' Running Formula, 3rd ed.)."""

from __future__ import annotations

import pytest

from arete.features.running import (
    race_equivalents,
    race_time_sec,
    training_paces,
    vdot_from_race,
    vdot_from_threshold_pace,
)


@pytest.mark.parametrize(
    ("distance", "time", "vdot"),
    [
        (5000, 19 * 60 + 57, 50),  # 5K 19:57 -> VDOT 50
        (10000, 41 * 60 + 21, 50),  # 10K 41:21 -> 50
        (42195, 3 * 3600 + 10 * 60 + 49, 50),  # marathon 3:10:49 -> 50
        (10000, 35 * 60 + 22, 60),  # 10K 35:22 -> 60
    ],
)
def test_vdot_matches_the_tables(distance, time, vdot):
    assert vdot_from_race(distance, time) == pytest.approx(vdot, abs=0.5)


def test_race_time_inverts_the_vdot():
    for distance in (5000, 10000, 21097, 42195):
        time = race_time_sec(50.0, distance)
        assert vdot_from_race(distance, time) == pytest.approx(50.0, abs=0.01)
    assert race_equivalents(50.0)["half"] == pytest.approx(91 * 60 + 35, abs=60)


def test_training_paces_at_vdot_50():
    paces = training_paces(50.0)
    assert paces.threshold == pytest.approx(255, abs=6)  # T 4:15/km
    assert paces.interval == pytest.approx(235, abs=6)  # I 3:55/km
    assert paces.easy[0] > paces.easy[1] > paces.marathon > paces.threshold
    assert paces.threshold > paces.interval > paces.repetition


def test_threshold_pace_gives_back_its_vdot():
    assert vdot_from_threshold_pace(training_paces(50.0).threshold) == pytest.approx(
        50.0, abs=0.3
    )


def test_bad_inputs():
    with pytest.raises(ValueError):
        vdot_from_race(0, 100)


def test_paces_endpoint_reads_garmin_then_the_threshold(router_client):
    from unittest.mock import patch

    from arete.api.metrics import router

    client = router_client(router)
    with patch(
        "arete.services.metrics.current_vdot", return_value=(50.0, "garmin_prediction")
    ):
        body = client.get("/metrics/paces").json()
    assert body["vdot"] == 50.0 and body["source"] == "garmin_prediction"
    assert body["paces"]["threshold"] < body["paces"]["easy"][1]
    assert set(body["equivalents"]) == {"5k", "10k", "half", "marathon"}
    with patch("arete.services.metrics.current_vdot", return_value=None):
        body = client.get("/metrics/paces").json()
    assert body["paces"] is None and "seuil" in body["reason"]


def test_vdot_source_order():
    from datetime import date
    from unittest.mock import patch

    from arete.dataio.db import connect
    from arete.services.metrics import current_vdot

    con = connect()
    try:
        with patch(
            "arete.services.metrics.get_user_settings",
            return_value={"threshold_pace_sec_km": 255},
        ):
            vdot, source = current_vdot(con) or (None, None)
            assert source == "threshold_pace" and vdot == pytest.approx(50, abs=0.5)
            con.execute(
                "INSERT INTO app.daily_metrics (user_id, date, race_10k_sec) VALUES (1, ?, ?)",
                [date(2099, 1, 1), 35 * 60 + 22],
            )
            vdot, source = current_vdot(con) or (None, None)
            assert source == "garmin_prediction" and vdot == pytest.approx(60, abs=0.5)
    finally:
        con.execute("DELETE FROM app.daily_metrics WHERE date = DATE '2099-01-01'")
        con.close()
