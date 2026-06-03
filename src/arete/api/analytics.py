"""Analytics API endpoints.

Provides historical training analytics: volume, training load, pace trends,
HR zones, sport distribution, and best efforts.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date, timedelta

import numpy as np
from fastapi import APIRouter, Query
from pydantic import BaseModel

from arete.api.metrics import _get_tss_history
from arete.dataio.db import connect

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])

# ---------- Helpers ----------

PERIOD_MAP: dict[str, int] = {
    "7d": 7,
    "30d": 30,
    "90d": 90,
    "6m": 180,
    "1y": 365,
    "all": 3650,
}

SPORT_FILTER: dict[str, tuple[str, ...]] = {
    "running": ("run", "trail_run"),
    "cycling": ("ride", "virtual_ride"),
}

EFFORT_NAMES = ("400m", "1k", "1 mile", "5k", "10k", "Half-Marathon")


def _parse_period(period: str) -> int:
    """Convert a period string to a number of days."""
    return PERIOD_MAP.get(period, 30)


def _format_pace(sec_per_km: int) -> str:
    """Format seconds per km as 'M:SS'."""
    minutes = sec_per_km // 60
    seconds = sec_per_km % 60
    return f"{minutes}:{seconds:02d}"


# ---------- Endpoints ----------


@router.get("/volume")
def get_volume(
    period: str = Query("30d"),
    sport: str = Query("all"),
):
    """Weekly volume aggregated by sport."""
    days = _parse_period(period)
    start_date = date.today() - timedelta(days=days)

    con = connect(read_only=True)
    try:
        sport_filter = ""
        params: list = [start_date]
        if sport != "all":
            sport_filter = "AND sport = ?"
            params.append(sport)

        rows = con.execute(
            f"""
            SELECT DATE_TRUNC('week', date) as week,
                   sport,
                   SUM(duration_sec) / 3600.0 as hours,
                   SUM(COALESCE(distance_m, 0)) / 1000.0 as km
            FROM app.actual_sessions
            WHERE date >= ? AND user_id = 1
              {sport_filter}
            GROUP BY week, sport
            ORDER BY week ASC, sport ASC
            """,
            params,
        ).fetchall()
    finally:
        con.close()

    weeks_map: dict[str, dict] = {}
    for week_ts, row_sport, hours, km in rows:
        week_str = str(week_ts.date()) if hasattr(week_ts, "date") else str(week_ts)
        if week_str not in weeks_map:
            weeks_map[week_str] = {
                "week": week_str,
                "sports": {},
                "total_hours": 0.0,
                "total_km": 0.0,
            }
        entry = weeks_map[week_str]
        h = round(hours, 1)
        k = round(km, 1)
        entry["sports"][row_sport] = {"hours": h, "km": k}
        entry["total_hours"] = round(entry["total_hours"] + h, 1)
        entry["total_km"] = round(entry["total_km"] + k, 1)

    return {"weeks": list(weeks_map.values())}


@router.get("/training-load")
def get_training_load(
    period: str = Query("90d"),
):
    """Daily CTL / ATL / TSB time series."""
    days = _parse_period(period)
    tss_history = _get_tss_history(days=days)

    ctl = 0.0
    atl = 0.0
    data = []
    for day_tss in tss_history:
        ctl = ctl + (day_tss.tss - ctl) / 42.0
        atl = atl + (day_tss.tss - atl) / 7.0
        tsb = ctl - atl
        data.append(
            {
                "date": str(day_tss.date),
                "ctl": round(ctl, 1),
                "atl": round(atl, 1),
                "tsb": round(tsb, 1),
                "tss": round(day_tss.tss, 1),
            }
        )

    return {"data": data}


@router.get("/pace")
def get_pace(
    period: str = Query("90d"),
    sport: str = Query("running"),
):
    """Pace trend for running or cycling activities."""
    days = _parse_period(period)
    start_date = date.today() - timedelta(days=days)
    sports = SPORT_FILTER.get(sport, ("run",))
    placeholders = ", ".join("?" for _ in sports)

    con = connect(read_only=True)
    try:
        rows = con.execute(
            f"""
            SELECT date, avg_pace_sec_km, distance_m, duration_sec, name
            FROM app.actual_sessions
            WHERE date >= ? AND user_id = 1
              AND sport IN ({placeholders})
              AND avg_pace_sec_km IS NOT NULL
            ORDER BY date ASC
            """,
            [start_date, *sports],
        ).fetchall()
    finally:
        con.close()

    activities = []
    for row_date, pace, distance_m, _duration, name in rows:
        pace_int = int(pace)
        activities.append(
            {
                "date": str(row_date),
                "pace_sec_km": pace_int,
                "pace_display": _format_pace(pace_int),
                "distance_km": round(distance_m / 1000.0, 1) if distance_m else 0.0,
                "name": name or "",
            }
        )

    return {"activities": activities}


@router.get("/hr-zones")
def get_hr_zones(
    period: str = Query("30d"),
):
    """Weekly HR zone distribution."""
    days = _parse_period(period)
    start_date = date.today() - timedelta(days=days)

    con = connect(read_only=True)
    try:
        rows = con.execute(
            """
            SELECT DATE_TRUNC('week', date) as week,
                   hr_zones_json
            FROM app.actual_sessions
            WHERE date >= ? AND user_id = 1
              AND hr_zones_json IS NOT NULL
            ORDER BY week ASC
            """,
            [start_date],
        ).fetchall()
    finally:
        con.close()

    if not rows:
        return {"weeks": []}

    weeks_map: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for week_ts, hr_json in rows:
        week_str = str(week_ts.date()) if hasattr(week_ts, "date") else str(week_ts)
        zones = json.loads(hr_json) if isinstance(hr_json, str) else hr_json
        for zone_name, seconds in zones.items():
            weeks_map[week_str][zone_name] += int(seconds)

    result = [{"week": w, "zones": dict(z)} for w, z in sorted(weeks_map.items())]
    return {"weeks": result}


@router.get("/sport-distribution")
def get_sport_distribution(
    period: str = Query("90d"),
):
    """Sport distribution by hours and count."""
    days = _parse_period(period)
    start_date = date.today() - timedelta(days=days)

    con = connect(read_only=True)
    try:
        rows = con.execute(
            """
            SELECT sport,
                   SUM(duration_sec) / 3600.0 as hours,
                   COUNT(*) as count
            FROM app.actual_sessions
            WHERE date >= ? AND user_id = 1
            GROUP BY sport
            ORDER BY hours DESC
            """,
            [start_date],
        ).fetchall()
    finally:
        con.close()

    total_hours = sum(row[1] for row in rows) if rows else 0.0
    sports = []
    for row_sport, hours, count in rows:
        pct = round(hours / total_hours * 100, 1) if total_hours > 0 else 0.0
        sports.append(
            {
                "sport": row_sport,
                "hours": round(hours, 1),
                "count": int(count),
                "percentage": pct,
            }
        )

    return {"sports": sports, "total_hours": round(total_hours, 1)}


@router.get("/best-efforts")
def get_best_efforts(
    sport: str = Query("running"),
):
    """All-time best efforts (PRs) for common distances."""
    sports = SPORT_FILTER.get(sport, ("run",))
    placeholders = ", ".join("?" for _ in sports)

    con = connect(read_only=True)
    try:
        rows = con.execute(
            f"""
            SELECT best_efforts_json, date, name
            FROM app.actual_sessions
            WHERE user_id = 1
              AND best_efforts_json IS NOT NULL
              AND sport IN ({placeholders})
            ORDER BY date DESC
            """,
            list(sports),
        ).fetchall()
    finally:
        con.close()

    # Track best per effort name
    bests: dict[str, dict] = {}
    for efforts_json, row_date, activity_name in rows:
        efforts = (
            json.loads(efforts_json) if isinstance(efforts_json, str) else efforts_json
        )
        if not isinstance(efforts, list):
            continue
        for effort in efforts:
            name = effort.get("name", "")
            if name not in EFFORT_NAMES:
                continue
            elapsed = effort.get("elapsed_time", 0)
            if elapsed <= 0:
                continue
            if name not in bests or elapsed < bests[name]["best_time_sec"]:
                bests[name] = {
                    "name": name,
                    "best_time_sec": elapsed,
                    "best_time_display": _format_pace(elapsed),
                    "date": str(row_date),
                    "activity_name": activity_name or "",
                }

    # Return in canonical order
    ordered = [bests[n] for n in EFFORT_NAMES if n in bests]
    return {"efforts": ordered}


# ---------- Session CRUD ----------


class SessionUpdate(BaseModel):
    rpe: int | None = None
    notes: str | None = None


@router.patch("/sessions/{session_id}")
def update_session(session_id: int, body: SessionUpdate):
    """Update RPE and/or notes for an actual session."""
    con = connect(read_only=False)
    try:
        updates = []
        values: list = []
        if body.rpe is not None:
            updates.append("rpe = ?")
            values.append(body.rpe)
        if body.notes is not None:
            updates.append("notes = ?")
            values.append(body.notes)
        if not updates:
            return {"success": True}

        values.append(session_id)
        con.execute(
            f"UPDATE app.actual_sessions SET {', '.join(updates)} WHERE id = ?",
            values,
        )
        return {"success": True}
    finally:
        con.close()


@router.get("/sessions")
def list_sessions(limit: int = 20, offset: int = 0):
    """List recent actual sessions (for Log page)."""
    con = connect(read_only=True)
    try:
        rows = con.execute(
            """
            SELECT id, date, sport, name, duration_sec, distance_m,
                   avg_hr, avg_pace_sec_km, rpe, notes, source, calories
            FROM app.actual_sessions
            WHERE user_id = 1
            ORDER BY date DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            [limit, offset],
        ).fetchall()

        sessions = []
        for r in rows:
            pace_display = None
            if r[7]:
                pace_display = f"{r[7] // 60}:{r[7] % 60:02d}"
            sessions.append(
                {
                    "id": r[0],
                    "date": str(r[1]),
                    "sport": r[2],
                    "name": r[3],
                    "duration_sec": r[4],
                    "distance_m": r[5],
                    "avg_hr": r[6],
                    "avg_pace_sec_km": r[7],
                    "pace_display": pace_display,
                    "rpe": r[8],
                    "notes": r[9],
                    "source": r[10],
                    "calories": r[11],
                }
            )
    finally:
        con.close()

    return {"sessions": sessions}


