"""Personalized Banister model coefficient fitting.

Fits athlete-specific k1/k2/baseline parameters from training history
using cardiac efficiency (HR / speed) as the performance proxy.
"""

from __future__ import annotations

import logging
from datetime import date, timedelta

import numpy as np
from sklearn.linear_model import Ridge

from arete.dataio.db import connect
from arete.features.fitness import DailyTSS, calculate_atl, calculate_ctl

logger = logging.getLogger(__name__)


def get_tss_history(con, start_date: date, end_date: date) -> list[DailyTSS]:
    """Fetch daily TSS from actual_sessions."""
    rows = con.execute(
        """
        SELECT date,
               SUM(
                 CASE
                   WHEN rpe IS NOT NULL THEN
                     (COALESCE(duration_sec, 0) / 60.0) * POWER(rpe / 10.0, 2) / 0.36
                   WHEN suffer_score IS NOT NULL THEN
                     suffer_score * 0.8
                   WHEN avg_hr IS NOT NULL THEN
                     (COALESCE(duration_sec, 0) / 60.0) * POWER(LEAST(avg_hr, 200) / 180.0, 2) / 0.36
                   ELSE
                     (COALESCE(duration_sec, 0) / 60.0) * 0.25 / 0.36
                 END
               ) as daily_tss
        FROM app.actual_sessions
        WHERE date >= ? AND date <= ?
          AND user_id = 1
        GROUP BY date
        ORDER BY date ASC
        """,
        [start_date, end_date],
    ).fetchall()

    tss_by_date = {row[0]: float(row[1]) for row in rows}

    tss_list = []
    current = start_date
    while current <= end_date:
        tss = tss_by_date.get(current, 0.0)
        tss_list.append(DailyTSS(date=current, tss=tss))
        current += timedelta(days=1)

    return tss_list


def get_running_sessions(con, start_date: date, end_date: date) -> list[dict]:
    """Fetch running sessions with HR and speed data."""
    rows = con.execute(
        """
        SELECT date, avg_hr, avg_speed_mps
        FROM app.actual_sessions
        WHERE sport IN ('running', 'run')
          AND avg_hr IS NOT NULL
          AND avg_speed_mps IS NOT NULL
          AND avg_speed_mps > 0
          AND date >= ? AND date <= ?
          AND user_id = 1
        ORDER BY date ASC
        """,
        [start_date, end_date],
    ).fetchall()

    return [
        {"date": r[0], "avg_hr": float(r[1]), "avg_speed_mps": float(r[2])}
        for r in rows
    ]


def compute_efficiency(avg_hr: float, avg_speed_mps: float) -> float:
    """Cardiac efficiency: HR per km/h. Lower = more efficient."""
    speed_kmh = avg_speed_mps * 3.6
    return avg_hr / speed_kmh


def fit_coefficients(sessions: list[dict]) -> dict | None:
    """Fit Banister coefficients from session data.

    Args:
        sessions: list of dicts with 'ctl', 'atl', 'avg_hr', 'avg_speed_mps'

    Returns:
        dict with k1, k2, baseline, r2, n_samples, or None if insufficient data
    """
    if len(sessions) < 10:
        return None

    X = np.column_stack(
        [
            [s["ctl"] for s in sessions],
            [s["atl"] for s in sessions],
        ]
    )
    y = np.array(
        [compute_efficiency(s["avg_hr"], s["avg_speed_mps"]) for s in sessions]
    )

    model = Ridge(alpha=1.0, fit_intercept=True)
    model.fit(X, y)

    # Model: efficiency = baseline + k1*CTL - k2*ATL
    # Ridge coef for ATL is the raw coefficient (not negated)
    k1_raw, k2_raw = float(model.coef_[0]), float(model.coef_[1])
    k1 = max(0.0, k1_raw)
    k2 = max(0.0, -k2_raw)  # Negate: ATL should decrease efficiency
    baseline = float(model.intercept_)
    r2 = float(model.score(X, y))

    return {
        "k1": round(k1, 4),
        "k2": round(k2, 4),
        "baseline": round(baseline, 2),
        "r2": round(r2, 4),
        "n_samples": len(sessions),
    }


def load_coefficients(user_id: int = 1) -> dict | None:
    """Load personalized Banister coefficients from DB.

    Returns None if coefficients are not available or R² is too low.
    """
    con = connect(read_only=True)
    try:
        row = con.execute(
            "SELECT k1, k2, baseline, r2 FROM app.banister_coefficients WHERE user_id = ?",
            [user_id],
        ).fetchone()
        if row and row[3] and float(row[3]) > 0.1:
            return {
                "k1": float(row[0]),
                "k2": float(row[1]),
                "baseline": float(row[2]),
                "r2": float(row[3]),
            }
        return None
    finally:
        con.close()


def store_coefficients(coeffs: dict, user_id: int = 1) -> None:
    """UPSERT Banister coefficients into DB."""
    con = connect()
    try:
        con.execute(
            """
            INSERT INTO app.banister_coefficients (user_id, k1, k2, baseline, r2, n_samples, fitted_at)
            VALUES (?, ?, ?, ?, ?, ?, now())
            ON CONFLICT (user_id) DO UPDATE SET
                k1 = EXCLUDED.k1,
                k2 = EXCLUDED.k2,
                baseline = EXCLUDED.baseline,
                r2 = EXCLUDED.r2,
                n_samples = EXCLUDED.n_samples,
                fitted_at = now()
            """,
            [
                user_id,
                coeffs["k1"],
                coeffs["k2"],
                coeffs["baseline"],
                coeffs["r2"],
                coeffs["n_samples"],
            ],
        )
        con.commit()
    finally:
        con.close()
