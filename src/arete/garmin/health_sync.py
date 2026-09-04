"""Garmin daily metrics sync (HRV, sleep, body battery, stress).

Fetches one day of health metrics from Garmin Connect and persists
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
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from arete.dataio.db import connect
from arete.garmin.client import GarminAuthError, GarminClient

logger = logging.getLogger(__name__)


# ---------- Per-day fetchers (raw Garmin JSON -> daily_metrics columns) ----------


def _fetch_hrv(client: GarminClient, target_date: date) -> dict[str, Any]:
    try:
        data = client.hrv(target_date) or {}
    except Exception as e:
        logger.warning("HRV fetch failed for %s: %s", target_date, e)
        return {}
    summary = data.get("hrvSummary") or {}
    return {
        "hrv_last_night": summary.get("lastNightAvg"),
        "hrv_weekly_avg": summary.get("weeklyAvg"),
        "hrv_status": summary.get("status"),
    }


def _fetch_sleep(client: GarminClient, target_date: date) -> dict[str, Any]:
    try:
        data = client.sleep(target_date) or {}
    except Exception as e:
        logger.warning("Sleep fetch failed for %s: %s", target_date, e)
        return {}
    dto = data.get("dailySleepDTO") or {}
    if not dto.get("id"):
        return {}
    score = (dto.get("sleepScores") or {}).get("overall") or {}
    return {
        "sleep_duration_sec": dto.get("sleepTimeSeconds"),
        "sleep_score": score.get("value"),
        "sleep_deep_sec": dto.get("deepSleepSeconds"),
        "sleep_light_sec": dto.get("lightSleepSeconds"),
        "sleep_rem_sec": dto.get("remSleepSeconds"),
        "sleep_awake_sec": dto.get("awakeSleepSeconds"),
    }


def _fetch_stress(client: GarminClient, target_date: date) -> dict[str, Any]:
    try:
        data = client.stress(target_date) or {}
    except Exception as e:
        logger.warning("Stress fetch failed for %s: %s", target_date, e)
        return {}
    return {
        "stress_avg": data.get("avgStressLevel"),
        "stress_max": data.get("maxStressLevel"),
    }


def _fetch_body_battery(client: GarminClient, target_date: date) -> dict[str, Any]:
    try:
        days = client.body_battery(target_date)
    except Exception as e:
        logger.warning("BodyBattery fetch failed for %s: %s", target_date, e)
        return {}
    if not days:
        return {}
    day = days[0]
    values = [
        v[1]
        for v in (day.get("bodyBatteryValuesArray") or [])
        if isinstance(v, list | tuple) and len(v) > 1 and v[1] is not None
    ]
    return {
        "body_battery_charged": day.get("charged"),
        "body_battery_drained": day.get("drained"),
        "body_battery_high": max(values) if values else None,
        "body_battery_low": min(values) if values else None,
    }


def _fetch_steps(client: GarminClient, target_date: date) -> dict[str, Any]:
    try:
        items = client.steps(target_date)
    except Exception as e:
        logger.warning("Steps fetch failed for %s: %s", target_date, e)
        return {}
    if not items:
        return {}
    return {"steps": items[0].get("totalSteps")}


def _fetch_resting_hr(client: GarminClient, target_date: date) -> dict[str, Any]:
    try:
        data = client.resting_hr(target_date) or {}
    except Exception as e:
        logger.warning("Resting HR fetch failed for %s: %s", target_date, e)
        return {}
    metrics = (data.get("allMetrics") or {}).get("metricsMap") or {}
    entries = metrics.get("WELLNESS_RESTING_HEART_RATE") or []
    value = (
        entries[0].get("value") if entries and isinstance(entries[0], dict) else None
    )
    return {"resting_hr": value}


# ---------- Aggregation + persistence ----------


@dataclass
class DailySyncResult:
    date: date
    success: bool
    fields_synced: int
    error: str | None = None


def _gather_metrics(client: GarminClient, target_date: date) -> dict[str, Any]:
    """Fetch all signals for one day. Failures on individual signals are non-fatal."""
    metrics: dict[str, Any] = {"date": target_date, "source": "garmin"}
    for fetch in (
        _fetch_hrv,
        _fetch_sleep,
        _fetch_stress,
        _fetch_body_battery,
        _fetch_steps,
        _fetch_resting_hr,
    ):
        metrics.update(fetch(client, target_date))
    return {k: v for k, v in metrics.items() if v is not None}


def _upsert_daily_metrics(metrics: dict[str, Any]) -> None:
    """Insert or replace a single daily_metrics row."""
    con = connect()
    try:
        cols = [k for k in metrics if k != "date"]
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


def sync_day(target_date: date, client: GarminClient | None = None) -> DailySyncResult:
    """Sync one day of Garmin health data."""
    client = client or GarminClient()
    try:
        client.connect()
    except GarminAuthError as e:
        return DailySyncResult(
            date=target_date, success=False, fields_synced=0, error=str(e)
        )
    try:
        metrics = _gather_metrics(client, target_date)
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
    """Sync a range of dates with one authenticated session (about 6 calls per day)."""
    client = GarminClient()
    results: list[DailySyncResult] = []
    cur = start
    while cur <= end:
        r = sync_day(cur, client)
        results.append(r)
        if r.success:
            logger.info("Synced %s (%d fields)", cur, r.fields_synced)
        else:
            logger.warning("Failed %s: %s", cur, r.error)
        cur += timedelta(days=1)
    return results