@router.get("/hr-drift")
def get_hr_drift(
    period: str = Query("1y"),
    min_duration_min: int = Query(40, ge=20, le=240),
):
    """HR drift per run with proper normalization (cardiac decoupling + residual).

    The raw HR drift (last_2km_hr - first_2km_hr) / first_hr is confounded by
    distance, gradient, and D+. This endpoint computes:

    1. **Per-km HR profile** (split by half) — raw data for visualization
    2. **HR drift %** (raw) — first half vs second half average HR
    3. **Pace drift %** (raw) — first half vs second half average pace
    4. **Cardiac decoupling %** (Friel) = pace_drift + hr_drift
       - <5% = excellent aerobic fitness (HR stable despite effort)
       - 5-10% = good
       - >10% = cardiac drift (aerobic capacity under-trained, fatigue, or heat)
    5. **Residual drift** = actual_decoupling - predicted_by_baseline
       Baseline = linear regression of decoupling ~ distance + D+/km + avg_pace
       Negative residual = better than athlete's own baseline (good day)
       Positive residual = worse than baseline (fatigue, illness, overtraining)
    6. **Drift score** based on residual + decoupling combination

    Only includes runs >= min_duration_min with >= 4 full 1-km laps.
    """
    days = _parse_period(period)
    start_date = date.today() - timedelta(days=days)
    min_duration_sec = min_duration_min * 60

    con = connect(read_only=True)
    try:
        rows = con.execute(
            """
            SELECT id, date, name, distance_m, ascent_m,
                   moving_time_sec, avg_hr, avg_pace_sec_km, laps_json
            FROM app.actual_sessions
            WHERE date >= ? AND user_id = 1
              AND sport IN ('run', 'trail_run', 'running', 'virtualrun')
              AND moving_time_sec >= ?
              AND laps_json IS NOT NULL
            ORDER BY date ASC
            """,
            [start_date, min_duration_sec],
        ).fetchall()
    finally:
        con.close()

    # ---- Step 1: compute per-run metrics from laps ----
    raw_runs: list[dict] = []
    for r in rows:
        rid, date_v, name, dist_m, dplus, dur, avg_hr, pace_sec, laps_str = r
        try:
            laps = json.loads(laps_str) if laps_str else []
        except (json.JSONDecodeError, TypeError):
            continue

        km_laps = [
            l
            for l in laps
            if 900 <= (l.get("distance") or 0) <= 1100
            and l.get("average_heartrate")
            and l.get("average_speed")
        ]
        if len(km_laps) < 4:
            continue

        # Per-km HR, pace, elevation
        hr_series = [l["average_heartrate"] for l in km_laps]
        pace_series = [3600.0 / l["average_speed"] for l in km_laps]  # sec/km
        elev_series = [l.get("total_elevation_gain", 0) or 0 for l in km_laps]

        n = len(km_laps)
        half = n // 2
        first_hr = sum(hr_series[:half]) / half
        last_hr = sum(hr_series[-half:]) / half
        first_pace = sum(pace_series[:half]) / half
        last_pace = sum(pace_series[-half:]) / half
        if first_hr <= 0 or first_pace <= 0:
            continue

        # Raw drifts (positive = HR rises / pace slows)
        hr_drift_pct = (last_hr - first_hr) / first_hr * 100
        # Pace drift: positive when pace slows (last_pace > first_pace)
        pace_drift_pct = (last_pace - first_pace) / first_pace * 100
        # Friel cardiac decoupling = pace_drift + hr_drift
        decoupling_pct = pace_drift_pct + hr_drift_pct

        # Per-km profile (rounded for display)
        splits = [
            {
                "km": i + 1,
                "hr": round(hr_series[i], 1),
                "pace_sec_km": round(pace_series[i]),
                "elev_m": round(elev_series[i]),
            }
            for i in range(n)
        ]

        raw_runs.append(
            {
                "id": rid,
                "date": str(date_v),
                "name": name,
                "distance_km": round(dist_m / 1000, 1) if dist_m else None,
                "elevation_m": int(dplus) if dplus else None,
                "duration_min": int(dur / 60) if dur else None,
                "avg_hr": int(avg_hr) if avg_hr else None,
                "avg_pace_sec_km": pace_sec,
                "hr_drift_pct": round(hr_drift_pct, 1),
                "pace_drift_pct": round(pace_drift_pct, 1),
                "decoupling_pct": round(decoupling_pct, 1),
                "splits": splits,
            }
        )

    # ---- Step 2 helpers: classify run type + score ----

    def _classify_run_type(r: dict) -> str:
        elev_per_km = (r["elevation_m"] or 0) / max(r["distance_km"] or 1, 1)
        pace = r["avg_pace_sec_km"] or 0
        dist = r["distance_km"] or 0
        if dist < 12 and pace < 360 and elev_per_km < 20:
            return "intensity"
        if elev_per_km > 30 and dist >= 15:
            return "trail_long"
        if elev_per_km > 30:
            return "trail_short"
        if dist >= 18:
            return "long_run"
        return "base"

    def _score_run(run_type: str, hr: float, residual: float | None) -> str:
        if run_type == "intensity":
            if hr < 5:
                return "excellent"
            if hr < 12:
                return "good" if (residual is None or residual < 8) else "moderate"
            if hr < 18:
                return "moderate"
            return "concerning"
        if run_type in ("trail_long", "trail_short"):
            if hr < 0:
                return "excellent"
            if hr < 5:
                return "excellent" if (residual is None or residual < 5) else "good"
            if hr < 10:
                return "good" if (residual is None or residual < 8) else "moderate"
            return "concerning"
        # base or long_run
        if hr < 0:
            return "excellent"
        if hr < 3:
            return "excellent" if (residual is None or residual < 5) else "good"
        if hr < 6:
            return "good" if (residual is None or residual < 8) else "moderate"
        if hr < 10:
            return "moderate"
        return "concerning"

    # ---- Step 2: fit baseline regression on athlete's own data ----
    baseline = None
    if len(raw_runs) >= 10:
        # Predictors: distance_km, elev_per_km, avg_pace_sec_km
        X = np.array(
            [
                [
                    r["distance_km"] or 0,
                    (r["elevation_m"] or 0) / max(r["distance_km"] or 1, 1),
                    r["avg_pace_sec_km"] or 0,
                ]
                for r in raw_runs
            ],
            dtype=float,
        )
        y = np.array([r["decoupling_pct"] for r in raw_runs], dtype=float)

        # Standardize for numerical stability
        X_mean = X.mean(axis=0)
        X_std = X.std(axis=0)
        X_std[X_std == 0] = 1.0
        X_norm = (X - X_mean) / X_std

        # Add intercept
        X_full = np.column_stack([np.ones(len(X_norm)), X_norm])
        # OLS via normal equations
        coeffs, *_ = np.linalg.lstsq(X_full, y, rcond=None)
        y_pred = X_full @ coeffs
        ss_res = float(np.sum((y - y_pred) ** 2))
        ss_tot = float(np.sum((y - y.mean()) ** 2))
        r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0

        # De-normalize coefficients for interpretability
        # y = c0 + c1 * (x1 - m1)/s1 + c2 * (x2 - m2)/s2 + c3 * (x3 - m3)/s3
        # Original-space: y = (c0 - c1*m1/s1 - c2*m2/s2 - c3*m3/s3)
        #                   + c1/s1 * x1 + c2/s2 * x2 + c3/s3 * x3
        orig_coeffs = [
            float(
                coeffs[0] - sum(coeffs[i + 1] * X_mean[i] / X_std[i] for i in range(3))
            ),
            float(coeffs[1] / X_std[0]),
            float(coeffs[2] / X_std[1]),
            float(coeffs[3] / X_std[2]),
        ]

        baseline = {
            "formula": "decoupling = b0 + b1*distance_km + b2*elev_per_km + b3*avg_pace_sec_km",
            "coefficients": {
                "intercept": round(orig_coeffs[0], 3),
                "distance_km": round(orig_coeffs[1], 3),
                "elev_per_km": round(orig_coeffs[2], 3),
                "avg_pace_sec_km": round(orig_coeffs[3], 3),
            },
            "r_squared": round(r_squared, 3),
            "n_samples": len(raw_runs),
        }

        # ---- Step 3: compute residual drift + classify run type + score ----
        for r in raw_runs:
            x = np.array(
                [
                    r["distance_km"] or 0,
                    (r["elevation_m"] or 0) / max(r["distance_km"] or 1, 1),
                    r["avg_pace_sec_km"] or 0,
                ],
                dtype=float,
            )
            expected = orig_coeffs[0] + sum(orig_coeffs[i + 1] * x[i] for i in range(3))
            residual = r["decoupling_pct"] - expected
            r["expected_decoupling_pct"] = round(expected, 1)
            r["drift_residual_pct"] = round(residual, 1)

            r["run_type"] = _classify_run_type(r)

            tags: list[str] = []
            if r["hr_drift_pct"] < 0:
                tags.append("negative_hr_drift")
            if r["pace_drift_pct"] > 15:
                tags.append("large_pace_slowdown")
            if r["decoupling_pct"] > 10:
                tags.append("high_coupling")
            if residual > 5:
                tags.append("worse_than_baseline")
            if residual < -5:
                tags.append("well_below_baseline")
            r["tags"] = tags

            r["drift_score"] = _score_run(r["run_type"], r["hr_drift_pct"], residual)

    else:
        # Not enough data for baseline — fall back to run-type-aware scoring
        for r in raw_runs:
            r["expected_decoupling_pct"] = None
            r["drift_residual_pct"] = None
            r["run_type"] = _classify_run_type(r)

            tags: list[str] = []
            if r["hr_drift_pct"] < 0:
                tags.append("negative_hr_drift")
            if r["pace_drift_pct"] > 15:
                tags.append("large_pace_slowdown")
            r["tags"] = tags

            r["drift_score"] = _score_run(r["run_type"], r["hr_drift_pct"], None)

    # ---- Step 4: bucket by effort class for context ----
    def effort_class(r: dict) -> str:
        d = r["distance_km"] or 0
        e = r["elevation_m"] or 0
        elev_per_km = e / max(d, 1)
        if d < 10:
            return "short"
        if d < 18 and elev_per_km < 30:
            return "moderate_flat"
        if d < 18 and elev_per_km >= 30:
            return "moderate_hilly"
        if d >= 18 and elev_per_km < 40:
            return "long_flat"
        if d >= 18 and elev_per_km < 80:
            return "long_hilly"
        return "long_mountain"

    buckets: dict[str, list[float]] = defaultdict(list)
    for r in raw_runs:
        buckets[effort_class(r)].append(r["decoupling_pct"])

    bucket_summary = {
        k: {
            "n": len(v),
            "avg_decoupling_pct": round(sum(v) / len(v), 1) if v else None,
            "best_decoupling_pct": round(min(v), 1) if v else None,
            "worst_decoupling_pct": round(max(v), 1) if v else None,
        }
        for k, v in sorted(buckets.items())
    }

    return {
        "runs": raw_runs,
        "count": len(raw_runs),
        "baseline": baseline,
        "effort_buckets": bucket_summary,
    }


