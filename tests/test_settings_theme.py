"""Theme preferences round-trip through the HTTP and persistence boundaries."""

import pytest

from arete.api.settings import router
from arete.dataio.init_duckdb import main as init_db


@pytest.fixture(autouse=True)
def settings_database(tmp_path, monkeypatch):
    # Other suites intentionally leave legacy settings in the shared database.
    monkeypatch.setenv("ARETE_DB", str(tmp_path / "settings.duckdb"))
    init_db()


@pytest.mark.parametrize("theme", ["light", "dark", "darker", "abyss"])
def test_theme_round_trip(router_client, theme):
    client = router_client(router)
    original = client.get("/settings").json()
    try:
        response = client.put("/settings", json={**original, "theme": theme})
        assert response.status_code == 200, response.text
        assert response.json()["theme"] == theme
        assert client.get("/settings").json()["theme"] == theme
    finally:
        assert client.put("/settings", json=original).status_code == 200


def test_unknown_theme_is_rejected(router_client):
    client = router_client(router)
    original = client.get("/settings").json()
    response = client.put("/settings", json={**original, "theme": "unknown"})
    assert response.status_code == 422
    assert client.get("/settings").json() == original
