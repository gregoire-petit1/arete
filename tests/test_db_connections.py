"""Readers must coexist with writers during concurrent dashboard requests."""

from contextlib import closing

from arete.dataio.db import connect, db_connection
from arete.dataio.init_duckdb import main as init_schema
from arete.dataio.settings import get_user_settings
from arete.features.banister import load_coefficients
from arete.services.metrics import get_player_stats


def test_dashboard_readers_coexist_with_writer(tmp_path, monkeypatch):
    monkeypatch.setenv("ARETE_DB", str(tmp_path / "connections.duckdb"))
    init_schema()
    # Keep the writer open: sequential requests hide DuckDB's mode conflict.
    with closing(connect()) as writer:
        with db_connection() as reader:
            assert reader.execute("SELECT 1").fetchone() == (1,)
        assert get_player_stats().level == 0
        assert load_coefficients(user_id=999999) is None
        get_user_settings(user_id=1)
        assert writer.execute("SELECT 1").fetchone() == (1,)