@router.get("/cardiac-efficiency")
def get_cardiac_efficiency(
    period: str = Query("90d"),
):
    """Weekly cardiac efficiency trend for runs.

    Efficiency = avg_hr / speed_kmh.  Lower = more efficient heart.
    """
    days = _parse_period(period)
    start_date = date.today() - timedelta(days=days)

    con = connect(read_only=True)
    try:
        rows = con.execute(
            """
            SELECT DATE_TRUNC('week', date) as week,
                   avg_hr,
                   avg_pace_sec_km,
                   duration_sec
            FROM app.actual_sessions
            WHERE date >= ? AND user_id = 1
              AND sport IN ('run', 'trail_run', 'running')
              AND avg_hr IS NOT NULL
              AND avg_pace_sec_km IS NOT NULL
              AND avg_pace_sec_km > 0
            ORDER BY week ASC
            """,
            [start_date],
        ).fetchall()
    finally:
        con.close()

    if not rows:
        return {"data": []}

    # Group by week — weighted average by duration
    weeks: dict[str, dict] = defaultdict(
        lambda: {"hr_sum": 0.0, "speed_sum": 0.0, "dur_sum": 0, "n": 0}
    )
    for week_ts, hr, pace, dur in rows:
        week_str = str(week_ts.date()) if hasattr(week_ts, "date") else str(week_ts)
        w = weeks[week_str]
        weight = dur or 1
        speed_kmh = 3600.0 / pace  # convert sec/km to km/h
        w["hr_sum"] += hr * weight
        w["speed_sum"] += speed_kmh * weight
        w["dur_sum"] += weight
        w["n"] += 1

    result = []
    for week_str in sorted(weeks.keys()):
        w = weeks[week_str]
        avg_hr = w["hr_sum"] / w["dur_sum"]
        avg_speed = w["speed_sum"] / w["dur_sum"]
        efficiency = round(avg_hr / avg_speed, 1) if avg_speed > 0 else None
        avg_pace_sec = int(3600.0 / avg_speed) if avg_speed > 0 else None
        result.append(
            {
                "week": week_str,
                "efficiency": efficiency,
                "avg_hr": round(avg_hr, 1),
                "avg_pace": _format_pace(avg_pace_sec) if avg_pace_sec else None,
                "avg_pace_sec_km": avg_pace_sec,
                "n_runs": w["n"],
            }
        )

    return {"data": result}


