"""Garmin daily metrics sync (HRV, sleep, body battery, stress).

Fetches one day of health metrics from Garmin Connect via garth and persists
to app.daily_metrics. Computes a daily readiness score from the signals.

Readiness formula (0-100):
  - 40% HRV vs personal baseline (higher = better recovery)
  - 30% Sleep score / duration
  - 30% Body battery high (peak charge)
  - Penalty: high stress avg or RHR > personal baseline

Note: Personal baselines for HRV/RHR are derived from a 14-day rolling average
in the same table. This module is the entry point; the readiness computation
is in `compute_readiness()` and can also be re-run retroactively.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import garth

from arete.dataio.db import connect

logger = logging.getLogger(__name__)


TOKENS_DIR = Path(os.environ.get("ARETE_GARMIN_TOKENS_DIR", "/app/data/garmin_tokens"))


# ---------- Token management ----------


def _ensure_authenticated() -> None:
    """Load saved tokens, raise if missing."""
    if not TOKENS_DIR.exists() or not any(TOKENS_DIR.iterdir()):
        raise FileNotFoundError(
            f"No Garmin tokens found at {TOKENS_DIR}. "
            "Run `uv run python scripts/garmin_login.py` first."
        )
    garth.resume(str(TOKENS_DIR))


# ---------- Per-day fetchers ----------


def _fetch_hrv(target_date: date) -> dict[str, Any]:
    """Fetch HRV summary for the given date (last_night + weekly_avg)."""
    try:
        hrv = garth.HRVData.get(target_date.isoformat())
    except Exception as e:
        logger.warning("HRV fetch failed for %s: %s", target_date, e)
        return {}
    if not hrv or not hrv.hrv_summary:
        return {}
    s = hrv.hrv_summary
    return {
        "hrv_last_night": getattr(s, "last_night_avg", None),
        "hrv_weekly_avg": getattr(s, "weekly_avg", None),
        "hrv_status": getattr(s, "status", None),
    }


def _fetch_sleep(target_date: date) -> dict[str, Any]:
    """Fetch sleep summary for the given date."""
    try:
        sleep = garth.SleepData.get(target_date.isoformat())
    except Exception as e:
        logger.warning("Sleep fetch failed for %s: %s", target_date, e)
        return {}
    if not sleep or not sleep.daily_sleep_dto:
        return {}
    dto = sleep.daily_sleep_dto
    score = getattr(dto.sleep_scores, "overall", None) if dto.sleep_scores else None
    return {
        "sleep_duration_sec": getattr(dto, "sleep_time_seconds", None),
        "sleep_score": getattr(score, "value", None) if score else None,
        "sleep_deep_sec": getattr(dto, "deep_sleep_seconds", None),
        "sleep_light_sec": getattr(dto, "light_sleep_seconds", None),
        "sleep_rem_sec": getattr(dto, "rem_sleep_seconds", None),
        "sleep_awake_sec": getattr(dto, "awake_sleep_seconds", None),
    }


def _fetch_body_battery(target_date: date) -> dict[str, Any]:
    """Fetch body battery charged/drained/high/low."""
    try:
        bb = garth.DailyBodyBatteryStress.get(target_date.isoformat())
    except Exception as e:
        logger.warning("BodyBattery fetch failed for %s: %s", target_date, e)
        return {}
    return {
        "body_battery_charged": getattr(bb, "body_battery_charged", None),
        "body_battery_drained": getattr(bb, "body_battery_drained", None),
        "body_battery_high": getattr(bb, "max_body_battery", None),
        "body_battery_low": getattr(bb, "min_body_battery", None),
        "stress_avg": getattr(bb, "avg_stress_level", None),
        "stress_max": getattr(bb, "max_stress_level", None),
    }


def _fetch_steps(target_date: date) -> dict[str, Any]:
    """Fetch steps + intensity minutes."""
    try:
        items = garth.DailySteps.list(target_date, 1)
    except Exception as e:
        logger.warning("Steps fetch failed for %s: %s", target_date, e)
        return {}
    if not items:
        return {}
    s = items[0]
    return {
        "steps": getattr(s, "total_steps", None),
    }


# ---------- Aggregation + persistence ----------


@dataclass
class DailySyncResult:
    date: date
    success: bool
    fields_synced: int
    error: str | None = None


def _gather_metrics(target_date: date) -> dict[str, Any]:
    """Fetch all signals for one day. Failures on individual signals are non-fatal."""
    metrics: dict[str, Any] = {"date": target_date, "source": "garmin"}
    metrics.update(_fetch_hrv(target_date))
    metrics.update(_fetch_sleep(target_date))
    metrics.update(_fetch_body_battery(target_date))
    metrics.update(_fetch_steps(target_date))
    metrics = {k: v for k, v in metrics.items() if v is not None}
    return metrics


def _upsert_daily_metrics(metrics: dict[str, Any]) -> None:
    """Insert or replace a single daily_metrics row."""
    con = connect()
    try:
        cols = [k for k in metrics.keys() if k != "date"]
        placeholders = ", ".join(["?"] * (len(cols) + 2))  # +2 for user_id, date
        col_list = ", ".join(["user_id", "date", *cols])
        update_set = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols)
        values = [1, metrics["date"], *[metrics.get(c) for c in cols]]
        con.execute(
            f"""
            INSERT INTO app.daily_metrics ({col_list})
            VALUES ({placeholders})
            ON CONFLICT (user_id, date) DO UPDATE SET {update_set}
            """,
            values,
        )
        con.commit()
    finally:
        con.close()


def sync_day(target_date: date) -> DailySyncResult:
    """Sync one day of Garmin health data."""
    try:
        _ensure_authenticated()
    except FileNotFoundError as e:
        return DailySyncResult(
            date=target_date, success=False, fields_synced=0, error=str(e)
        )
    try:
        metrics = _gather_metrics(target_date)
    except Exception as e:
        logger.exception("Failed to gather metrics for %s", target_date)
        return DailySyncResult(
            date=target_date, success=False, fields_synced=0, error=str(e)
        )
    try:
        _upsert_daily_metrics(metrics)
    except Exception as e:
        logger.exception("Failed to upsert metrics for %s", target_date)
        return DailySyncResult(
            date=target_date, success=False, fields_synced=0, error=str(e)
        )
    return DailySyncResult(
        date=target_date, success=True, fields_synced=len(metrics) - 1
    )  # -1 for 'date'


def sync_range(start: date, end: date) -> list[DailySyncResult]:
    """Sync a range of dates. Each day is one API call group (3-4 calls)."""
    results: list[DailySyncResult] = []
    cur = start
    while cur <= end:
        r = sync_day(cur)
        results.append(r)
        if r.success:
            logger.info("Synced %s (%d fields)", cur, r.fields_synced)
        else:
            logger.warning("Failed %s: %s", cur, r.error)
        cur += timedelta(days=1)
    return results
