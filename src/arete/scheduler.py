"""Daily background sync (Garmin activities + health, Strava) inside the API.

Enabled by ``ARETE_AUTO_SYNC_HOUR`` (local hour). No extra dependency: an
asyncio task wakes up every few minutes, compares the wall clock to the
scheduled hour and runs the blocking syncs in a worker thread when the day's
run is still owed. Short ticks on purpose: a laptop that sleeps freezes the
container's monotonic clock, and a single long sleep would silently skip a day.
The last run is written next to the database, so a restart does not re-run a
sync that already happened — and does run the one that was missed.
Failures are logged and never stop the loop.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import date, datetime, timedelta
from pathlib import Path

from arete.config import config

logger = logging.getLogger(__name__)

HEALTH_LOOKBACK_DAYS = 3
TICK_SECONDS = 300
STATE_FILENAME = "last_daily_sync.json"


#: Status of the most recent run, for ``GET /sync/status`` and the agent's
#: ``get_sync_status`` tool. Process-local and deliberately not persisted: it
#: answers "what happened on the run this process did", while the durable
#: "did today's run happen at all" lives in the JSON marker below.
_last_status: dict[str, str] = {}


def last_status() -> dict[str, str]:
    """Per-source status of the last sync this process ran ({} if none yet)."""
    return dict(_last_status)


def state_path() -> Path:
    """Where the last run is recorded (beside the DuckDB file)."""
    from arete.dataio.db import get_db_path

    return get_db_path().parent / STATE_FILENAME


def last_run_date() -> date | None:
    """Day of the last completed run, None when it never ran."""
    path = state_path()
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text())
        return datetime.fromisoformat(payload["ran_at"]).date()
    except (ValueError, KeyError, OSError):
        logger.warning("Unreadable sync state at %s, treating as never run", path)
        return None


def record_run(when: datetime) -> None:
    path = state_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"ran_at": when.isoformat()}))
    except OSError as e:  # the sync itself succeeded; only the marker failed
        logger.warning("Could not record the sync state: %s", e)


def is_due(hour: int, now: datetime, last_run: date | None) -> bool:
    """True when the scheduled hour has passed and today's run is still owed."""
    if now.hour < hour:
        return False
    return last_run is None or last_run < now.date()


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
    _last_status.clear()
    _last_status.update(status)
    return status


def write_daily_briefing() -> str:
    """Have the coach write the day's briefing, after the sync that feeds it.

    Kept out of ``daily_sync`` so the sync's status dict stays about sources.
    Log-and-continue: the briefing must never be able to break the loop, and
    it has its own rule floor, so a failure here is already handled downstream.
    """
    from arete.coach.briefing import briefing_enabled, generate_briefing

    if not briefing_enabled():
        return "disabled"
    try:
        briefing = generate_briefing(trigger="scheduler")
    except Exception as e:  # noqa: BLE001 - background job must not die
        logger.warning("Daily briefing failed: %s", e)
        return f"failed: {e}"
    logger.info("Daily briefing: %s", briefing.source)
    return briefing.source


async def run_forever(hour: int, tick_seconds: int = TICK_SECONDS) -> None:
    logger.info(
        "Automatic sync armed for %02d:00 local, checked every %d min (last run: %s)",
        hour,
        tick_seconds // 60,
        last_run_date() or "never",
    )
    while True:
        now = datetime.now()
        if is_due(hour, now, last_run_date()):
            await asyncio.to_thread(daily_sync)
            record_run(datetime.now())
            # After the sync, never before: the briefing reads the data the
            # sync just landed.
            await asyncio.to_thread(write_daily_briefing)
        await asyncio.sleep(tick_seconds)


def start() -> asyncio.Task[None] | None:
    """Start the loop if ARETE_AUTO_SYNC_HOUR is set; returns the task."""
    hour = config.auto_sync_hour
    if hour is None:
        logger.info("Automatic sync disabled (ARETE_AUTO_SYNC_HOUR unset)")
        return None
    return asyncio.create_task(run_forever(hour), name="arete-daily-sync")
