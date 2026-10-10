"""Readers must coexist with writers during concurrent dashboard requests."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from threading import Barrier, Event

import duckdb
import pytest

from arete.dataio.db import connect, db_connection
from arete.dataio.init_duckdb import main as init_schema
from arete.dataio.settings import get_user_settings
from arete.features.banister import load_coefficients
from arete.services.metrics import get_player_stats


def test_local_opens_are_serialized_but_queries_can_overlap(tmp_path, monkeypatch):
    monkeypatch.setenv("ARETE_DB", str(tmp_path / "concurrent.duckdb"))
    original_connect = duckdb.connect
    opening, release, second_started, overlapping = (Event() for _ in range(4))
    querying = Barrier(2, timeout=5)

    def paused_connect(*args, **kwargs):
        if opening.is_set():
            overlapping.set()
        else:
            opening.set()
            assert release.wait(timeout=5)
        return original_connect(*args, **kwargs)

    def read(second=False):
        if second:
            second_started.set()
        with closing(connect()) as con:
            # Holding the lock for the connection's lifetime would deadlock here.
            querying.wait()
            return con.execute("SELECT 1").fetchone()

    monkeypatch.setattr(duckdb, "connect", paused_connect)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(read)
        try:
            assert opening.wait(timeout=5)
            second = pool.submit(read, True)
            assert second_started.wait(timeout=5)
            assert not overlapping.wait(timeout=0.1)
        finally:
            release.set()
        assert first.result(timeout=5) == (1,)
        assert second.result(timeout=5) == (1,)


def test_failed_local_open_is_not_retried_and_releases_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("ARETE_DB", str(tmp_path / "failed.duckdb"))
    original_connect = duckdb.connect
    attempts = 0

    def fail_once(*args, **kwargs):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise duckdb.IOException("cannot open database")
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(duckdb, "connect", fail_once)
    with pytest.raises(duckdb.IOException, match="cannot open database"):
        connect()
    assert attempts == 1
    with closing(connect()) as con:
        assert con.execute("SELECT 1").fetchone() == (1,)
    assert attempts == 2


def test_dashboard_readers_coexist_with_writer(tmp_path, monkeypatch):
    monkeypatch.setenv("ARETE_DB", str(tmp_path / "connections.duckdb"))
    init_schema()
    # Keep the writer open: sequential requests hide DuckDB's mode conflict.
    with closing(connect()) as writer:
        with db_connection() as reader:
            assert reader.execute("SELECT 1").fetchone() == (1,)
        assert get_player_stats().level == 0
        assert load_coefficients() is None
        get_user_settings(user_id=1)
        assert writer.execute("SELECT 1").fetchone() == (1,)
