"""Tests for the HR drift / decoupling analysis (pure functions)."""

from __future__ import annotations

import json

from arete.features.hr_drift import (
    analyze_runs,
    classify_run_type,
    effort_class,
    run_from_row,
    score_run,
)


def _laps(hrs: list[float], speeds: list[float]) -> str:
    return json.dumps(
        [
            {"distance": 1000, "average_heartrate": hr, "average_speed": sp}
            for hr, sp in zip(hrs, speeds, strict=True)
        ]
    )


def _row(rid: int, hrs: list[float], speeds: list[float], dist_m: float = 10000.0):
    return (rid, "2026-06-01", "run", dist_m, 50.0, 3000, 150, 300, _laps(hrs, speeds))


class TestRunFromRow:
    def test_requires_four_km_laps(self):
        assert run_from_row(_row(1, [140, 141, 142], [3.3, 3.3, 3.3])) is None

    def test_drift_and_decoupling(self):
        # HR rises 140 -> 154 (+10 %) at constant pace: decoupling = +10 %
        run = run_from_row(_row(1, [140, 140, 154, 154], [3.3] * 4))
        assert run is not None
        assert run["hr_drift_pct"] == 10.0
        assert run["pace_drift_pct"] == 0.0
        assert run["decoupling_pct"] == 10.0
        assert len(run["splits"]) == 4

    def test_bad_json_skipped(self):
        assert run_from_row((1, "2026-06-01", "x", 1, 1, 1, 1, 1, "{not json")) is None


class TestClassification:
    def test_run_types(self):
        assert (
            classify_run_type(
                {"distance_km": 8.0, "avg_pace_sec_km": 300, "elevation_m": 20}
            )
            == "intensity"
        )
        assert (
            classify_run_type(
                {"distance_km": 20.0, "avg_pace_sec_km": 420, "elevation_m": 900}
            )
            == "trail_long"
        )
        assert (
            classify_run_type(
                {"distance_km": 20.0, "avg_pace_sec_km": 420, "elevation_m": 100}
            )
            == "long_run"
        )
        assert (
            classify_run_type(
                {"distance_km": 10.0, "avg_pace_sec_km": 420, "elevation_m": 50}
            )
            == "base"
        )

    def test_scores_are_monotonic_in_hr_drift(self):
        order = ["excellent", "good", "moderate", "concerning"]
        scores = [score_run("base", hr, None) for hr in (-1, 2, 5, 8, 15)]
        assert [order.index(s) for s in scores] == sorted(
            order.index(s) for s in scores
        )

    def test_effort_class(self):
        assert effort_class({"distance_km": 5.0, "elevation_m": 0}) == "short"
        assert (
            effort_class({"distance_km": 25.0, "elevation_m": 2500}) == "long_mountain"
        )


class TestAnalyzeRuns:
    def test_no_baseline_below_ten_runs(self):
        result = analyze_runs(
            [_row(i, [140, 140, 150, 150], [3.3] * 4) for i in range(3)]
        )
        assert result["count"] == 3
        assert result["baseline"] is None
        assert all(r["drift_residual_pct"] is None for r in result["runs"])
        assert set(result["effort_buckets"]) == {"moderate_flat"}

    def test_baseline_fitted_and_residuals_present(self):
        rows = []
        for i in range(12):
            dist = 6000 + i * 1000
            hr_end = 145 + i  # decoupling grows with distance
            rows.append(_row(i, [140, 140, hr_end, hr_end], [3.3] * 4, dist_m=dist))
        result = analyze_runs(rows)
        assert result["baseline"] is not None
        assert result["baseline"]["n_samples"] == 12
        assert "_slopes" not in result["baseline"]
        assert all(r["drift_residual_pct"] is not None for r in result["runs"])
        assert all(
            r["drift_score"] in {"excellent", "good", "moderate", "concerning"}
            for r in result["runs"]
        )
