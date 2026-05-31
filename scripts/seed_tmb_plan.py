#!/usr/bin/env python3
"""Inject TMB training plan sessions into Arete via /garmin/planned."""

import urllib.request, json, sys


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
        "Easy Yvette flat + 6x30s hill strides",
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
        "Hilly tempo, Troche stairs x4",
    ),
    (
        "2026-06-06",
        "running",
        "long_run",
        180,
        25.0,
        "moderate",
        "Z2",
        "Long 1 hilly: 10x Butte Montmartre (D+800m)",
    ),
    (
        "2026-06-07",
        "running",
        "long_run",
        180,
        24.0,
        "easy",
        "Z2",
        "Long 2 endurance: Chevreuse D+700m, slow (HR<150)",
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
        "Recovery run, flat, very slow",
    ),
    (
        "2026-06-10",
        "strength",
        "strength",
        45,
        None,
        "moderate",
        None,
        "Upper + 15min calves/ankles work",
    ),
    (
        "2026-06-11",
        "running",
        "tempo",
        60,
        10.0,
        "moderate",
        "Z3",
        "Short tempo: 4x3min threshold",
    ),
    (
        "2026-06-13",
        "running",
        "endurance",
        105,
        15.0,
        "moderate",
        "Z2",
        "Medium hilly Chevreuse, D+400m",
    ),
    (
        "2026-06-14",
        "running",
        "recovery",
        60,
        10.0,
        "easy",
        "Z1",
        "Easy flat, fluid legs",
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
        "Run + Montmartre DESCENT focus (eccentric quads)",
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
        "Long hilly tempo: Troche x6",
    ),
    (
        "2026-06-20",
        "running",
        "long_run",
        240,
        30.0,
        "moderate",
        "Z2",
        "TMB DRESS REHEARSAL: 13x Montmartre D+1100m, FULL PACK + nutrition + TMB shoes",
    ),
    (
        "2026-06-21",
        "running",
        "long_run",
        180,
        22.0,
        "easy",
        "Z2",
        "Back-to-back: Chevreuse D+700m, very slow, SAME PACK",
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
        "Easy + 6x100m fluid strides",
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
        "Short tempo: 3x5min marathon pace",
    ),
    (
        "2026-06-27",
        "running",
        "endurance",
        105,
        14.0,
        "moderate",
        "Z2",
        "Medium hilly Chevreuse D+500m",
    ),
    ("2026-06-28", "running", "recovery", 60, 9.0, "easy", "Z1", "Easy flat"),
    # S21 — Activation
    ("2026-06-29", "running", "recovery", 30, 5.0, "easy", "Z1", "Very short easy"),
    ("2026-07-01", "running", "tempo", 40, 7.0, "moderate", "Z2", "Run + 4x1min tempo"),
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
        40,
        5.0,
        "easy",
        "Z2",
        "Recon Chamonix, light elevation, feel altitude",
    ),
    # TMB
    (
        "2026-07-07",
        "running",
        "race",
        600,
        55.0,
        "hard",
        "Z2",
        "TMB Day 1 - France/Italy",
    ),
    (
        "2026-07-08",
        "running",
        "race",
        600,
        60.0,
        "hard",
        "Z2",
        "TMB Day 2 - Italy/Switzerland",
    ),
    (
        "2026-07-09",
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
    r_code, r_text = post(f"{API}/garmin/planned", body)
    if r_code in (200, 201):
        ok += 1
        print(f"  OK  {date} {sport:8} {stype:10} {desc[:50]}")
    else:
        fail += 1
        print(f"  FAIL {date} {r_code}: {r_text[:200]}")

print(f"\nDone: {ok} created, {fail} failed (total {len(PLAN)})")
sys.exit(0 if fail == 0 else 1)
