#!/usr/bin/env python3
"""Full Strava history import — fetches ALL activities, with proper 429 backoff.

Each activity = 2 API calls (detail + zones).
Strava limit: 100 requests / 15 min, 2000 / day.

Strategy:
  - 1.5s sleep between calls (slow but safe)
  - 60s pause every 40 imports (~80 calls)
  - On 429: pause 5min, then retry the same activity

Resumable: skips activities already in DB (by garmin_activity_id).
"""

import logging
import os
import sys
import time

import httpx

from arete.dataio.db import connect
from arete.garmin.repository import GarminRepository
from arete.strava.client import StravaClient
from arete.strava.models import strava_activity_to_actual_session

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("import_history")


CALL_DELAY_SEC = 1.5  # sleep between API calls
BURST_LIMIT = 40  # imports per burst
BURST_PAUSE_SEC = 75  # pause between bursts (slightly more than 60 to be safe)
BACKOFF_429_SEC = 300  # 5 min on 429


def fetch_with_retry(client_fn, *args, **kwargs):
    """Call a Strava function with 429-aware backoff."""
    while True:
        try:
            return client_fn(*args, **kwargs)
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 429:
                logger.warning("429 hit, sleeping %ds…", BACKOFF_429_SEC)
                time.sleep(BACKOFF_429_SEC)
                continue
            raise


def fetch_all_activities(client, access_token: str) -> list[dict]:
    """Fetch all activities with 429-aware pagination."""
    import httpx as _httpx

    headers = {"Authorization": f"Bearer {access_token}"}
    all_acts: list[dict] = []
    page = 1
    per_page = 50
    while True:
        url = "https://www.strava.com/api/v3/athlete/activities"
        while True:
            resp = _httpx.get(
                url, headers=headers, params={"per_page": per_page, "page": page}
            )
            if resp.status_code == 429:
                logger.warning(
                    "429 on fetch_activities page %d, sleeping %ds…",
                    page,
                    BACKOFF_429_SEC,
                )
                time.sleep(BACKOFF_429_SEC)
                continue
            if resp.status_code != 200:
                logger.error("Strava API error: %s %s", resp.status_code, resp.text)
                return all_acts
            break
        batch = resp.json()
        if not batch:
            break
        all_acts.extend(batch)
        if len(batch) < per_page:
            break
        page += 1
    return all_acts


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

    logger.info("Fetching all activities…")
    activities = fetch_all_activities(client, access_token)
    logger.info("  → %d activities from Strava", len(activities))

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

    to_import.sort(key=lambda a: a.get("start_date", ""))
    repo = GarminRepository()
    imported = 0
    errors: list[str] = []

    for idx, activity in enumerate(to_import, start=1):
        act_id = str(activity.get("id", ""))
        sport = activity.get("sport_type", activity.get("type", "?"))
        start = activity.get("start_date_local") or activity.get("start_date", "")
        date_short = start[:10] if start else "?"

        try:
            time.sleep(CALL_DELAY_SEC)
            detail = fetch_with_retry(
                client.fetch_activity_detail, access_token, int(act_id)
            )
            time.sleep(CALL_DELAY_SEC)
            hr_zones = fetch_with_retry(
                client.fetch_activity_zones, access_token, int(act_id)
            )

            activity_data = detail if detail else activity
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

            if imported % BURST_LIMIT == 0:
                logger.info(
                    "  ⏸  Burst limit (%d), pausing %ds…", BURST_LIMIT, BURST_PAUSE_SEC
                )
                time.sleep(BURST_PAUSE_SEC)

        except Exception as exc:
            errors.append(f"{date_short} {act_id} ({sport}): {exc}")
            logger.error(
                "  [%d/%d] %s %s  ✗ %s", idx, len(to_import), date_short, sport, exc
            )

    logger.info("=" * 60)
    logger.info(
        "DONE: %d imported, %d errors (out of %d to import)",
        imported,
        len(errors),
        len(to_import),
    )
    if errors:
        logger.info("First 10 errors:")
        for e in errors[:10]:
            logger.info("  • %s", e)
    return 0 if not errors else 2


if __name__ == "__main__":
    sys.exit(main())
