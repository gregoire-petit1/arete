"""Analysis windows: how long a period is, how it is bucketed, what precedes it.

One place decides that "90d" means 90 days grouped by week, and that the window
to compare against is the 90 days just before.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Literal

Bucket = Literal["day", "week", "month"]

PERIOD_DAYS: dict[str, int] = {
    "7d": 7,
    "30d": 30,
    "90d": 90,
    "6m": 180,
    "1y": 365,
    "all": 3650,
}
BUCKET_FOR_PERIOD: dict[str, Bucket] = {
    "7d": "day",
    "30d": "day",
    "90d": "week",
    "6m": "month",
    "1y": "month",
    "all": "month",
}
DEFAULT_PERIOD = "30d"


@dataclass(frozen=True)
class PeriodWindow:
    """A period and the window of the same length right before it."""

    period: str
    bucket: Bucket
    start: date
    end: date  # inclusive
    prev_start: date | None
    prev_end: date | None

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1


def resolve_period(
    period: str, today: date, earliest: date | None = None
) -> PeriodWindow:
    """Window for ``period`` ending today, plus the comparable window before it.

    ``all`` starts at the athlete's first session (or 10 years back) and has no
    previous window to compare against.
    """
    key = period if period in PERIOD_DAYS else DEFAULT_PERIOD
    bucket = BUCKET_FOR_PERIOD[key]
    end = today

    if key == "all":
        start = earliest or (today - timedelta(days=PERIOD_DAYS["all"] - 1))
        return PeriodWindow(key, bucket, start, end, None, None)

    length = PERIOD_DAYS[key]
    start = end - timedelta(days=length - 1)
    prev_end = start - timedelta(days=1)
    return PeriodWindow(
        key, bucket, start, end, prev_end - timedelta(days=length - 1), prev_end
    )


def bucket_start(d: date, bucket: Bucket) -> date:
    """First day of the bucket ``d`` belongs to (Monday for weeks, 1st for months)."""
    if bucket == "day":
        return d
    if bucket == "week":
        return d - timedelta(days=d.weekday())
    return d.replace(day=1)


def bucket_key(d: date, bucket: Bucket) -> str:
    return bucket_start(d, bucket).isoformat()


def bucket_keys(start: date, end: date, bucket: Bucket) -> list[str]:
    """Every bucket between two dates, in order, including empty ones."""
    keys: list[str] = []
    cur = bucket_start(start, bucket)
    while cur <= end:
        keys.append(cur.isoformat())
        if bucket == "day":
            cur += timedelta(days=1)
        elif bucket == "week":
            cur += timedelta(days=7)
        else:
            cur = (cur.replace(day=28) + timedelta(days=4)).replace(day=1)
    return keys
