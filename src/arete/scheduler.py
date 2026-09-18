"""Daily background sync (Garmin activities + health, Strava) inside the API.

Enabled by ``ARETE_AUTO_SYNC_HOUR`` (local hour). No extra dependency: an
asyncio task sleeps until the next occurrence and runs the blocking syncs in a
worker thread. Failures are logged and never stop the loop.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import date, datetime, timedelta

from arete.config import config

logger = logging.getLogger(__name__)

HEALTH_LOOKBACK_DAYS = 3


def seconds_until(hour: int, now: datetime) -> float:
    """Seconds from ``now`` to the next ``hour``:00 (today if still ahead)."""
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return (target - now).total_seconds()


def daily_sync() -> dict[str, str]:
    """Run every configured sync once. Returns a short status per source."""
    status: dict[str, str] = {}

    from arete.garmin.client import GarminClient

    garmin = GarminClient()
    if garmin.has_tokens():
        from arete.garmin.health_sync import sync_range
        from arete.garmin.readiness import update_readiness_range
        from arete.garmin.sync import GarminSyncClient

        try:
            result = GarminSyncClient(client=garmin).sync_activities(download_fit=True)
            status["garmin_activities"] = (
                f"{result.activities_synced} synced, {len(result.errors)} errors"
            )
        except Exception as e:  # noqa: BLE001 - background job must not die
            status["garmin_activities"] = f"failed: {e}"
        try:
            end = date.today()
            start = end - timedelta(days=HEALTH_LOOKBACK_DAYS)
            days = sync_range(start, end)
            update_readiness_range(start, end)
            status["garmin_health"] = f"{sum(1 for d in days if d.success)} days"
        except Exception as e:  # noqa: BLE001
            status["garmin_health"] = f"failed: {e}"
    else:
        status["garmin"] = "no tokens"

    from arete.api.strava import SyncRequest, _get_strava_tokens, sync

    if _get_strava_tokens():
        try:
            result = sync(SyncRequest(days=7))
            status["strava"] = f"{result['imported']} imported"
        except Exception as e:  # noqa: BLE001
            status["strava"] = f"failed: {e}"
    else:
        status["strava"] = "not connected"

    logger.info("Daily sync: %s", status)
    return status


async def run_forever(hour: int) -> None:
    while True:
        delay = seconds_until(hour, datetime.now())
        logger.info("Next automatic sync in %.0f min", delay / 60)
        await asyncio.sleep(delay)
        await asyncio.to_thread(daily_sync)


def start() -> asyncio.Task[None] | None:
    """Start the loop if ARETE_AUTO_SYNC_HOUR is set; returns the task."""
    hour = config.auto_sync_hour
    if hour is None:
        logger.info("Automatic sync disabled (ARETE_AUTO_SYNC_HOUR unset)")
        return None
    return asyncio.create_task(run_forever(hour), name="arete-daily-sync")
