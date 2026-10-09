"""Running fitness as Jack Daniels' VDOT: race equivalents and training paces.

Two published equations (Daniels & Gilbert, *Oxygen Power*, 1979):

- oxygen cost of running at ``v`` metres per minute:
  ``VO2 = -4.60 + 0.182258 v + 0.000104 v^2`` (ml/kg/min);
- share of VO2max sustainable for ``t`` minutes:
  ``0.8 + 0.1894393 e^(-0.012778 t) + 0.2989558 e^(-0.1932605 t)``.

A race gives the VDOT (cost / share); the VDOT gives every other race time
and the training paces, each a share of VDOT. Pure functions, no I/O.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

#: Daniels' training intensities, as shares of VDOT.
EASY_RANGE = (0.62, 0.70)
THRESHOLD_SHARE = 0.88
INTERVAL_SHARE = 0.98
REPETITION_SHARE = 1.05

RACE_DISTANCES_M: dict[str, int] = {
    "5k": 5000,
    "10k": 10000,
    "half": 21097,
    "marathon": 42195,
}


def oxygen_cost(v_m_per_min: float) -> float:
    return -4.60 + 0.182258 * v_m_per_min + 0.000104 * v_m_per_min**2


def sustainable_share(minutes: float) -> float:
    return (
        0.8
        + 0.1894393 * math.exp(-0.012778 * minutes)
        + 0.2989558 * math.exp(-0.1932605 * minutes)
    )


def vdot_from_race(distance_m: float, time_sec: float) -> float:
    """VDOT shown by a race (or Garmin's prediction of one)."""
    if distance_m <= 0 or time_sec <= 0:
        raise ValueError("distance and time must be positive")
    minutes = time_sec / 60
    return oxygen_cost(distance_m / minutes) / sustainable_share(minutes)


def velocity_at(vo2: float) -> float:
    """Metres per minute whose oxygen cost is ``vo2`` (the quadratic's root)."""
    a, b, c = 0.000104, 0.182258, -4.60 - vo2
    return (-b + math.sqrt(b * b - 4 * a * c)) / (2 * a)


def pace_sec_km(vo2: float) -> int:
    return round(60_000 / velocity_at(vo2))


def vdot_from_threshold_pace(sec_per_km: int) -> float:
    """VDOT from the pace held at threshold (Daniels' T pace, 88 % of VDOT)."""
    v = 60_000 / sec_per_km
    return oxygen_cost(v) / THRESHOLD_SHARE


def race_time_sec(vdot: float, distance_m: float) -> int:
    """Equivalent race time over ``distance_m`` for this VDOT (bisection)."""
    low, high = distance_m / 1000 * 1.5, distance_m / 1000 * 20.0  # minutes
    for _ in range(60):
        mid = (low + high) / 2
        shown = oxygen_cost(distance_m / mid) / sustainable_share(mid)
        if shown > vdot:
            low = mid  # too fast for this VDOT: more time
        else:
            high = mid
    return round((low + high) / 2 * 60)


@dataclass(frozen=True)
class TrainingPaces:
    """Seconds per km; easy is a range (slow, fast)."""

    vdot: float
    easy: tuple[int, int]
    marathon: int
    threshold: int
    interval: int
    repetition: int

    def to_dict(self) -> dict:
        return {
            "vdot": round(self.vdot, 1),
            "easy": list(self.easy),
            "marathon": self.marathon,
            "threshold": self.threshold,
            "interval": self.interval,
            "repetition": self.repetition,
        }


def training_paces(vdot: float) -> TrainingPaces:
    marathon_time = race_time_sec(vdot, RACE_DISTANCES_M["marathon"])
    return TrainingPaces(
        vdot=vdot,
        easy=(pace_sec_km(EASY_RANGE[0] * vdot), pace_sec_km(EASY_RANGE[1] * vdot)),
        marathon=round(marathon_time / (RACE_DISTANCES_M["marathon"] / 1000)),
        threshold=pace_sec_km(THRESHOLD_SHARE * vdot),
        interval=pace_sec_km(INTERVAL_SHARE * vdot),
        repetition=pace_sec_km(REPETITION_SHARE * vdot),
    )


def race_equivalents(vdot: float) -> dict[str, int]:
    return {name: race_time_sec(vdot, d) for name, d in RACE_DISTANCES_M.items()}


def format_pace(sec_per_km: int) -> str:
    return f"{sec_per_km // 60}:{sec_per_km % 60:02d}/km"
