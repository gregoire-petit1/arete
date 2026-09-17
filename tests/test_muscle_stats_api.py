"""GET /strength/stats/muscles: what the heat map reads."""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import patch

import pytest

from arete.api.strength import router


@pytest.fixture
def client(router_client):
    return router_client(router)


TODAY = date.today()


def activity(volumes, sets=None, last=None):
    return (volumes, sets or {}, last or {})


class TestMuscleStats:
    @patch("arete.api.strength._cardio_muscle_activity", return_value=({}, {}))
    @patch("arete.api.strength._repo")
    def test_window_and_every_region(self, repo, _cardio, client):
        repo.get_muscle_activity.return_value = activity({"lats": 1000.0})
        data = client.get("/strength/stats/muscles?days=7").json()
        assert data["days"] == 7
        assert data["end"] == TODAY.isoformat()
        assert data["start"] == (TODAY - timedelta(days=6)).isoformat()
        assert len(data["muscles"]) == 20

    @patch("arete.api.strength._cardio_muscle_activity", return_value=({}, {}))
    @patch("arete.api.strength._repo")
    def test_coarse_muscle_is_spread(self, repo, _cardio, client):
        repo.get_muscle_activity.return_value = activity(
            {"back": 1000.0}, {"back": 10.0}, {"back": TODAY}
        )
        muscles = {
            m["muscle"]: m
            for m in client.get("/strength/stats/muscles").json()["muscles"]
        }
        assert muscles["lats"]["volume"] == 500.0
        assert muscles["traps"]["volume"] == 250.0
        assert muscles["lats"]["level"] == 4
        assert muscles["traps"]["level"] == 2
        assert muscles["chest"]["level"] == 0

    @patch("arete.api.strength._cardio_muscle_activity")
    @patch("arete.api.strength._repo")
    def test_cardio_adds_volume_and_freshness(self, repo, cardio, client):
        repo.get_muscle_activity.return_value = activity({"lats": 100.0})
        cardio.return_value = ({"quads": 900.0}, {"quads": TODAY})
        muscles = {
            m["muscle"]: m
            for m in client.get("/strength/stats/muscles").json()["muscles"]
        }
        assert muscles["quads"]["volume"] == 900.0
        assert muscles["quads"]["last_trained"] == TODAY.isoformat()
        assert muscles["quads"]["level"] == 4

    @patch("arete.api.strength._cardio_muscle_activity", return_value=({}, {}))
    @patch("arete.api.strength._repo")
    def test_cardio_can_be_excluded(self, repo, cardio, client):
        repo.get_muscle_activity.return_value = activity({"lats": 100.0})
        client.get("/strength/stats/muscles?include_cardio=false")
        cardio.assert_not_called()

    @patch("arete.api.strength._cardio_muscle_activity", return_value=({}, {}))
    @patch("arete.api.strength._repo")
    def test_previous_window_is_queried_before_the_current_one(self, repo, _c, client):
        repo.get_muscle_activity.side_effect = [
            activity({"lats": 100.0}),
            activity({"lats": 400.0}),
        ]
        muscles = {
            m["muscle"]: m
            for m in client.get("/strength/stats/muscles?days=7").json()["muscles"]
        }
        assert muscles["lats"]["volume"] == 100.0
        assert muscles["lats"]["previous_volume"] == 400.0
        prev_call = repo.get_muscle_activity.call_args_list[1][0]
        assert prev_call[1] == TODAY - timedelta(days=7)

    @patch("arete.api.strength._cardio_muscle_activity", return_value=({}, {}))
    @patch("arete.api.strength._repo")
    def test_no_training_leaves_everything_cold(self, repo, _c, client):
        repo.get_muscle_activity.return_value = activity({})
        muscles = client.get("/strength/stats/muscles").json()["muscles"]
        assert all(m["level"] == 0 and m["volume"] == 0.0 for m in muscles)

    def test_days_out_of_range_is_rejected(self, client):
        assert client.get("/strength/stats/muscles?days=0").status_code == 422
        assert client.get("/strength/stats/muscles?days=400").status_code == 422
