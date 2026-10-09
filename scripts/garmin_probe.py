"""Print what Garmin Connect actually answers, read-only, before trusting a mapping.

Arete maps Garmin JSON it could not observe when the code was written: the
Training Readiness / status / VO2max / race-prediction / endurance / hill
payloads, and the structured-workout payload the watch push sends. Run this
once against your account and compare.

Usage:
    uv run python scripts/garmin_probe.py                 # today's metrics
    uv run python scripts/garmin_probe.py --date 2026-10-08
    uv run python scripts/garmin_probe.py --workout 123456789
    uv run python scripts/garmin_probe.py --save tests/data/garmin

``--workout`` prints a workout created by hand in Garmin Connect (web: Training >
Workouts; its id is in the URL). Build one with a 10' warm-up without target,
3 x (3' at a custom HR range / 2' recovery), 1 km at a pace range and a
cool-down: its stepType / endCondition / targetType ids are the reference for
``arete.garmin.workouts``. ``--save`` writes each payload as JSON, with the
display name and ids that identify the account replaced.

Only GET requests: nothing is written to Garmin.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

from arete.garmin.client import GarminClient

_PRIVATE_KEYS = {"userProfilePK", "userProfileId", "ownerId", "displayName", "deviceId"}


def _scrub(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: ("<redacted>" if k in _PRIVATE_KEYS else _scrub(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [_scrub(v) for v in value]
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--date", type=date.fromisoformat, default=date.today())
    parser.add_argument("--workout", help="id of a workout to print")
    parser.add_argument("--save", type=Path, help="directory for the JSON payloads")
    args = parser.parse_args()

    client = GarminClient()
    day: date = args.date
    reads = {
        "training_readiness": lambda: client.training_readiness(day),
        "training_status": lambda: client.training_status(day),
        "max_metrics": lambda: client.max_metrics(day),
        "race_predictions": client.race_predictions,
        "endurance_score": lambda: client.endurance_score(day),
        "hill_score": lambda: client.hill_score(day),
    }
    if args.workout:
        reads["workout_reference"] = lambda: client.connect().get_workout_by_id(
            args.workout
        )

    for name, read in reads.items():
        try:
            payload = read()
        except Exception as e:  # noqa: BLE001 - a probe reports, it does not stop
            print(f"== {name}: FAILED {type(e).__name__}: {e}")
            continue
        print(f"== {name}")
        print(json.dumps(payload, indent=2, ensure_ascii=False, default=str)[:4000])
        if args.save:
            args.save.mkdir(parents=True, exist_ok=True)
            (args.save / f"{name}.json").write_text(
                json.dumps(_scrub(payload), indent=2, ensure_ascii=False, default=str)
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
