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
from time import monotonic

from arete.config import config
from arete.dataio.db import db_connection
from arete.services.athlete_scope import athlete_scope, current_athlete_id

logger = logging.getLogger(__name__)

HEALTH_LOOKBACK_DAYS = 3
TICK_SECONDS = 300
STATE_FILENAME = "last_daily_sync.json"


#: Status of the most recent run, for ``GET /sync/status`` and the agent's
#: ``get_sync_status`` tool. Process-local and deliberately not persisted: it
#: answers "what happened on the run this process did", while the durable
#: "did today's run happen at all" lives in the JSON marker below.
_last_status: dict[int, dict[str, str]] = {}


def last_status() -> dict[str, str]:
    """Per-source status of the last sync this process ran ({} if none yet)."""
    return dict(_last_status.get(current_athlete_id(), {}))


def state_path() -> Path:
    """Where the last run is recorded (in the data directory)."""
    from arete.config import config

    return config.data_dir / STATE_FILENAME


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
    imported = 0  # new sessions from any source, for the notification
    synced_ids: list[int] = []  # Garmin's, for the coach's feedback

    from arete.garmin.client import GarminClient

    garmin = GarminClient()
    if garmin.has_tokens():
        from arete.garmin.health_sync import sync_range
        from arete.garmin.readiness import update_readiness_range
        from arete.garmin.sync import GarminSyncClient

        try:
            result = GarminSyncClient(client=garmin).sync_activities(download_fit=True)
            imported += result.activities_synced
            synced_ids = list(result.session_ids)
            status["garmin_activities"] = (
                f"{result.activities_synced} synced, {len(result.errors)} errors"
            )
        except Exception as e:  # noqa: BLE001 - background job must not die
            status["garmin_activities"] = f"failed: {e}"
        if synced_ids:  # before the feedback, which reads GAP and weather
            from arete.services.session_conditions import enrich_sessions

            conditions = enrich_sessions(synced_ids)
            status["conditions"] = (
                f"{conditions['terrain']} terrain, {conditions['weather']} weather"
            )
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

    # After the health data, before the briefing that explains it. Runs without
    # Garmin too: the readiness then comes from the load model.
    try:
        from arete.services.plan_adaptation import adapt_today

        decisions = adapt_today(respect_setting=True)
        kinds = ", ".join(sorted({d.decision for d in decisions})) or "none"
        status["plan"] = f"{len(decisions)} decisions ({kinds})"
    except Exception as e:  # noqa: BLE001 - background job must not die
        status["plan"] = f"failed: {e}"

    # After the decisions, so a session they changed goes out changed.
    if garmin.has_tokens():
        from arete.services.plan_adaptation import push_today

        status["garmin_push"] = push_today(garmin)

    from arete.api.strava import SyncRequest, _get_strava_tokens, sync

    if _get_strava_tokens():
        try:
            result = sync(SyncRequest(days=7))
            imported += int(result["imported"])
            status["strava"] = f"{result['imported']} imported"
        except Exception as e:  # noqa: BLE001
            status["strava"] = f"failed: {e}"
    else:
        status["strava"] = "not connected"

    # After every plan change of the run (adaptation, completed sessions).
    from arete.calendar import sync_training_plan
    from arete.services.calendar_plan import DAILY

    status["google_calendar"] = sync_training_plan(DAILY)

    # Before the briefing that reads the journal the feedback files; after the
    # bounded calendar run, so a slow model cannot starve it.
    if synced_ids:
        status["feedback"] = write_sync_feedback(synced_ids)

    if imported:
        from arete.services.notifications import notify

        notify("Arete", f"{imported} séance(s) importée(s)", "/log?tab=cardio")
    logger.info("Daily sync: %s", status)
    _last_status[current_athlete_id()] = dict(status)
    return status


def write_sync_feedback(session_ids: list[int]) -> str:
    """The coach's word on the sessions the sync imported. Never raises.

    One model request for the whole batch (``coaching.write_sync_feedback``);
    the rule text stands in for a failed or unusable answer.
    """
    try:
        from arete.coaching import write_sync_feedback as write

        outcome = write(session_ids)
    except Exception as e:  # noqa: BLE001 - background job must not die
        logger.warning("Sync feedback failed: %s", e)
        return f"failed: {e}"
    return f"{outcome['sessions']} sessions ({outcome['agent']} by the coach)"


