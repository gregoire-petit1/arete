"""Per-second streams of an activity, kept after the FIT parse.

The FIT records (1 Hz, or every few seconds with smart recording) used to be
read for the HR zones and dropped. They are now kept, one row per activity in
``app.activity_streams``, one LIST column per channel aligned on ``t``
(seconds since the first record), so the session page can chart them and the
analytics in ``time_series`` can read them again without the file.

Sizing: the column types are narrow on purpose. With every channel present a
sample is 30 bytes (INTEGER t, SMALLINT heart rate, cadence and power, FLOAT
speed, altitude, distance, latitude and longitude; float32 keeps about half a
metre of precision on coordinates), so an hour at 1 Hz is at most ~108 KB
before DuckDB compresses the list segments. ``MAX_SAMPLES`` bounds a single
row: longer recordings are thinned evenly rather than truncated.

Pure data and conversions only: the SQL lives in ``GarminRepository``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from arete.garmin.time_series import TimeSeriesData, TimeSeriesPoint

#: Twelve hours at 1 Hz. Beyond it, every k-th sample is kept.
MAX_SAMPLES = 43_200

#: Sports whose FIT cadence is in strides per minute (doubled to steps/min,
#: the unit of the session averages from the Garmin API and Strava).
STRIDE_CADENCE_SPORTS = frozenset({"running", "walking", "hiking"})

#: Stored channels, in the column order of ``app.activity_streams``.
CHANNELS = (
    "heart_rate",
    "speed_mps",
    "altitude_m",
    "distance_m",
    "cadence",
    "power_w",
    "lat",
    "lon",
)

#: Decimal places kept per channel (the integers are rounded to units).
_DECIMALS = {
    "heart_rate": 0,
    "speed_mps": 2,
    "altitude_m": 1,
    "distance_m": 1,
    "cadence": 0,
    "power_w": 0,
    "lat": 6,
    "lon": 6,
}


@dataclass(frozen=True)
class ActivityStreams:
    """One activity's samples, channel by channel, aligned on ``t``.

    A channel the activity never recorded is ``None``; a sample missing from a
    recorded channel is a ``None`` element.
    """

    t: list[int]
    heart_rate: list[float | None] | None = None
    speed_mps: list[float | None] | None = None
    altitude_m: list[float | None] | None = None
    distance_m: list[float | None] | None = None
    cadence: list[float | None] | None = None
    power_w: list[float | None] | None = None
    lat: list[float | None] | None = None
    lon: list[float | None] | None = None

    def __post_init__(self) -> None:
        for name in CHANNELS:
            values = getattr(self, name)
            assert values is None or len(values) == len(self.t), name

    def __len__(self) -> int:
        return len(self.t)

    def channels(self) -> dict[str, list[float | None]]:
        """The recorded channels only."""
        return {
            name: getattr(self, name)
            for name in CHANNELS
            if getattr(self, name) is not None
        }

    @property
    def has_route(self) -> bool:
        return self.lat is not None and self.lon is not None

    def to_time_series(self, start: datetime | None = None) -> TimeSeriesData:
        """Back into the analytics' shape (``ActivityMetricsCalculator``)."""
        base = start or datetime(2000, 1, 1)
        columns = self.channels()

        def at(name: str, i: int) -> Any:
            values = columns.get(name)
            return None if values is None else values[i]

        points = []
        for i, t in enumerate(self.t):
            hr, cadence, power = at("heart_rate", i), at("cadence", i), at("power_w", i)
            points.append(
                TimeSeriesPoint(
                    timestamp=base + timedelta(seconds=t),
                    elapsed_sec=t,
                    heart_rate=None if hr is None else int(hr),
                    speed_mps=at("speed_mps", i),
                    cadence=None if cadence is None else int(cadence),
                    power=None if power is None else int(power),
                    altitude=at("altitude_m", i),
                    distance_m=at("distance_m", i),
                    lat=at("lat", i),
                    lon=at("lon", i),
                )
            )
        return TimeSeriesData(points=points)


def _round(value: Any, decimals: int) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return round(number) if decimals == 0 else round(number, decimals)


def from_time_series(ts: TimeSeriesData | None, sport: str) -> ActivityStreams | None:
    """Streams worth storing from a detailed FIT parse, or None.

    Cadence is converted to steps per minute on foot. Points come in record
    order; ``t`` restarts from the first record so a pause stays a gap.
    """
    if ts is None or not ts.points:
        return None
    points = ts.points
    if len(points) > MAX_SAMPLES:
        step = -(-len(points) // MAX_SAMPLES)  # ceiling division
        points = points[::step]
    start = points[0].timestamp
    cadence_factor = 2 if sport in STRIDE_CADENCE_SPORTS else 1

    raw: dict[str, list[Any]] = {
        "heart_rate": [p.heart_rate for p in points],
        "speed_mps": [p.speed_mps for p in points],
        "altitude_m": [p.altitude for p in points],
        "distance_m": [p.distance_m for p in points],
        "cadence": [
            None if p.cadence is None else p.cadence * cadence_factor for p in points
        ],
        "power_w": [p.power for p in points],
        "lat": [p.lat for p in points],
        "lon": [p.lon for p in points],
    }
    columns: dict[str, list[float | None] | None] = {}
    for name, values in raw.items():
        rounded = [_round(v, _DECIMALS[name]) for v in values]
        columns[name] = rounded if any(v is not None for v in rounded) else None
    if all(values is None for values in columns.values()):
        return None
    t = [max(0, int((p.timestamp - start).total_seconds())) for p in points]
    return ActivityStreams(t=t, **columns)


def _bucket_mean(values: list[float | None], start: int, end: int) -> float | None:
    present = [v for v in values[start:end] if v is not None]
    return sum(present) / len(present) if present else None


def downsample(streams: ActivityStreams, max_points: int) -> dict[str, list[Any]]:
    """At most ``max_points`` samples per channel, for a chart.

    Each output point is the mean of its bucket (the bucket's first ``t``),
    so a short spike still moves the line instead of vanishing between picks.
    Coordinates are not included: see ``route``.
    """
    assert max_points > 0
    n = len(streams)
    size = max(1, -(-n // max_points))
    starts = range(0, n, size)
    out: dict[str, list[Any]] = {"t": [streams.t[i] for i in starts]}
    for name, values in streams.channels().items():
        if name in ("lat", "lon"):
            continue
        decimals = _DECIMALS[name]
        out[name] = [
            _round(_bucket_mean(values, i, min(i + size, n)), decimals) for i in starts
        ]
    return out


def route(streams: ActivityStreams, max_points: int) -> list[list[float]] | None:
    """The GPS trace as [lat, lon] pairs, evenly thinned to about ``max_points``."""
    if streams.lat is None or streams.lon is None:
        return None
    pairs = [
        [lat, lon]
        for lat, lon in zip(streams.lat, streams.lon, strict=True)
        if lat is not None and lon is not None
    ]
    if len(pairs) < 2:
        return None
    step = max(1, -(-len(pairs) // max_points))
    thinned = pairs[::step]
    if thinned[-1] is not pairs[-1]:
        thinned.append(pairs[-1])  # the finish stays where it was
    return thinned
