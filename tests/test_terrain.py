"""Grade-adjusted pace (Minetti), climbing speed and the descent profile."""

from __future__ import annotations

import pytest

from arete.features.terrain import (
    MINETTI_COEFFICIENTS,
    analyze,
    grade_factor,
    running_cost,
)


def _course(
    n: int, *, speed: float = 3.0, grade=lambda i: 0.0, start_alt: float = 1000.0
):
    """(t, altitude, distance) of an n-second run at ``speed`` m/s."""
    t, alt, dist = [], [], []
    altitude = start_alt
    for i in range(n):
        if i:
            altitude += speed * grade(i)
        t.append(i)
        alt.append(altitude)
        dist.append(i * speed)
    return t, alt, dist


class TestMinetti:
    def test_flat_cost_is_minettis_intercept(self):
        assert running_cost(0) == pytest.approx(3.6)
        assert grade_factor(0) == pytest.approx(1.0)

    def test_published_values(self):
        # Minetti et al. 2002, Cr at +10 % and -10 %.
        assert running_cost(0.10) == pytest.approx(5.97, abs=0.01)
        assert running_cost(-0.10) == pytest.approx(2.15, abs=0.01)

    def test_uphill_costs_more_and_steeper_is_clamped(self):
        assert grade_factor(0.05) > 1 > grade_factor(-0.05)
        assert grade_factor(0.80) == grade_factor(0.45)
        assert len(MINETTI_COEFFICIENTS) == 6


class TestGap:
    def test_a_flat_run_keeps_its_pace(self):
        t, alt, dist = _course(1800)
        terrain = analyze(t, alt, dist, pace_sec_km=333)
        assert terrain is not None
        assert terrain.grade_factor == pytest.approx(1.0, abs=0.001)
        assert terrain.gap_sec_km == 333

    def test_altitude_noise_does_not_read_as_hills(self):
        # +/- 1.5 m of barometric jitter every second on a flat road
        t, _, dist = _course(1800)
        alt = [1000 + (1.5 if i % 2 else -1.5) for i in range(1800)]
        terrain = analyze(t, alt, dist, pace_sec_km=333)
        assert terrain is not None and terrain.grade_factor == pytest.approx(
            1, abs=0.02
        )

    def test_a_climb_reads_faster_than_its_pace(self):
        t, alt, dist = _course(1800, speed=2.0, grade=lambda i: 0.10)
        terrain = analyze(t, alt, dist, pace_sec_km=500)
        assert terrain is not None
        assert terrain.grade_factor == pytest.approx(5.97 / 3.6, rel=0.02)
        assert terrain.gap_sec_km == pytest.approx(500 / (5.97 / 3.6), abs=5)

    def test_without_the_session_pace_the_moving_pace_is_used(self):
        t, alt, dist = _course(1200, speed=4.0)
        terrain = analyze(t, alt, dist)
        assert terrain is not None and terrain.gap_sec_km == 250

    def test_pauses_are_not_effort(self):
        # 10 min standing still in the middle: neither time nor distance
        t, alt, dist = _course(1200)
        t = [x if x < 600 else x + 600 for x in t]
        terrain = analyze(t, alt, dist)
        assert terrain is not None and terrain.gap_sec_km == 333

    def test_no_altitude_no_terrain(self):
        t, _, dist = _course(600)
        assert analyze(t, None, dist) is None
        assert analyze(t, [None] * 600, dist) is None

    def test_too_short_for_a_gap_still_has_climbing(self):
        # 800 m of treadmill-like distance, but altitude for the VAM
        t, alt, dist = _course(400, speed=2.0, grade=lambda i: 0.2)
        terrain = analyze(t, alt, dist)
        assert terrain is not None and terrain.gap_sec_km is None
        assert terrain.vam[5] == pytest.approx(2.0 * 0.2 * 3600, rel=0.02)


class TestClimbing:
    def test_a_steady_climb_gives_its_rate_on_every_duration_it_lasts(self):
        # 1440 m/h: 0.4 m/s up, for 40 min
        t, alt, dist = _course(2400, speed=1.0, grade=lambda i: 0.4)
        terrain = analyze(t, alt, dist)
        assert terrain is not None
        assert set(terrain.vam) == {5, 10, 20, 30}  # too short for 60 min
        for rate in terrain.vam.values():
            assert rate == pytest.approx(1440, rel=0.02)

    def test_the_best_window_is_found_inside_a_longer_run(self):
        # flat, then 10 min at 1080 m/h, then flat
        t, alt, dist = _course(
            3700, speed=1.5, grade=lambda i: 0.2 if 1200 <= i < 1800 else 0.0
        )
        terrain = analyze(t, alt, dist)
        assert terrain is not None
        assert terrain.vam[5] == pytest.approx(1080, rel=0.03)
        assert terrain.vam[60] == pytest.approx(180, rel=0.03)  # 180 m in the hour

    def test_a_descent_has_no_climbing_speed(self):
        t, alt, dist = _course(1800, grade=lambda i: -0.1)
        terrain = analyze(t, alt, dist)
        assert terrain is not None and terrain.vam == {}


class TestDescent:
    def test_time_and_distance_land_in_their_grade_band(self):
        # 10 min flat, then 10 min at -12 %
        t, alt, dist = _course(1200, grade=lambda i: -0.12 if i >= 600 else 0.0)
        terrain = analyze(t, alt, dist)
        assert terrain is not None
        bands = {(b["min"], b["max"]): b for b in terrain.descent}
        assert bands[(-2, 2)]["sec"] == pytest.approx(600, abs=40)
        assert bands[(-15, -10)]["sec"] == pytest.approx(600, abs=40)
        assert bands[(-15, -10)]["m"] == pytest.approx(1800, abs=120)
