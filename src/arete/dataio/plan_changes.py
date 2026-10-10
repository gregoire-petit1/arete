"""Notice, within one HTTP request, that the training plan changed.

Writers of ``app.planned_sessions`` call :func:`touch`. The HTTP layer opens a
:func:`watch` around each request and, once the response is sent, follows the
plan into Google Calendar when something changed. Outside a watched request
(tests, the in-process scheduler) ``touch`` does nothing: the daily sync
reconciles the whole window anyway.

A mutable flag rather than a plain value: route handlers, streamed bodies and
agent tools run in copies of the request's context, and a copy shares the
flag object while a reassignment would stay in the copy.
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

_changed: ContextVar[list[bool] | None] = ContextVar("arete_plan_changed", default=None)


def touch() -> None:
    """Record that this request changed the plan (no-op outside a request)."""
    flag = _changed.get()
    if flag is not None:
        flag[:] = [True]


def clear() -> None:
    """Forget the change: the caller has just synced the plan itself."""
    flag = _changed.get()
    if flag is not None:
        flag.clear()


@contextmanager
def watch() -> Iterator[list[bool]]:
    """A flag that turns truthy when the plan changes inside the block."""
    flag: list[bool] = []
    token = _changed.set(flag)
    try:
        yield flag
    finally:
        _changed.reset(token)
