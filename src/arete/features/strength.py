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

from collections.abc import Mapping
from enum import Enum
from typing import TYPE_CHECKING, NamedTuple

if TYPE_CHECKING:
    from arete.strength.models import StrengthSession


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


def _one_rm_for(exercise_name: str | None, one_rm: Mapping[str, float]) -> float | None:
    if not exercise_name:
        return None
    value = one_rm.get(exercise_name.lower())
    return value if value and value > 0 else None


def calculate_average_intensity(
    session: StrengthSession, one_rm: Mapping[str, float]
) -> float | None:
    """Average relative intensity (%1RM as 0-1) over working sets.

    Args:
        session: Strength session (``arete.strength.models``)
        one_rm: Known 1RM per exercise name (lowercase)

    Returns:
        Average relative intensity, or None if no exercise has a known 1RM
    """
    intensities = []
    for exercise in session.exercises:
        name = exercise.exercise.name if exercise.exercise else None
        max_load = _one_rm_for(name, one_rm)
        if max_load is None:
            continue
        for s in exercise.sets:
            if s.weight_kg and not s.is_warmup:
                intensities.append(calculate_relative_intensity(s.weight_kg, max_load))

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


def calculate_session_inol(
    session: StrengthSession, one_rm: Mapping[str, float]
) -> float | None:
    """Total INOL for a session (sum over working sets with a known 1RM).

    Weekly INOL recommendations:
    - < 2: Recovery/deload
    - 2-4: Optimal for progression
    - > 4: Risk of overtraining

    Returns None if no exercise has a known 1RM.
    """
    total_inol = 0.0
    has_data = False

    for exercise in session.exercises:
        name = exercise.exercise.name if exercise.exercise else None
        max_load = _one_rm_for(name, one_rm)
        if max_load is None:
            continue
        for s in exercise.sets:
            if not s.weight_kg or s.is_warmup:
                continue
            total_inol += calculate_inol(s.reps, (s.weight_kg / max_load) * 100)
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
    session: StrengthSession, one_rm: Mapping[str, float] | None = None
) -> float:
    """Training load for a strength session.

    Volume x average intensity when 1RMs are known, else volume x session RPE,
    else plain volume.
    """
    volume = session.total_volume
    avg_intensity = calculate_average_intensity(session, one_rm or {})

    if avg_intensity:
        return volume * avg_intensity

    if session.overall_rpe:
        return volume * (session.overall_rpe / 10)

    # Default: just volume
    return volume