@router.get("/hr-pace-scatter")
def get_hr_pace_scatter(
    period: str = Query("90d"),
):
    """Per-session HR, pace, elevation data for scatter plots."""
    days = _parse_period(period)
    start_date = date.today() - timedelta(days=days)

    con = connect(read_only=True)
    try:
        rows = con.execute(
            """
            SELECT date, sport, name,
                   avg_hr, max_hr,
                   avg_pace_sec_km,
                   ascent_m,
                   CASE WHEN distance_m IS NOT NULL THEN ROUND(distance_m / 1000.0, 1) ELSE NULL END as distance_km,
                   duration_sec
            FROM app.actual_sessions
            WHERE date >= ? AND user_id = 1
              AND avg_hr IS NOT NULL
              AND sport IN ('run', 'trail_run', 'running', 'walk', 'walking', 'hike')
            ORDER BY date ASC
            """,
            [start_date],
        ).fetchall()
    finally:
        con.close()

    sessions = []
    for r in rows:
        pace_display = None
        if r[5]:
            pace_display = f"{r[5] // 60}:{r[5] % 60:02d}"
        sessions.append(
            {
                "date": str(r[0]),
                "sport": r[1],
                "name": r[2],
                "avg_hr": r[3],
                "max_hr": r[4],
                "pace_sec_km": r[5],
                "pace_display": pace_display,
                "elevation_gain": r[6],
                "distance_km": float(r[7]) if r[7] is not None else None,
                "duration_sec": r[8],
            }
        )

    return {"sessions": sessions}