def write_daily_briefing() -> str:
    """Have the coach write the day's briefing, after the sync that feeds it.

    Kept out of ``daily_sync`` so the sync's status dict stays about sources.
    Log-and-continue: the briefing must never be able to break the loop, and
    it has its own rule floor, so a failure here is already handled downstream.
    """
    from arete.coaching import generate_briefing
    from arete.services.briefing import briefing_enabled
    from arete.services.coaching_repository import BriefingRepository

    if not briefing_enabled():
        return "disabled"
    # A briefing the dashboard asked for before the sync is rewritten: it was
    # read off last night's missing data. One this job already wrote (a cron
    # that fires twice) is kept: the second run would pay for the same text.
    existing = BriefingRepository().get_for_day(date.today())
    if existing is not None and existing.trigger == "scheduler":
        return existing.source
    try:
        briefing = generate_briefing(trigger="scheduler")
    except Exception as e:  # noqa: BLE001 - background job must not die
        logger.warning("Daily briefing failed: %s", e)
        return f"failed: {e}"
    logger.info("Daily briefing: %s", briefing.source)
    from arete.services.notifications import first_sentence, notify

    notify("Briefing du coach", first_sentence(briefing.text), "/")
    return briefing.source


def write_weekly_review(today: date | None = None) -> str:
    """On Mondays, review the week that just ended. Never raises."""
    today = today or date.today()
    if today.weekday() != 0:
        return "not monday"
    try:
        from arete.coaching import generate_weekly_review
        from arete.services.notifications import first_sentence, notify

        review = generate_weekly_review()
        notify("Bilan de la semaine", first_sentence(review.text), "/planning")
    except Exception as e:  # noqa: BLE001 - background job must not die
        logger.warning("Weekly review failed: %s", e)
        return f"failed: {e}"
    return f"{review.source}, {len(review.proposals)} proposals"


MAX_SCHEDULED_ATHLETES = 5
SCHEDULE_DISPATCH_SECONDS = 240
SCHEDULE_LEASE_SECONDS = 900


def run_scheduled_batch() -> dict:
    """Claim a bounded batch; each athlete has a durable daily marker and lease.

    A failed/ambiguous run is not automatically replayed: its lease remains for
    investigation. Dispatch stops at the deadline and reports deferred work.
    """
    deadline = monotonic() + SCHEDULE_DISPATCH_SECONDS
    with db_connection() as con:
        rows = con.execute(
            "SELECT id FROM app.athletes WHERE deleted_at IS NULL "
            "AND (last_sync_at IS NULL OR CAST(last_sync_at AS DATE)<current_date) "
            "AND sync_lease_until IS NULL ORDER BY last_sync_at NULLS FIRST,id LIMIT ?",
            [MAX_SCHEDULED_ATHLETES + 1],
        ).fetchall()
    outcomes: dict[str, dict] = {}
    deferred = len(rows) > MAX_SCHEDULED_ATHLETES
    for (athlete_id,) in rows[:MAX_SCHEDULED_ATHLETES]:
        if monotonic() >= deadline:
            deferred = True
            break
        with db_connection() as con:
            claimed = con.execute(
                "UPDATE app.athletes SET sync_lease_until=current_timestamp + ? * INTERVAL '1 second' "
                "WHERE id=? AND deleted_at IS NULL AND sync_lease_until IS NULL "
                "AND (last_sync_at IS NULL OR CAST(last_sync_at AS DATE)<current_date) RETURNING id",
                [SCHEDULE_LEASE_SECONDS, athlete_id],
            ).fetchone()
        if not claimed:
            continue
        with athlete_scope(athlete_id):
            from arete.dataio import mirror

            try:
                if config.is_remote_db:
                    mirror.hydrate()
                status = daily_sync()
                status["briefing"] = write_daily_briefing()
                status["review"] = write_weekly_review()
                record_run(datetime.now())
                if config.is_remote_db:
                    mirror.flush()
                with db_connection() as con:
                    con.execute(
                        "UPDATE app.athletes SET last_sync_at=current_timestamp,sync_lease_until=NULL WHERE id=?",
                        [athlete_id],
                    )
                outcomes[str(athlete_id)] = status
            except Exception:
                logger.exception(
                    "Scheduled work failed for athlete %s; lease retained", athlete_id
                )
                outcomes[str(athlete_id)] = {
                    "status": "failed; manual recovery required"
                }
    return {"athletes": outcomes, "deferred": deferred}


async def run_forever(hour: int, tick_seconds: int = TICK_SECONDS) -> None:
    from anyio import to_thread

    logger.info(
        "Automatic sync armed for %02d:00, dispatch every %ds", hour, tick_seconds
    )
    # This task intentionally lives as long as the server; each dispatch is bounded.
    while True:
        if datetime.now().hour >= hour:
            try:
                await to_thread.run_sync(run_scheduled_batch)
            except Exception:
                logger.exception(
                    "Scheduled dispatch failed; next tick will check unclaimed work"
                )
        await asyncio.sleep(tick_seconds)


def start() -> asyncio.Task[None] | None:
    """Start the loop if ARETE_AUTO_SYNC_HOUR is set; returns the task."""
    hour = config.auto_sync_hour
    if hour is None:
        logger.info("Automatic sync disabled (ARETE_AUTO_SYNC_HOUR unset)")
        return None
    return asyncio.create_task(run_forever(hour), name="arete-daily-sync")
