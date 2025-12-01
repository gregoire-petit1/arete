"""Pytest configuration and fixtures for Arete tests."""

import os
import tempfile
from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Set test database path before importing app modules
_test_db_dir = tempfile.mkdtemp()
os.environ["ARETE_DB"] = str(Path(_test_db_dir) / "test_arete.duckdb")


@pytest.fixture(scope="session")
def test_db_path() -> Path:
    """Return the path to the test database."""
    return Path(os.environ["ARETE_DB"])


@pytest.fixture(scope="session", autouse=True)
def setup_test_db() -> Generator[None, None, None]:
    """Initialize the test database before running tests."""
    from arete.dataio.init_duckdb import main as init_db

    init_db()
    yield
    # Cleanup after all tests
    db_path = Path(os.environ["ARETE_DB"])
    if db_path.exists():
        db_path.unlink()


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Create a test client for the FastAPI app."""
    from arete.api.main import app

    with TestClient(app) as c:
        yield c
