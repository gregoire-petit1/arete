"""Trusted athlete scope shared by HTTP, workers and domain services.

Only authentication and scheduled work establish this context. Request bodies
and model tool arguments cannot switch it. ContextVar propagation preserves it
through AnyIO workers and overlapping async invocations.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_athlete: ContextVar[int | None] = ContextVar("arete_athlete", default=None)


def current_athlete_id() -> int:
    from arete.config import config

    value = _athlete.get()
    if value is not None:
        return value
    if config.auth_provider == "clerk":
        raise RuntimeError("Authenticated deployment requires an athlete scope")
    return 1  # Existing self-hosted installations have one implicit athlete.


@contextmanager
def athlete_scope(athlete_id: int) -> Iterator[None]:
    assert type(athlete_id) is int and athlete_id > 0, "Invalid trusted athlete id"
    token = _athlete.set(athlete_id)
    try:
        yield
    finally:
        _athlete.reset(token)


def database_athlete_id() -> int | None:
    """NULL closes private views during account resolution, before authentication."""
    from arete.config import config

    value = _athlete.get()
    return value if value is not None or config.auth_provider == "clerk" else 1


def resolve_athlete_id(requested: int | None = None) -> int:
    actual = current_athlete_id()
    if requested is not None and requested != actual:
        raise PermissionError("Cannot access another athlete")
    return actual
