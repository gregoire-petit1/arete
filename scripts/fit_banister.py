"""CLI entry point for fitting personalized Banister coefficients.

Usage:
    uv run python scripts/fit_banister.py
    uv run python scripts/fit_banister.py --dry-run
    uv run python scripts/fit_banister.py --start 2025-01-01 --end 2026-06-03
"""

from __future__ import annotations

import argparse
import logging
from datetime import date, timedelta

from arete.dataio.db import connect
from arete.features.banister import (
    fit_coefficients,
    get_running_sessions,
    get_tss_history,
    store_coefficients,
)
from arete.features.fitness import calculate_atl, calculate_ctl

logger = logging.getLogger(__name__)


def main(
    dry_run: bool = False,
    start_date_str: str | None = None,
    end_date_str: str | None = None,
) -> dict | None:
    """Run the Banister coefficient fitting pipeline."""
    end = date.fromisoformat(end_date_str) if end_date_str else date.today()
    start = (
        date.fromisoformat(start_date_str)
        if start_date_str
        else end - timedelta(days=180)
    )

    con = connect(read_only=True)
    try:
        tss_history = get_tss_history(con, start - timedelta(days=84), end)
        sessions = get_running_sessions(con, start, end)
    finally:
        con.close()

    if not sessions:
        print("No running sessions with HR data found in date range.")
        return None

    for s in sessions:
        s["ctl"] = calculate_ctl(tss_history, s["date"])
        s["atl"] = calculate_atl(tss_history, s["date"])

    result = fit_coefficients(sessions)
    if result is None:
        print(f"Insufficient data: {len(sessions)} sessions (need >= 10).")
        return None

    print(f"\nFitted coefficients ({result['n_samples']} sessions, R²={result['r2']}):")
    print(f"  k1 (fitness gain)  = {result['k1']}")
    print(f"  k2 (fatigue cost)  = {result['k2']}")
    print(f"  baseline (speed per beat at rest) = {result['baseline']}")

    if dry_run:
        print("\nDry-run: coefficients NOT saved.")
    else:
        store_coefficients(result)
        print("\nCoefficients saved to app.banister_coefficients.")

    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    parser = argparse.ArgumentParser(description="Fit Banister model coefficients")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print coefficients without saving"
    )
    parser.add_argument("--start", type=str, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, help="End date (YYYY-MM-DD)")
    args = parser.parse_args()

    main(dry_run=args.dry_run, start_date_str=args.start, end_date_str=args.end)
