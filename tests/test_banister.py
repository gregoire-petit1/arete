"""Tests for Banister coefficient fitting."""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest

from arete.features.banister import compute_efficiency, fit_coefficients
from arete.features.fitness import DailyTSS, calculate_atl, calculate_ctl


# ── Helpers ──────────────────────────────────────────────────


def _make_daily_tss(dates: list[date], tss_values: list[float]):
    """Build list of DailyTSS for the fitness module."""
    return [DailyTSS(date=d, tss=t) for d, t in zip(dates, tss_values)]


# ── Unit tests ───────────────────────────────────────────────


class TestFitCoefficients:
    def test_recovers_known_coefficients(self):
        rng = np.random.default_rng(42)
        n = 150

        ctl_vals = rng.uniform(40, 120, n).tolist()
        atl_vals = rng.uniform(30, 150, n).tolist()

        true_k1, true_k2, true_baseline = 0.8, 1.5, 60.0

        eff = np.array(
            [
                true_baseline + true_k1 * c - true_k2 * a
                for c, a in zip(ctl_vals, atl_vals)
            ]
        )
        noise = rng.normal(0, 3, size=len(eff))
        y = eff + noise

        sessions = []
        for i, (ctl, atl) in enumerate(zip(ctl_vals, atl_vals)):
            speed_mps = rng.uniform(2.5, 4.5)
            eff_target = y[i]
            hr = eff_target * speed_mps * 3.6
            sessions.append(
                {
                    "ctl": ctl,
                    "atl": atl,
                    "avg_hr": hr,
                    "avg_speed_mps": speed_mps,
                }
            )

        result = fit_coefficients(sessions)
        assert result is not None
        assert result["n_samples"] == n
        assert abs(result["k1"] - true_k1) < 0.3, f"k1: {result['k1']} vs {true_k1}"
        assert abs(result["k2"] - true_k2) < 0.3, f"k2: {result['k2']} vs {true_k2}"
        assert abs(result["baseline"] - true_baseline) < 5.0, (
            f"baseline: {result['baseline']} vs {true_baseline}"
        )
        assert result["r2"] > 0.8

    def test_insufficient_data_returns_none(self):
        assert fit_coefficients([]) is None

        sessions = [
            {"ctl": 50, "atl": 40, "avg_hr": 140, "avg_speed_mps": 3.0}
            for _ in range(9)
        ]
        assert fit_coefficients(sessions) is None

    def test_negative_coefficients_are_clamped(self):
        rng = np.random.default_rng(7)
        n = 50
        ctl_vals = rng.uniform(40, 100, n).tolist()
        atl_vals = rng.uniform(30, 120, n).tolist()

        sessions = []
        for c, a in zip(ctl_vals, atl_vals):
            speed_mps = rng.uniform(2.5, 4.5)
            hr = (60.0 + 0.5 * c + 2.0 * a) * speed_mps * 3.6
            sessions.append(
                {
                    "ctl": c,
                    "atl": a,
                    "avg_hr": hr,
                    "avg_speed_mps": speed_mps,
                }
            )

        result = fit_coefficients(sessions)
        if result is not None:
            assert result["k2"] >= 0.0
            assert result["k1"] >= 0.0

    def test_compute_efficiency(self):
        assert compute_efficiency(150, 10.0 / 3.6) == pytest.approx(15.0)
        assert compute_efficiency(120, 12.0 / 3.6) == pytest.approx(10.0)


class TestCtlAtlFromTssHistory:
    def test_ctl_convergence(self):
        """CTL converges with enough constant-TSS data."""
        today = date.today()
        n_days = 300
        dates = [today - timedelta(days=i) for i in range(n_days, 0, -1)]
        tss_values = [60.0] * len(dates)
        tss_history = _make_daily_tss(dates, tss_values)

        ctl = calculate_ctl(tss_history, today)
        # 84 iterations at TC=42 → ~87% convergence:
        #   CTL after 84 of 60 = 60*(1 - (1-1/42)^85) ≈ 52
        #   Since today has TSS=0, final CTL ≈ 52 + (0-52)/42 ≈ 50.8
        assert abs(ctl - 50.0) < 3.0, f"CTL {ctl} should be ~50.8"

    def test_atl_convergence(self):
        today = date.today()
        n_days = 120
        dates = [today - timedelta(days=i) for i in range(n_days, 0, -1)]
        tss_values = [60.0] * len(dates)
        tss_history = _make_daily_tss(dates, tss_values)

        atl = calculate_atl(tss_history, today)
        # 28 iterations at TC=7 → ~98% convergence:
        #   ATL after 28 of 60 = 60*(1 - (1-1/7)^28) ≈ 59.2
        #   Since today has TSS=0, final ATL ≈ 59.2 + (0-59.2)/7 ≈ 50.7
        assert abs(atl - 50.0) < 3.0, f"ATL {atl} should be ~50.7"

    def test_ctl_smoother_than_atl(self):
        """CTL should be smoother (closer to mean) than ATL with alternating input."""
        today = date.today()
        n_days = 120
        dates = [today - timedelta(days=i) for i in range(n_days, 0, -1)]
        tss_values = [100.0 if i % 2 == 0 else 20.0 for i in range(len(dates))]
        tss_history = _make_daily_tss(dates, tss_values)

        ctl = calculate_ctl(tss_history, today)
        atl = calculate_atl(tss_history, today)

        # Both converge toward 60 (mean of 100 and 20)
        # CTL should be closer to the mean than ATL since it damps more
        assert abs(ctl - 60.0) < abs(atl - 60.0)
