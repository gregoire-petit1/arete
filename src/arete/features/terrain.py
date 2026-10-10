"""Terrain of a session on foot, from its kept streams: GAP, climbing speed, descents.

Grade-adjusted pace (GAP) uses the energy cost of running on a slope measured
by Minetti et al. (2002), "Energy cost of walking and running at extreme uphill
and downhill slopes", J Appl Physiol 93:1039-1046, fitted on gradients from
-45 % to +45 %:

    C(i) = 155.4 i^5 - 30.4 i^4 - 43.3 i^3 + 46.3 i^2 + 19.5 i + 3.6   (J/kg/m)

where ``i`` is the gradient as a fraction (rise over horizontal distance).
Each stretch of the session counts ``C(i) / C(0)`` times its horizontal
distance: the flat distance the same energy would have covered. The session's
``grade_factor`` is that flat-equivalent distance over the distance actually
run, and its GAP is the pace divided by it (a flat run keeps its pace).
Minetti's curve is metabolic: a technical descent run slower than the cost
allows reads as slow, which is what it was for the legs, not for the lungs.

Climbing speed (VAM, m/h) is the best net gain over a fixed duration, like a
power curve for climbing. The descent profile is the time and distance spent
in each band of negative grade, so a period can sum it into a pace per band.

Pure functions over plain lists, no I/O: ``services/session_conditions``
reads the streams and stores what this returns.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

#: Bump when the computation changes: stored rows below it are recomputed.
MODEL_VERSION = 1

#: Minetti's polynomial, highest degree first.
MINETTI_COEFFICIENTS = (155.4, -30.4, -43.3, 46.3, 19.5, 3.6)
#: The range the polynomial was fitted on; steeper samples are clamped to it.
MAX_GRADE = 0.45

#: Altitude is averaged over this many seconds on each side of a sample:
#: barometric steps and GPS jitter would otherwise read as steep grades.
SMOOTH_HALF_WINDOW_SEC = 15
#: Horizontal length of the stretches a grade is read on.
SEGMENT_M = 20.0
#: A longer gap between two samples is a pause (or lost signal), not effort.
MAX_STEP_SEC = 30
#: Slower than this the athlete is standing, not walking up a wall.
MIN_MOVING_MPS = 0.3
#: Below this a GAP says nothing.
MIN_GAP_DISTANCE_M = 1000.0

#: Durations of the climbing-speed curve, in minutes.
VAM_MINUTES = (5, 10, 20, 30, 60)

#: Grade bands of the descent profile, in percent, flat first (lower, upper).
DESCENT_BANDS: tuple[tuple[int, int], ...] = (
    (-2, 2),
    (-5, -2),
    (-10, -5),
    (-15, -10),
    (-20, -15),
    (-30, -20),
    (-45, -30),
)


def running_cost(grade: float) -> float:
    """Minetti's energy cost of running at ``grade`` (fraction), in J/kg/m."""
    i = max(-MAX_GRADE, min(MAX_GRADE, grade))
    cost = 0.0
    for coefficient in MINETTI_COEFFICIENTS:
        cost = cost * i + coefficient
    return cost


def grade_factor(grade: float) -> float:
    """Cost of a metre at ``grade`` relative to a flat metre."""
    return running_cost(grade) / MINETTI_COEFFICIENTS[-1]


@dataclass(frozen=True)
class Terrain:
    """What a session's streams say about its terrain."""

    #: Flat-equivalent distance over horizontal distance, None without GAP.
    grade_factor: float | None
    #: Grade-adjusted pace, s/km.
    gap_sec_km: int | None
    #: Best net climbing speed, m/h, per duration in minutes (positive only).
    vam: dict[int, int]
    #: Seconds and metres per band of ``DESCENT_BANDS`` that saw any.
    descent: list[dict[str, float]]


def smooth(t: Sequence[int], values: Sequence[float]) -> list[float]:
    """Centred moving average over ``SMOOTH_HALF_WINDOW_SEC`` on each side."""
    n = len(values)
    prefix = [0.0]
    for value in values:
        prefix.append(prefix[-1] + value)
    out: list[float] = []
    lo = hi = 0
    for i in range(n):
        while t[lo] < t[i] - SMOOTH_HALF_WINDOW_SEC:
            lo += 1
        while hi < n and t[hi] <= t[i] + SMOOTH_HALF_WINDOW_SEC:
            hi += 1
        out.append((prefix[hi] - prefix[lo]) / (hi - lo))
    return out


