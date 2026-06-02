#!/usr/bin/env python3
"""Full Strava history import — fetches ALL activities from 2023 onwards.

Each activity = 2 API calls (detail + zones), so we pause 60s every 45 activities
to respect Strava's 100 req/15min rate limit.

Estimated time: ~300 activities × 2 calls / 200 calls per 15min = ~22min
"""

import os
import sys
import time
import logging
from datetime import datetime

from arete.dataio.db import connect
from arete.strava.client import StravaClient
from arete.strava.models import strava_activity_to_actual_session
from arete.garmin.repository import GarminRepository

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("import_history")


def main() -> int:
    con = connect(read_only=False)
    client = StravaClient(
        os.environ["STRAVA_CLIENT_ID"],
        os.environ["STRAVA_CLIENT_SECRET"],
        os.environ["STRAVA_REDIRECT_URI"],
    )

    tokens = con.execute(
        "SELECT access_token, refresh_token, expires_at FROM app.strava_tokens WHERE user_id=1"
    ).fetchone()
    if not tokens:
        logger.error("No Strava tokens — connect first")
        return 1

    access_token, refresh_token, expires_at = tokens
    if StravaClient.needs_refresh(expires_at):
        logger.info("Refreshing access token…")
        new = client.refresh_token(refresh_token)
        con.execute(
            "UPDATE app.strava_tokens SET access_token=?, refresh_token=?, expires_at=? WHERE user_id=1",
            [new["access_token"], new["refresh_token"], new["expires_at"]],
        )
        access_token = new["access_token"]
        logger.info("  → new expires_at: %s", new["expires_at"])

    # Fetch all activities
    logger.info("Fetching all activities (no time filter)…")
    activities = client.fetch_activities(access_token)
    logger.info("  → %d activities returned by Strava", len(activities))

    # Dedup against DB
    existing_ids = {
        str(r[0])
        for r in con.execute(
            "SELECT garmin_activity_id FROM app.actual_sessions WHERE source='strava'"
        ).fetchall()
    }
    to_import = [a for a in activities if str(a.get("id", "")) not in existing_ids]
    logger.info(
        "  → %d new to import (already in DB: %d)", len(to_import), len(existing_ids)
    )

    if not to_import:
        logger.info("Nothing to import. Done.")
        return 0

    # Sort chronologically (oldest first) so the DB ends up in a sensible order
    to_import.sort(key=lambda a: a.get("start_date", ""))

    repo = GarminRepository()
    imported = 0
    skipped = 0
    errors: list[str] = []

    for idx, activity in enumerate(to_import, start=1):
        act_id = str(activity.get("id", ""))
        sport = activity.get("sport_type", activity.get("type", "?"))
        start = activity.get("start_date_local") or activity.get("start_date", "")
        date_short = start[:10] if start else "?"

        try:
            # Detail (laps, splits, best_efforts)
            detail = client.fetch_activity_detail(access_token, int(act_id))
            activity_data = detail if detail else activity

            # HR zones
            hr_zones = client.fetch_activity_zones(access_token, int(act_id))

            session = strava_activity_to_actual_session(
                activity_data, hr_zones=hr_zones
            )
            repo.create_actual_session(session)
            imported += 1

            dist_km = (activity.get("distance") or 0) / 1000
            logger.info(
                "  [%d/%d] %s %s %.1fkm  ✓",
                idx,
                len(to_import),
                date_short,
                sport,
                dist_km,
            )

            # Rate limit: pause every 45 imports (~90 API calls)
            if imported % 45 == 0:
                logger.info("  ⏸  Approaching rate limit, pausing 60s…")
                time.sleep(60)

        except Exception as exc:
            errors.append(f"{date_short} {act_id} ({sport}): {exc}")
            logger.error(
                "  [%d/%d] %s %s  ✗ %s", idx, len(to_import), date_short, sport, exc
            )

    logger.info("=" * 60)
    logger.info(
        "DONE: %d imported, %d skipped, %d errors", imported, skipped, len(errors)
    )
    if errors:
        logger.info("First 10 errors:")
        for e in errors[:10]:
            logger.info("  • %s", e)
    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(main())
