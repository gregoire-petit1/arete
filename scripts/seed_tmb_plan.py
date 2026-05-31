#!/usr/bin/env python3
"""Inject TMB training plan sessions into Arete via /garmin/planned.

Locations: Paris only — Montmartre (D+), Quais de Seine (flat), Buttes Chaumont (mixed).
TMB dates: 8-9-10 July 2026.
"""

import urllib.request, urllib.error, json, sys


def post(url, body):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


API = "http://localhost:8000"

# (date, sport, session_type, duration_min, distance_km, intensity, hr_zone, description)
PLAN = [
    # S17 — Spec Block 1
    (
        "2026-06-02",
        "running",
        "endurance",
        60,
        10.0,
        "easy",
        "Z2",
        "Easy Quais de Seine + 6x30s hill strides Montmartre",
    ),
    (
        "2026-06-03",
        "strength",
        "strength",
        45,
        None,
        "moderate",
        None,
        "Upper light, no legs",
    ),
    (
        "2026-06-04",
        "running",
        "tempo",
        75,
        12.0,
        "moderate",
        "Z3",
        "Hilly tempo Buttes Chaumont: 8 tours + finish",
    ),
    (
        "2026-06-06",
        "running",
        "long_run",
        180,
        25.0,
        "moderate",
        "Z2",
        "Long 1 D+: 10x Butte Montmartre (D+800m) + Quais Seine",
    ),
    (
        "2026-06-07",
        "running",
        "long_run",
        180,
        22.0,
        "easy",
        "Z2",
        "Long 2 endurance: Quais Seine + Buttes Chaumont 5 tours, HR<150",
    ),
    # S18 — Active Recovery
    (
        "2026-06-09",
        "running",
        "recovery",
        45,
        8.0,
        "easy",
        "Z1",
        "Recovery: Quais Seine flat very slow",
    ),
    (
        "2026-06-10",
        "strength",
        "strength",
        45,
        None,
        "moderate",
        None,
        "Upper + 15min calves/ankles",
    ),
    (
        "2026-06-11",
        "running",
        "tempo",
        60,
        10.0,
        "moderate",
        "Z3",
        "Short tempo Quais Seine: 4x3min threshold",
    ),
    (
        "2026-06-13",
        "running",
        "endurance",
        105,
        15.0,
        "moderate",
        "Z2",
        "Medium hilly: Buttes Chaumont 8 tours + boucle",
    ),
    (
        "2026-06-14",
        "running",
        "recovery",
        60,
        10.0,
        "easy",
        "Z1",
        "Easy Quais Seine, fluid legs",
    ),
    # S19 — Spec Block 2 PEAK
    (
        "2026-06-16",
        "running",
        "endurance",
        60,
        10.0,
        "moderate",
        "Z2",
        "Montmartre DESCENT focus 6 reps (eccentric quads)",
    ),
    (
        "2026-06-17",
        "strength",
        "strength",
        45,
        None,
        "moderate",
        None,
        "Upper light + core",
    ),
    (
        "2026-06-18",
        "running",
        "tempo",
        90,
        13.0,
        "moderate",
        "Z3",
        "Long tempo: Buttes Chaumont 10 tours soutenu",
    ),
    (
        "2026-06-20",
        "running",
        "long_run",
        240,
        30.0,
        "moderate",
        "Z2",
        "TMB DRESS REHEARSAL: 14x Montmartre D+1100m, FULL PACK + nutrition + TMB shoes",
    ),
    (
        "2026-06-21",
        "running",
        "long_run",
        180,
        22.0,
        "easy",
        "Z2",
        "Back-to-back: Quais Seine + Buttes Chaumont 6 tours, SAME PACK, very slow",
    ),
    # S20 — Discharge
    (
        "2026-06-23",
        "running",
        "recovery",
        45,
        7.0,
        "easy",
        "Z1",
        "Easy Quais Seine + 6x100m fluid strides",
    ),
    (
        "2026-06-24",
        "strength",
        "strength",
        30,
        None,
        "easy",
        None,
        "Very light upper, no legs",
    ),
    (
        "2026-06-25",
        "running",
        "tempo",
        50,
        8.0,
        "moderate",
        "Z3",
        "Short tempo Quais Seine: 3x5min marathon pace",
    ),
    (
        "2026-06-27",
        "running",
        "endurance",
        105,
        14.0,
        "moderate",
        "Z2",
        "Medium hilly: Montmartre 6 reps + Buttes 3 tours",
    ),
    (
        "2026-06-28",
        "running",
        "recovery",
        60,
        9.0,
        "easy",
        "Z1",
        "Easy Quais Seine flat",
    ),
    # S21 — Activation (TMB starts Tue 8/7, so this week ends Sun 5/7, then travel)
    (
        "2026-06-29",
        "running",
        "recovery",
        30,
        5.0,
        "easy",
        "Z1",
        "Very short easy Quais Seine",
    ),
    (
        "2026-07-01",
        "running",
        "tempo",
        40,
        7.0,
        "moderate",
        "Z2",
        "Quais Seine + 4x1min tempo",
    ),
    (
        "2026-07-03",
        "running",
        "recovery",
        30,
        5.0,
        "easy",
        "Z1",
        "Activation + 4x20s strides",
    ),
    (
        "2026-07-05",
        "running",
        "recovery",
        30,
        4.0,
        "easy",
        "Z1",
        "Last easy run before travel",
    ),
    (
        "2026-07-06",
        "running",
        "recovery",
        40,
        5.0,
        "easy",
        "Z2",
        "Recon Chamonix on arrival: light elevation, feel altitude",
    ),
    # TMB — 8-9-10 July
    (
        "2026-07-08",
        "running",
        "race",
        600,
        55.0,
        "hard",
        "Z2",
        "TMB Day 1 - France/Italy",
    ),
    (
        "2026-07-09",
        "running",
        "race",
        600,
        60.0,
        "hard",
        "Z2",
        "TMB Day 2 - Italy/Switzerland",
    ),
    (
        "2026-07-10",
        "running",
        "race",
        600,
        55.0,
        "hard",
        "Z2",
        "TMB Day 3 - Switzerland/France",
    ),
]

ok, fail = 0, 0
for entry in PLAN:
    date, sport, stype, dur, dist, intens, hr, desc = entry
    body = {
        "date": date,
        "sport": sport,
        "session_type": stype,
        "target_duration_min": dur,
        "target_distance_km": dist,
        "target_intensity": intens,
        "target_hr_zone": hr,
        "description": desc,
        "source": "coach",
    }
    code, text = post(f"{API}/garmin/planned", body)
    if code in (200, 201):
        ok += 1
        print(f"  OK   {date} {sport:8} {stype:10} {desc[:55]}")
    else:
        fail += 1
        print(f"  FAIL {date} {code}: {text[:200]}")

print(f"\nDone: {ok} created, {fail} failed (total {len(PLAN)})")
sys.exit(0 if fail == 0 else 1)
