"""Load a training plan (JSON) into app.planned_sessions.

Usage:
    uv run python scripts/seed_plan.py data/plans/prog_2026_v3.json [--replace]

JSON: a list of {"date": "YYYY-MM-DD", "sport": "running", "session_type": "tempo",
"target_duration_min": 55, "target_distance_km": 5.0, "target_intensity": "hard",
"description": "..."}. Sessions get source="coach". With --replace, existing coach
sessions in the covered date range are deleted first (idempotent re-import).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from arete.garmin.models import PlannedSession, SessionType
from arete.garmin.repository import GarminRepository


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument(
        "--replace", action="store_true", help="drop coach sessions in range first"
    )
    args = parser.parse_args()

    items = json.loads(args.plan.read_text())
    if not items:
        print("empty plan")
        return 1
    dates = sorted(date.fromisoformat(i["date"]) for i in items)
    repo = GarminRepository()

    if args.replace:
        existing = repo.list_planned_sessions(
            start_date=dates[0], end_date=dates[-1], limit=10000
        )
        removed = 0
        for s in existing:
            if s.source == "coach" and s.id is not None:
                repo.delete_planned_session(s.id)
                removed += 1
        print(
            f"removed {removed} previous coach sessions between {dates[0]} and {dates[-1]}"
        )

    for item in items:
        repo.create_planned_session(
            PlannedSession(
                date=date.fromisoformat(item["date"]),
                sport=item.get("sport", "running"),
                session_type=SessionType(item.get("session_type", "endurance")),
                target_duration_min=item.get("target_duration_min"),
                target_distance_km=item.get("target_distance_km"),
                target_intensity=item.get("target_intensity"),
                description=item.get("description"),
                source="coach",
            )
        )
    print(f"created {len(items)} planned sessions ({dates[0]} -> {dates[-1]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
