"""Heart-rate zones computed from the athlete's own numbers.

A zone only means something against a reference. Threshold heart rate is the
better one: it moves with fitness and it is what a session is planned around.
Max heart rate is the fallback for an athlete who has never tested a threshold.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Literal

Basis = Literal["lthr", "max_hr"]

DEFAULT_MAX_HR = 190

# Share of threshold HR opening each zone (Friel, running): Z1 < 85 %, Z2 85-89,
# Z3 90-94, Z4 95-99, Z5 >= 100 % of threshold.
LTHR_FRACTIONS: tuple[float, float, float, float] = (0.85, 0.90, 0.95, 1.00)
# Share of max HR opening each zone, for athletes without a tested threshold.
MAX_HR_FRACTIONS: tuple[float, float, float, float] = (0.60, 0.70, 0.80, 0.90)
#: Threshold HR as a share of max HR: where the two tables open Z5.
LTHR_FROM_MAX_HR = MAX_HR_FRACTIONS[3] / LTHR_FRACTIONS[3]

ZONE_NAMES: tuple[str, ...] = ("z1", "z2", "z3", "z4", "z5")

#: What each zone is called, in French. Same words the Analytics card uses, so
#: the coach and the chart never disagree about what Z3 means.
ZONE_LABELS_FR: tuple[str, ...] = (
    "récupération",
    "endurance",
    "tempo",
    "seuil",
    "VO2max",
)


@dataclass(frozen=True)
class ZoneModel:
    """The four heart rates that separate the five zones."""

    boundaries: tuple[int, int, int, int]
    basis: Basis
    reference: int

    @classmethod
    def from_reference(
        cls, lthr: int | None = None, max_hr: int | None = None
    ) -> ZoneModel:
        """Threshold first, max HR second, a plausible default last."""
        if lthr and lthr > 0:
            return cls(_bounds(lthr, LTHR_FRACTIONS), "lthr", lthr)
        reference = max_hr if max_hr and max_hr > 0 else DEFAULT_MAX_HR
        return cls(_bounds(reference, MAX_HR_FRACTIONS), "max_hr", reference)

    @property
    def threshold_hr(self) -> int:
        """Threshold HR: tested, or derived from max HR."""
        if self.basis == "lthr":
            return self.reference
        return round(self.reference * LTHR_FROM_MAX_HR)

    def zone_of(self, hr: float) -> int:
        """Zone number 1-5 for one heart-rate reading."""
        for index, boundary in enumerate(self.boundaries):
            if hr < boundary:
                return index + 1
        return 5

    def labelled_zone_of(self, hr: float) -> tuple[int, str]:
        """Zone number and its French name, e.g. ``(2, "endurance")``."""
        zone = self.zone_of(hr)
        return zone, ZONE_LABELS_FR[zone - 1]

    def seconds_in_zones(
        self, samples: Iterable[tuple[float, float]]
    ) -> dict[str, int]:
        """Seconds per zone from (heart rate, seconds) samples."""
        totals = dict.fromkeys(ZONE_NAMES, 0)
        for hr, seconds in samples:
            if hr and seconds > 0:
                totals[f"z{self.zone_of(hr)}"] += int(round(seconds))
        return totals

    def target_range(self, zone: int) -> tuple[int, int]:
        """A closed bpm range to aim at for zone 1-5 (a planned "Z2").

        The outer zones are open-ended; each gets the width of its neighbour,
        so a planned Z1 or Z5 still has a range a watch can display.
        """
        if not 1 <= zone <= 5:
            raise ValueError(f"zone {zone}")
        b = self.boundaries
        if zone == 1:
            return b[0] - (b[1] - b[0]), b[0] - 1
        if zone == 5:
            return b[3], b[3] + (b[3] - b[2])
        return b[zone - 2], b[zone - 1] - 1

    def ranges(self) -> list[tuple[int, int | None]]:
        """Heart-rate span of each zone; the last one is open-ended."""
        low = 0
        spans: list[tuple[int, int | None]] = []
        for boundary in self.boundaries:
            spans.append((low, boundary - 1))
            low = boundary
        spans.append((low, None))
        return spans

    def as_dict(self) -> dict:
        return {
            "basis": self.basis,
            "reference": self.reference,
            "boundaries": list(self.boundaries),
            "ranges": [
                {"zone": name, "min": low, "max": high}
                for name, (low, high) in zip(ZONE_NAMES, self.ranges(), strict=True)
            ],
        }


def _bounds(reference: int, fractions: Sequence[float]) -> tuple[int, int, int, int]:
    values = [int(round(reference * f)) for f in fractions]
    # Keep the boundaries strictly increasing even with a low reference.
    for i in range(1, len(values)):
        values[i] = max(values[i], values[i - 1] + 1)
    return (values[0], values[1], values[2], values[3])


def samples_from_laps(laps: Iterable[dict]) -> list[tuple[float, float]]:
    """(average HR, seconds) per lap — the fallback when no FIT file is stored."""
    samples = []
    for lap in laps or []:
        hr = lap.get("average_heartrate")
        seconds = lap.get("moving_time") or lap.get("elapsed_time")
        if hr and seconds:
            samples.append((float(hr), float(seconds)))
    return samples
