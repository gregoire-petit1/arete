"""One vocabulary for muscles, and the stats the heat map needs.

Exercises are stored with whatever the catalog or the parser knew at the time:
sometimes a precise head ("lats"), sometimes a region ("back"), sometimes
nothing useful ("full_body"). Everything is expanded here onto the twenty ids
the silhouette can paint, so the map never lights a whole back because one
exercise was filed coarsely.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date

# The twenty regions the silhouette draws, front then back then legs.
CANONICAL: tuple[str, ...] = (
    "chest",
    "front_delts",
    "side_delts",
    "biceps",
    "forearms",
    "abs",
    "obliques",
    "traps",
    "rear_delts",
    "lats",
    "rhomboids",
    "lower_back",
    "triceps",
    "quads",
    "hip_flexors",
    "adductors",
    "tibialis",
    "glutes",
    "hamstrings",
    "calves",
)

LABEL_FR: dict[str, str] = {
    "chest": "Pectoraux",
    "front_delts": "Deltoïdes antérieurs",
    "side_delts": "Deltoïdes latéraux",
    "biceps": "Biceps",
    "forearms": "Avant-bras",
    "abs": "Abdominaux",
    "obliques": "Obliques",
    "traps": "Trapèzes",
    "rear_delts": "Deltoïdes postérieurs",
    "lats": "Grands dorsaux",
    "rhomboids": "Rhomboïdes",
    "lower_back": "Lombaires",
    "triceps": "Triceps",
    "quads": "Quadriceps",
    "hip_flexors": "Fléchisseurs de hanche",
    "adductors": "Adducteurs",
    "tibialis": "Tibial antérieur",
    "glutes": "Fessiers",
    "hamstrings": "Ischio-jambiers",
    "calves": "Mollets",
}

# Coarse or legacy ids, split over the regions they actually cover.
ALIASES: dict[str, dict[str, float]] = {
    "shoulders": {"front_delts": 0.4, "side_delts": 0.35, "rear_delts": 0.25},
    "deltoids": {"front_delts": 0.4, "side_delts": 0.35, "rear_delts": 0.25},
    "back": {"lats": 0.5, "traps": 0.25, "rhomboids": 0.25},
    "upper_back": {"traps": 0.5, "rhomboids": 0.5},
    "mid_back": {"rhomboids": 0.6, "lats": 0.4},
    "core": {"abs": 0.6, "obliques": 0.4},
    "pectorals": {"chest": 1.0},
    "pecs": {"chest": 1.0},
    "erector_spinae": {"lower_back": 1.0},
    "spinal_erectors": {"lower_back": 1.0},
    "latissimus_dorsi": {"lats": 1.0},
    "trapezius": {"traps": 1.0},
    "quadriceps": {"quads": 1.0},
    "gluteus_maximus": {"glutes": 1.0},
    "gluteus_medius": {"glutes": 1.0},
    "biceps_femoris": {"hamstrings": 1.0},
    "gastrocnemius": {"calves": 1.0},
    "soleus": {"calves": 1.0},
    "tibialis_anterior": {"tibialis": 1.0},
    "inner_thigh": {"adductors": 1.0},
    "iliopsoas": {"hip_flexors": 1.0},
    "brachioradialis": {"forearms": 1.0},
    "wrist_flexors": {"forearms": 1.0},
    "rectus_abdominis": {"abs": 1.0},
    "external_obliques": {"obliques": 1.0},
    "full_body": {
        "quads": 0.15,
        "glutes": 0.15,
        "lats": 0.12,
        "chest": 0.12,
        "abs": 0.12,
        "hamstrings": 0.1,
        "traps": 0.08,
        "front_delts": 0.08,
        "triceps": 0.04,
        "biceps": 0.04,
    },
}


def expand(muscle: str) -> dict[str, float]:
    """Regions a stored muscle id covers, with the share of the volume each takes."""
    key = (muscle or "").strip().lower()
    if key in CANONICAL:
        return {key: 1.0}
    return ALIASES.get(key, {})


def spread(volumes: Mapping[str, float]) -> dict[str, float]:
    """Rewrite any muscle vocabulary onto the canonical regions."""
    out: dict[str, float] = {}
    for muscle, volume in volumes.items():
        for region, share in expand(muscle).items():
            out[region] = out.get(region, 0.0) + volume * share
    return out


HEAT_LEVELS = 5  # 0 (cold) to 4 (hardest worked region of the window)


def heat_level(volume: float, peak: float) -> int:
    """Relative scale: the busiest region of the window is always 4, nothing is 0."""
    if volume <= 0 or peak <= 0:
        return 0
    return max(1, min(HEAT_LEVELS - 1, round(volume / peak * (HEAT_LEVELS - 1))))


@dataclass(frozen=True)
class MuscleStat:
    muscle: str
    label: str
    volume: float
    sets: int
    level: int
    previous_volume: float | None
    last_trained: date | None

    def as_dict(self) -> dict:
        return {
            "muscle": self.muscle,
            "label": self.label,
            "volume": round(self.volume, 1),
            "sets": self.sets,
            "level": self.level,
            "previous_volume": (
                None if self.previous_volume is None else round(self.previous_volume, 1)
            ),
            "last_trained": self.last_trained.isoformat()
            if self.last_trained
            else None,
        }


def build_stats(
    volumes: Mapping[str, float],
    sets: Mapping[str, float],
    last_trained: Mapping[str, date],
    previous: Mapping[str, float] | None = None,
) -> list[MuscleStat]:
    """One entry per canonical region, ordered by volume, cold regions included."""
    current = spread(volumes)
    set_counts = spread(sets)
    prev = spread(previous) if previous is not None else None
    peak = max(current.values(), default=0.0)

    stats = [
        MuscleStat(
            muscle=region,
            label=LABEL_FR[region],
            volume=current.get(region, 0.0),
            sets=int(round(set_counts.get(region, 0.0))),
            level=heat_level(current.get(region, 0.0), peak),
            previous_volume=None if prev is None else prev.get(region, 0.0),
            last_trained=_latest(region, last_trained),
        )
        for region in CANONICAL
    ]
    return sorted(stats, key=lambda s: -s.volume)


def _latest(region: str, last_trained: Mapping[str, date]) -> date | None:
    """Most recent day any stored id that covers this region was trained."""
    days = [day for muscle, day in last_trained.items() if region in expand(muscle)]
    return max(days) if days else None