def _band(grade_pct: float) -> int | None:
    for index, (lower, upper) in enumerate(DESCENT_BANDS):
        if lower <= grade_pct < upper:
            return index
    return None


def _segments(
    t: Sequence[int], distance: Sequence[float], altitude: Sequence[float]
) -> list[tuple[float, float, float]]:
    """(seconds, horizontal metres, grade) of each moving stretch."""
    segments: list[tuple[float, float, float]] = []
    sec = metres = climb = 0.0

    def flush() -> None:
        nonlocal sec, metres, climb
        if metres > 0:
            segments.append((sec, metres, climb / metres))
        sec = metres = climb = 0.0

    for i in range(1, len(t)):
        dt = t[i] - t[i - 1]
        dd = distance[i] - distance[i - 1]
        if dt <= 0 or dt > MAX_STEP_SEC or dd < MIN_MOVING_MPS * dt:
            flush()  # a pause or a dropout closes the stretch
            continue
        sec += dt
        metres += dd
        climb += altitude[i] - altitude[i - 1]
        if metres >= SEGMENT_M:
            flush()
    flush()
    return segments


def _vam(t: Sequence[int], altitude: Sequence[float]) -> dict[int, int]:
    """Best net gain per duration, m/h: a window is the first sample past it."""
    bests: dict[int, int] = {}
    n = len(t)
    for minutes in VAM_MINUTES:
        span = minutes * 60
        if n < 2 or t[-1] - t[0] < span:
            break
        best = 0.0
        j = 0
        for i in range(n):
            j = max(j, i)
            while j < n and t[j] - t[i] < span:
                j += 1
            if j == n:
                break
            best = max(best, (altitude[j] - altitude[i]) / (t[j] - t[i]) * 3600)
        if best > 0:
            bests[minutes] = round(best)
    return bests


def analyze(
    t: Sequence[int],
    altitude_m: Sequence[float | None] | None,
    distance_m: Sequence[float | None] | None,
    *,
    pace_sec_km: int | None = None,
) -> Terrain | None:
    """The terrain of one session, None when it recorded no altitude.

    ``pace_sec_km`` is the session's own pace: the GAP divides it, so a flat
    run's GAP is its pace whatever pauses the streams cannot see. Without it
    the GAP is the streams' moving pace, adjusted.
    """
    if altitude_m is None:
        return None
    times: list[int] = []
    raw: list[float] = []
    walked: list[tuple[int, float]] = []  # (index in times, distance)
    for i, value in enumerate(altitude_m):
        if value is None:
            continue
        distance = None if distance_m is None else distance_m[i]
        if distance is not None:
            walked.append((len(times), float(distance)))
        times.append(t[i])
        raw.append(float(value))
    if len(times) < 2:
        return None
    altitude = smooth(times, raw)
    vam = _vam(times, altitude)

    factor = gap = None
    descent: list[dict[str, float]] = []
    if len(walked) >= 2:
        segments = _segments(
            [times[i] for i, _ in walked],
            [d for _, d in walked],
            [altitude[i] for i, _ in walked],
        )
        metres = sum(s[1] for s in segments)
        if metres >= MIN_GAP_DISTANCE_M:
            equivalent = sum(s[1] * grade_factor(s[2]) for s in segments)
            factor = equivalent / metres
            if pace_sec_km is None:
                pace_sec_km = round(sum(s[0] for s in segments) / metres * 1000)
            gap = round(pace_sec_km / factor)
        bands = [[0.0, 0.0] for _ in DESCENT_BANDS]
        for sec, length, grade in segments:
            band = _band(grade * 100)
            if band is not None:
                bands[band][0] += sec
                bands[band][1] += length
        descent = [
            {"min": lower, "max": upper, "sec": round(sec), "m": round(length)}
            for (lower, upper), (sec, length) in zip(DESCENT_BANDS, bands, strict=True)
            if sec > 0
        ]
    return Terrain(
        grade_factor=None if factor is None else round(factor, 3),
        gap_sec_km=gap,
        vam=vam,
        descent=descent,
    )
