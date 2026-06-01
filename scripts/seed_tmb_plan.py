#!/usr/bin/env python3
"""Re-seed TMB plan with geographically accurate session descriptions.

Montmartre circuit (Abbesses → Ravignan escaliers → de la Mire escaliers
→ Lepic → Place JB Clément → Norvins → Saules escaliers ↓ → Caulaincourt
→ Saules escaliers ↑ → Marcadet):
  - 1 rep (A/R) ≈ 100m D+
  - 3 reps = 300m D+  |  4 reps = 400m D+  |  5 reps = 500m D+
  - 7 reps = 700m D+  |  8 reps = 800m D+  |  11 reps = 1100m D+
  - Each rep includes stairs DOWN (Saules ↓) = eccentric quad work built-in

Flat routes from 128 rue de Turenne:
  - Canal Saint-Martin (0.7km north, ultra flat) → récup/easy
  - Quais de Seine / Île de la Cité (1.4km south, flat) → tempo plat / long flat
  - Approach to Montmartre base (Pigalle/Abbesses): ~3km via Turbigo/Pigalle

Session structure for Montmartre runs:
  Turenne → Abbesses (~3km warm-up) + N reps + retour (~3km cool-down)
"""

import urllib.request, urllib.error, json, sys


def delete(url):
    req = urllib.request.Request(url, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


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

# ── Step 1: delete existing coach sessions ────────────────────────────────────
import urllib.request as ur

req = ur.Request(f"{API}/garmin/planned")
with ur.urlopen(req) as r:
    data = json.loads(r.read())
sessions = data if isinstance(data, list) else data.get("sessions", [])
to_delete = [
    s["id"]
    for s in sessions
    if s.get("source") == "coach" and s.get("date", "") >= "2026-06-01"
]
print(f"Deleting {len(to_delete)} existing coach sessions…")
for sid in to_delete:
    status = delete(f"{API}/garmin/planned/{sid}")
    print(f"  DELETE {sid} → {status}")

# ── Step 2: re-create with correct descriptions ───────────────────────────────
# (date, sport, session_type, duration_min, distance_km, intensity, hr_zone, description)
PLAN = [
    # ── S17 (1–7 juin) — Bloc spécifique 1 ──────────────────────────────────
    # Lun 01/06 : OFF (récup S16)
    (
        "2026-06-02",
        "running",
        "endurance",
        60,
        10.0,
        "easy",
        "Z2",
        "Easy + strides: Turenne → Canal St-Martin aller-retour, 6×30s accélérations fin",
    ),
    (
        "2026-06-03",
        "strength",
        "strength",
        45,
        None,
        "moderate",
        None,
        "Upper light — pas de jambes",
    ),
    (
        "2026-06-04",
        "running",
        "tempo",
        75,
        12.0,
        "moderate",
        "Z3",
        "Tempo vallonné: Turenne → Abbesses (warm-up 3km) + 3 reps Montmartre soutenu (D+300m) + retour",
    ),
    # Ven 05/06 : OFF (veille bloc)
    (
        "2026-06-06",
        "running",
        "long_run",
        180,
        22.0,
        "moderate",
        "Z2",
        "Long 1 D+: Turenne → Abbesses + 8 reps Montmartre (D+800m) + retour — 1er back-to-back",
    ),
    (
        "2026-06-07",
        "running",
        "long_run",
        180,
        21.0,
        "easy",
        "Z2",
        "Long 2 endurance: Turenne → Abbesses + 7 reps Montmartre (D+700m) + retour — jambes lourdes, HR<150, allure TMB J2",
    ),
    # ── S18 (8–14 juin) — Récup active ─────────────────────────────────────
    # Lun 08/06 : OFF
    (
        "2026-06-09",
        "running",
        "recovery",
        45,
        7.0,
        "easy",
        "Z1",
        "Récup: Turenne → Canal St-Martin → Républiq → retour, plat très lent",
    ),
    (
        "2026-06-10",
        "strength",
        "strength",
        45,
        None,
        "moderate",
        None,
        "Upper + 15min mollets/chevilles (montée sur pointe d'escalier)",
    ),
    (
        "2026-06-11",
        "running",
        "tempo",
        60,
        10.0,
        "moderate",
        "Z3",
        "Tempo plat: Turenne → Quais de Seine (Île de la Cité) → retour, 4×3min allure seuil",
    ),
    # Ven 12/06 : OFF
    (
        "2026-06-13",
        "running",
        "endurance",
        100,
        15.0,
        "moderate",
        "Z2",
        "Moyen vallonné: Turenne → Abbesses + 4 reps Montmartre (D+400m) + retour",
    ),
    (
        "2026-06-14",
        "running",
        "recovery",
        60,
        9.0,
        "easy",
        "Z1",
        "Easy récup: Turenne → Canal St-Martin → Quais aller-retour, jambes fluides",
    ),
    # ── S19 (15–21 juin) — Bloc spécifique 2 PEAK ───────────────────────────
    # Lun 15/06 : OFF
    (
        "2026-06-16",
        "running",
        "endurance",
        60,
        10.0,
        "moderate",
        "Z2",
        "Focus descentes: Turenne → Abbesses + 4 reps Montmartre, insister sur descente Saules escaliers (quadri excentrique)",
    ),
    (
        "2026-06-17",
        "strength",
        "strength",
        45,
        None,
        "moderate",
        None,
        "Upper light + gainage",
    ),
    (
        "2026-06-18",
        "running",
        "tempo",
        90,
        13.0,
        "moderate",
        "Z3",
        "Tempo long vallonné: Turenne → Abbesses + 6 reps Montmartre soutenu (D+600m) + retour",
    ),
    # Ven 19/06 : OFF strict (veille gros week-end)
    (
        "2026-06-20",
        "running",
        "long_run",
        240,
        28.0,
        "moderate",
        "Z2",
        "RÉPÉTITION GÉNÉRALE TMB: Turenne → Abbesses + 11 reps Montmartre (D+1100m) + retour — SAC COMPLET (nutrition 60g/h, gourdes, chaussures TMB, vêtements)",
    ),
    (
        "2026-06-21",
        "running",
        "long_run",
        180,
        21.0,
        "easy",
        "Z2",
        "BACK-TO-BACK J2: Turenne → Abbesses + 7 reps Montmartre (D+700m) + retour — MÊME SAC, allure très lente, HR<155 — simuler TMB J2 avec jambes lourdes",
    ),
    # ── S20 (22–28 juin) — Décharge ─────────────────────────────────────────
    # Lun 22/06 : OFF
    (
        "2026-06-23",
        "running",
        "recovery",
        45,
        7.0,
        "easy",
        "Z1",
        "Easy + accélérations: Canal St-Martin plat, 6×100m fluides fin de séance",
    ),
    (
        "2026-06-24",
        "strength",
        "strength",
        30,
        None,
        "easy",
        None,
        "Upper très light — pas de jambes (soutenances J+1)",
    ),
    # Jeu 25/06 : exam+oral → séance déplacée au 24 matin si possible, sinon OFF
    (
        "2026-06-27",
        "running",
        "endurance",
        100,
        14.0,
        "moderate",
        "Z2",
        "Moyen vallonné post-soutenances: Turenne → Abbesses + 5 reps Montmartre (D+500m) + retour",
    ),
    (
        "2026-06-28",
        "running",
        "recovery",
        60,
        9.0,
        "easy",
        "Z1",
        "Easy plat: Turenne → Quais de Seine aller-retour, jambes fluides",
    ),
    # ── S21 (29 juin – 6 juillet) — Activation ──────────────────────────────
    (
        "2026-06-29",
        "running",
        "recovery",
        30,
        5.0,
        "easy",
        "Z1",
        "Très court: Canal St-Martin aller-retour, plat easy",
    ),
    # Mar 30/06 : OFF
    (
        "2026-07-01",
        "running",
        "tempo",
        40,
        7.0,
        "moderate",
        "Z2",
        "Activation: Turenne → Canal St-Martin + 4×1min allure tempo, jambes vives",
    ),
    # Jeu 02/07 : OFF
    (
        "2026-07-03",
        "running",
        "recovery",
        30,
        5.0,
        "easy",
        "Z1",
        "Activation légère: 5km autour de République, 4×20s accélérations",
    ),
    (
        "2026-07-05",
        "running",
        "recovery",
        30,
        4.0,
        "easy",
        "Z1",
        "Dernière sortie avant voyage: 4km très easy Canal St-Martin, fraîcheur",
    ),
    (
        "2026-07-06",
        "running",
        "recovery",
        40,
        5.0,
        "easy",
        "Z2",
        "Reconnaissance Chamonix à l'arrivée: 30-40min très léger, sentir l'altitude, pas de D+",
    ),
    # ── TMB 8–9–10 juillet ───────────────────────────────────────────────────
    (
        "2026-07-08",
        "running",
        "race",
        600,
        55.0,
        "hard",
        "Z2",
        "TMB Jour 1 — France/Italie",
    ),
    (
        "2026-07-09",
        "running",
        "race",
        600,
        60.0,
        "hard",
        "Z2",
        "TMB Jour 2 — Italie/Suisse",
    ),
    (
        "2026-07-10",
        "running",
        "race",
        600,
        55.0,
        "hard",
        "Z2",
        "TMB Jour 3 — Suisse/France",
    ),
]

print(f"\nCreating {len(PLAN)} sessions…")
ok = fail = 0
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
        print(f"  OK  {date} {desc[:65]}")
    else:
        fail += 1
        print(f"  FAIL {date} {code}: {text[:150]}")

print(f"\nDone: {ok} created, {fail} failed")
sys.exit(0 if fail == 0 else 1)
