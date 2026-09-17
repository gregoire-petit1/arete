"""Analysis windows: length, bucket, previous window."""

from __future__ import annotations

from datetime import date

import pytest

from arete.features.periods import (
    BUCKET_FOR_PERIOD,
    PERIOD_DAYS,
    bucket_keys,
    bucket_start,
    resolve_period,
)

TODAY = date(2026, 9, 17)


class TestResolvePeriod:
    @pytest.mark.parametrize(("period", "bucket"), list(BUCKET_FOR_PERIOD.items()))
    def test_bucket_per_period(self, period, bucket):
        assert resolve_period(period, TODAY).bucket == bucket

    @pytest.mark.parametrize("period", ["7d", "30d", "90d", "6m", "1y"])
    def test_window_has_the_expected_length(self, period):
        w = resolve_period(period, TODAY)
        assert w.end == TODAY
        assert w.days == PERIOD_DAYS[period]

    def test_previous_window_sits_just_before(self):
        w = resolve_period("30d", TODAY)
        assert w.prev_end == w.start - (w.start - w.start).__class__(days=1)
        assert (w.prev_end - w.prev_start).days + 1 == 30

    def test_all_starts_at_the_first_session_and_has_no_comparison(self):
        w = resolve_period("all", TODAY, earliest=date(2025, 1, 1))
        assert w.start == date(2025, 1, 1)
        assert w.prev_start is None and w.prev_end is None

    def test_unknown_period_falls_back_to_30d(self):
        assert resolve_period("banana", TODAY).days == 30


class TestBuckets:
    def test_bucket_start(self):
        assert bucket_start(date(2026, 9, 17), "day") == date(2026, 9, 17)
        assert bucket_start(date(2026, 9, 17), "week") == date(2026, 9, 14)  # Monday
        assert bucket_start(date(2026, 9, 17), "month") == date(2026, 9, 1)

    def test_keys_are_gap_filled(self):
        assert len(bucket_keys(date(2026, 9, 11), date(2026, 9, 17), "day")) == 7
        weeks = bucket_keys(date(2026, 6, 19), date(2026, 9, 17), "week")
        assert weeks[0] == "2026-06-15" and len(weeks) == 14
        months = bucket_keys(date(2026, 1, 15), date(2026, 9, 17), "month")
        assert months == [f"2026-{m:02d}-01" for m in range(1, 10)]

    def test_month_rollover(self):
        assert bucket_keys(date(2026, 12, 15), date(2027, 2, 3), "month") == [
            "2026-12-01",
            "2027-01-01",
            "2027-02-01",
        ]
