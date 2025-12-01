"""Strength training metrics and calculations.

Implements:
- 1RM estimation (Epley, Brzycki, Lombardi, etc.)
- Volume calculations (tonnage, sets × reps × weight)
- Intensity metrics (%1RM, relative intensity)
- Training zones for strength
- VBT (Velocity Based Training) estimations

References:
- Epley (1985) - 1RM formula
- Brzycki (1993) - 1RM formula
- Jovanovic & Flanagan (2014) - VBT zones
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import NamedTuple


class StrengthZone(Enum):
    """Strength training zones based on %1RM."""

    TECHNIQUE = 1  # 50-65% 1RM - Skill work, speed
    HYPERTROPHY = 2  # 65-75% 1RM - Muscle building
    STRENGTH = 3  # 75-85% 1RM - Strength development
    POWER = 4  # 85-93% 1RM - Power, heavy doubles/triples
    MAX = 5  # 93-100% 1RM - Maximal strength, singles


class VBTZone(Enum):
    """Velocity Based Training zones."""

    STRENGTH_SPEED = "strength_speed"  # 0.75-1.0 m/s
    POWER = "power"  # 0.5-0.75 m/s
    ACCELERATIVE_STRENGTH = "accelerative_strength"  # 0.35-0.5 m/s
    ABSOLUTE_STRENGTH = "absolute_strength"  # < 0.35 m/s
    STARTING_STRENGTH = "starting_strength"  # > 1.0 m/s


class ZoneInfo(NamedTuple):
    """Information about a strength training zone."""

    zone: StrengthZone
    name: str
    description: str
    min_pct: float
    max_pct: float
    rep_range: str


# Zone definitions with French descriptions
ZONE_DEFINITIONS: dict[StrengthZone, ZoneInfo] = {
    StrengthZone.TECHNIQUE: ZoneInfo(
        StrengthZone.TECHNIQUE,
        "Technique",
        "Travail technique, vitesse, échauffement",
        0.50,
        0.65,
        "8-15+",
    ),
    StrengthZone.HYPERTROPHY: ZoneInfo(
        StrengthZone.HYPERTROPHY,
        "Hypertrophie",
        "Construction musculaire, volume modéré",
        0.65,
        0.75,
        "8-12",
    ),
    StrengthZone.STRENGTH: ZoneInfo(
        StrengthZone.STRENGTH,
        "Force",
        "Développement de la force",
        0.75,
        0.85,
        "4-6",
    ),
    StrengthZone.POWER: ZoneInfo(
        StrengthZone.POWER,
        "Puissance",
        "Force-vitesse, doubles et triples lourds",
        0.85,
        0.93,
        "2-3",
    ),
    StrengthZone.MAX: ZoneInfo(
        StrengthZone.MAX,
        "Maximal",
        "Force maximale, singles",
        0.93,
        1.00,
        "1",
    ),
}


@dataclass
class ExerciseSet:
    """A single set of an exercise."""

    reps: int
    weight_kg: float
    rpe: float | None = None
    velocity_ms: float | None = None  # For VBT

    @property
    def volume(self) -> float:
        """Volume = reps × weight."""
        return self.reps * self.weight_kg


@dataclass
class Exercise:
    """An exercise with multiple sets."""

    name: str
    sets: list[ExerciseSet] = field(default_factory=list)
    one_rm: float | None = None  # Known 1RM for this exercise

    @property
    def total_volume(self) -> float:
        """Total volume (tonnage) across all sets."""
        return sum(s.volume for s in self.sets)

    @property
    def total_sets(self) -> int:
        """Number of sets."""
        return len(self.sets)

    @property
    def total_reps(self) -> int:
        """Total reps across all sets."""
        return sum(s.reps for s in self.sets)

    @property
    def avg_weight(self) -> float:
        """Average weight used."""
        if not self.sets:
            return 0.0
        return sum(s.weight_kg for s in self.sets) / len(self.sets)

    @property
    def max_weight(self) -> float:
        """Maximum weight used."""
        if not self.sets:
            return 0.0
        return max(s.weight_kg for s in self.sets)


@dataclass
class StrengthSession:
    """A strength training session."""

    exercises: list[Exercise] = field(default_factory=list)
    duration_min: int | None = None
    rpe: float | None = None  # Session RPE

    @property
    def total_volume(self) -> float:
        """Total volume (tonnage) for the session."""
        return sum(e.total_volume for e in self.exercises)

    @property
    def total_sets(self) -> int:
        """Total number of sets."""
        return sum(e.total_sets for e in self.exercises)

    @property
    def total_reps(self) -> int:
        """Total number of reps."""
        return sum(e.total_reps for e in self.exercises)

    @property
    def density(self) -> float | None:
        """Training density = volume / duration (kg/min)."""
        if not self.duration_min or self.duration_min == 0:
            return None
        return self.total_volume / self.duration_min


# =============================================================================
# 1RM ESTIMATION FORMULAS
# =============================================================================


def estimate_1rm_epley(weight: float, reps: int) -> float:
    """Estimate 1RM using Epley formula.

    1RM = weight × (1 + reps/30)

    Most accurate for 10+ reps.

    Args:
        weight: Weight lifted
        reps: Number of reps completed

    Returns:
        Estimated 1RM
    """
    if reps <= 0:
        return 0.0
    if reps == 1:
        return weight
    return weight * (1 + reps / 30)


def estimate_1rm_brzycki(weight: float, reps: int) -> float:
    """Estimate 1RM using Brzycki formula.

    1RM = weight × 36 / (37 - reps)

    Most accurate for 1-10 reps.

    Args:
        weight: Weight lifted
        reps: Number of reps completed

    Returns:
        Estimated 1RM
    """
    if reps <= 0 or reps >= 37:
        return 0.0
    if reps == 1:
        return weight
    return weight * 36 / (37 - reps)


def estimate_1rm_lombardi(weight: float, reps: int) -> float:
    """Estimate 1RM using Lombardi formula.

    1RM = weight × reps^0.10

    Args:
        weight: Weight lifted
        reps: Number of reps completed

    Returns:
        Estimated 1RM
    """
    if reps <= 0:
        return 0.0
    if reps == 1:
        return float(weight)
    return float(weight * (reps**0.10))


def estimate_1rm_oconner(weight: float, reps: int) -> float:
    """Estimate 1RM using O'Conner formula.

    1RM = weight × (1 + reps/40)

    Similar to Epley, slightly more conservative.

    Args:
        weight: Weight lifted
        reps: Number of reps completed

    Returns:
        Estimated 1RM
    """
    if reps <= 0:
        return 0.0
    if reps == 1:
        return weight
    return weight * (1 + reps / 40)


def estimate_1rm_mayhew(weight: float, reps: int) -> float:
    """Estimate 1RM using Mayhew formula.

    1RM = 100 × weight / (52.2 + 41.9 × e^(-0.055 × reps))

    Accurate across rep ranges.

    Args:
        weight: Weight lifted
        reps: Number of reps completed

    Returns:
        Estimated 1RM
    """
    import math

    if reps <= 0:
        return 0.0
    if reps == 1:
        return weight
    return 100 * weight / (52.2 + 41.9 * math.exp(-0.055 * reps))


def estimate_1rm_average(weight: float, reps: int) -> float:
    """Estimate 1RM using average of multiple formulas.

    Provides a balanced estimate by averaging Epley, Brzycki, and Lombardi.

    Args:
        weight: Weight lifted
        reps: Number of reps completed

    Returns:
        Averaged 1RM estimate
    """
    if reps <= 0:
        return 0.0
    if reps == 1:
        return weight

    estimates = [
        estimate_1rm_epley(weight, reps),
        estimate_1rm_brzycki(weight, reps),
        estimate_1rm_lombardi(weight, reps),
    ]
    return sum(estimates) / len(estimates)


def estimate_1rm_rpe(weight: float, reps: int, rpe: float) -> float:
    """Estimate 1RM using RPE-based method.

    Uses the RPE/RIR chart to estimate true 1RM.
    RPE 10 = failure, RPE 9 = 1 rep in reserve, etc.

    Args:
        weight: Weight lifted
        reps: Number of reps completed
        rpe: Rate of Perceived Exertion (6-10 scale, 10 = max)

    Returns:
        Estimated 1RM adjusted for RPE
    """
    if reps <= 0 or rpe < 6:
        return 0.0

    # Reps in reserve = 10 - RPE
    rir = max(0, 10 - rpe)

    # Effective reps = actual reps + RIR
    effective_reps = reps + rir

    # Use Epley with effective reps
    return estimate_1rm_epley(weight, int(effective_reps))


# =============================================================================
# WEIGHT FROM TARGET
# =============================================================================


def weight_for_reps_at_percentage(one_rm: float, target_pct: float) -> float:
    """Calculate weight for a given %1RM.

    Args:
        one_rm: 1RM value
        target_pct: Target percentage (0.0-1.0)

    Returns:
        Weight to use
    """
    return one_rm * target_pct


def weight_for_target_reps(one_rm: float, target_reps: int) -> float:
    """Calculate weight for a target number of reps.

    Uses inverse of Epley formula.

    Args:
        one_rm: 1RM value
        target_reps: Target number of reps

    Returns:
        Weight to use
    """
    if target_reps <= 0:
        return one_rm
    if target_reps == 1:
        return one_rm
    return one_rm / (1 + target_reps / 30)


def percentage_from_reps(reps: int) -> float:
    """Estimate %1RM from rep count.

    Uses inverse of Epley formula.

    Args:
        reps: Number of reps

    Returns:
        Estimated %1RM (0.0-1.0)
    """
    if reps <= 0:
        return 1.0
    if reps == 1:
        return 1.0
    return 1 / (1 + reps / 30)


# =============================================================================
# INTENSITY METRICS
# =============================================================================


def calculate_relative_intensity(weight: float, one_rm: float) -> float:
    """Calculate relative intensity (%1RM).

    Args:
        weight: Weight used
        one_rm: 1RM value

    Returns:
        Relative intensity as decimal (0.0-1.0+)
    """
    if one_rm <= 0:
        return 0.0
    return weight / one_rm


def calculate_average_intensity(session: StrengthSession) -> float | None:
    """Calculate average relative intensity across a session.

    Only considers exercises with known 1RM.

    Args:
        session: Strength training session

    Returns:
        Average %1RM, or None if no exercises have known 1RM
    """
    intensities = []
    for exercise in session.exercises:
        if exercise.one_rm and exercise.one_rm > 0:
            for s in exercise.sets:
                ri = calculate_relative_intensity(s.weight_kg, exercise.one_rm)
                intensities.append(ri)

    if not intensities:
        return None
    return sum(intensities) / len(intensities)


def calculate_inol(reps: int, intensity_pct: float) -> float:
    """Calculate INOL (Intensity Number of Lifts).

    INOL = reps / (100 - intensity_pct)

    Used to measure training stress per set.
    - < 0.4: Easy, technical work
    - 0.4-0.8: Optimal for strength gains
    - 0.8-1.2: Hard, accumulates fatigue
    - > 1.2: Very demanding, risk of overtraining

    Args:
        reps: Number of reps
        intensity_pct: Intensity as percentage (e.g., 80 for 80%)

    Returns:
        INOL value
    """
    if intensity_pct >= 100:
        return float("inf")
    return reps / (100 - intensity_pct)


def calculate_session_inol(session: StrengthSession) -> float | None:
    """Calculate total INOL for a session.

    Weekly INOL recommendations:
    - < 2: Recovery/deload
    - 2-4: Optimal for progression
    - > 4: Risk of overtraining

    Args:
        session: Strength training session

    Returns:
        Total INOL, or None if no exercises have known 1RM
    """
    total_inol = 0.0
    has_data = False

    for exercise in session.exercises:
        if exercise.one_rm and exercise.one_rm > 0:
            for s in exercise.sets:
                intensity_pct = (s.weight_kg / exercise.one_rm) * 100
                set_inol = calculate_inol(s.reps, intensity_pct)
                total_inol += set_inol
                has_data = True

    return total_inol if has_data else None


# =============================================================================
# STRENGTH ZONES
# =============================================================================


def get_strength_zone(intensity_pct: float) -> StrengthZone:
    """Determine strength training zone from %1RM.

    Args:
        intensity_pct: Intensity as decimal (e.g., 0.80 for 80%)

    Returns:
        StrengthZone enum value
    """
    if intensity_pct < 0.65:
        return StrengthZone.TECHNIQUE
    if intensity_pct < 0.75:
        return StrengthZone.HYPERTROPHY
    if intensity_pct < 0.85:
        return StrengthZone.STRENGTH
    if intensity_pct < 0.93:
        return StrengthZone.POWER
    return StrengthZone.MAX


def get_zone_info(zone: StrengthZone) -> ZoneInfo:
    """Get detailed information about a zone.

    Args:
        zone: Strength training zone

    Returns:
        ZoneInfo with name, description, and rep range
    """
    return ZONE_DEFINITIONS[zone]


def get_zone_boundaries(one_rm: float) -> dict[StrengthZone, tuple[float, float]]:
    """Calculate weight boundaries for each zone.

    Args:
        one_rm: 1RM value

    Returns:
        Dict mapping zone to (min_weight, max_weight) tuple
    """
    return {
        zone: (
            round(info.min_pct * one_rm, 1),
            round(info.max_pct * one_rm, 1),
        )
        for zone, info in ZONE_DEFINITIONS.items()
    }


# =============================================================================
# VELOCITY BASED TRAINING (VBT)
# =============================================================================


def get_vbt_zone(velocity_ms: float) -> VBTZone:
    """Determine VBT zone from bar velocity.

    Based on Bryan Mann's velocity zones.

    Args:
        velocity_ms: Bar velocity in m/s

    Returns:
        VBTZone enum value
    """
    if velocity_ms > 1.0:
        return VBTZone.STARTING_STRENGTH
    if velocity_ms >= 0.75:
        return VBTZone.STRENGTH_SPEED
    if velocity_ms >= 0.5:
        return VBTZone.POWER
    if velocity_ms >= 0.35:
        return VBTZone.ACCELERATIVE_STRENGTH
    return VBTZone.ABSOLUTE_STRENGTH


def estimate_1rm_from_velocity(
    weight: float,
    velocity_ms: float,
    min_velocity: float = 0.17,
) -> float:
    """Estimate 1RM from velocity (load-velocity profile).

    Uses linear load-velocity relationship.
    Assumes 1RM is lifted at minimum velocity.

    Args:
        weight: Weight lifted
        velocity_ms: Velocity achieved
        min_velocity: Velocity at 1RM (default 0.17 m/s for squat)

    Returns:
        Estimated 1RM
    """
    # Simplified linear model
    # Assumes velocity decreases linearly with load
    # At 1RM, velocity = min_velocity
    if velocity_ms <= min_velocity:
        return weight

    # Rough approximation: every 0.1 m/s above min = ~5% below 1RM
    velocity_above_min = velocity_ms - min_velocity
    pct_below_max = velocity_above_min * 0.5  # Each 0.1 m/s ≈ 5%

    estimated_pct = 1 - pct_below_max
    if estimated_pct <= 0:
        return weight

    return weight / estimated_pct


def velocity_target_for_percentage(
    target_pct: float,
    max_velocity: float = 1.0,
    min_velocity: float = 0.17,
) -> float:
    """Calculate target velocity for a given %1RM.

    Uses linear load-velocity model.

    Args:
        target_pct: Target %1RM (0.0-1.0)
        max_velocity: Velocity at 0% load
        min_velocity: Velocity at 100% load

    Returns:
        Target velocity in m/s
    """
    velocity_range = max_velocity - min_velocity
    return max_velocity - (target_pct * velocity_range)


# =============================================================================
# VOLUME METRICS
# =============================================================================


def calculate_volume(sets: int, reps: int, weight: float) -> float:
    """Calculate training volume (tonnage).

    Volume = sets × reps × weight

    Args:
        sets: Number of sets
        reps: Reps per set (average)
        weight: Weight per rep

    Returns:
        Total volume in kg
    """
    return sets * reps * weight


def calculate_e1rm_volume(
    sets: int,
    reps: int,
    weight: float,
    one_rm: float,
) -> float:
    """Calculate effective volume normalized to 1RM.

    Accounts for intensity by weighting volume.

    Args:
        sets: Number of sets
        reps: Reps per set
        weight: Weight used
        one_rm: 1RM value

    Returns:
        Intensity-adjusted volume
    """
    if one_rm <= 0:
        return 0.0
    intensity = weight / one_rm
    return sets * reps * weight * intensity


def calculate_volume_load(exercise: Exercise) -> float:
    """Calculate total volume load for an exercise.

    Args:
        exercise: Exercise with sets

    Returns:
        Total volume (tonnage)
    """
    return exercise.total_volume


def calculate_session_volume(session: StrengthSession) -> float:
    """Calculate total session volume.

    Args:
        session: Strength training session

    Returns:
        Total volume in kg
    """
    return session.total_volume


# =============================================================================
# TRAINING LOAD FOR STRENGTH
# =============================================================================


def calculate_strength_training_load(
    session: StrengthSession,
) -> float:
    """Calculate training load for strength session.

    Uses volume × average intensity if 1RMs known,
    otherwise uses volume × session RPE.

    Args:
        session: Strength training session

    Returns:
        Training load value
    """
    volume = session.total_volume
    avg_intensity = calculate_average_intensity(session)

    if avg_intensity:
        # Volume × intensity factor
        return volume * avg_intensity

    if session.rpe:
        # Fall back to RPE-based load
        return volume * (session.rpe / 10)

    # Default: just volume
    return volume
