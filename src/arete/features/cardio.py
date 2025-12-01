"""Cardio-specific training metrics and calculations.

Implements:
- TRIMP (Training Impulse) - Heart rate based training load
- TSS (Training Stress Score) - Power/pace based load
- Heart rate zones (5-zone model)
- VO2max estimation (various methods)
- Efficiency metrics (pace/HR, cardiac drift)

References:
- Banister (1991) - TRIMP methodology
- Coggan - TSS for cycling
- Tanaka et al. (2001) - Age-predicted HRmax
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import NamedTuple


class Sex(Enum):
    """Biological sex for physiological calculations."""

    MALE = "male"
    FEMALE = "female"


class HRZone(Enum):
    """Heart rate training zones (5-zone model)."""

    ZONE_1 = 1  # Recovery: 50-60% HRmax
    ZONE_2 = 2  # Endurance: 60-70% HRmax
    ZONE_3 = 3  # Tempo: 70-80% HRmax
    ZONE_4 = 4  # Threshold: 80-90% HRmax
    ZONE_5 = 5  # VO2max: 90-100% HRmax


class ZoneInfo(NamedTuple):
    """Information about a heart rate zone."""

    zone: HRZone
    name: str
    description: str
    hr_min_pct: float
    hr_max_pct: float


# Zone definitions
ZONE_DEFINITIONS: dict[HRZone, ZoneInfo] = {
    HRZone.ZONE_1: ZoneInfo(
        HRZone.ZONE_1,
        "Récupération",
        "Récupération active, très facile",
        0.50,
        0.60,
    ),
    HRZone.ZONE_2: ZoneInfo(
        HRZone.ZONE_2,
        "Endurance",
        "Endurance fondamentale, conversation aisée",
        0.60,
        0.70,
    ),
    HRZone.ZONE_3: ZoneInfo(
        HRZone.ZONE_3,
        "Tempo",
        "Allure marathon/semi, phrases courtes possibles",
        0.70,
        0.80,
    ),
    HRZone.ZONE_4: ZoneInfo(
        HRZone.ZONE_4,
        "Seuil",
        "Seuil lactique, effort soutenu difficile",
        0.80,
        0.90,
    ),
    HRZone.ZONE_5: ZoneInfo(
        HRZone.ZONE_5,
        "VO2max",
        "Effort maximal, quelques mots seulement",
        0.90,
        1.00,
    ),
}


@dataclass
class CardioSession:
    """A cardio training session with heart rate data."""

    duration_min: int
    hr_avg: int
    hr_max: int
    hr_rest: int | None = None  # Resting HR (for HRR calculations)
    distance_km: float | None = None
    elevation_m: float | None = None


@dataclass
class ZoneDistribution:
    """Time spent in each heart rate zone."""

    zone_1_min: float
    zone_2_min: float
    zone_3_min: float
    zone_4_min: float
    zone_5_min: float

    @property
    def total_min(self) -> float:
        """Total time across all zones."""
        return (
            self.zone_1_min + self.zone_2_min + self.zone_3_min + self.zone_4_min + self.zone_5_min
        )

    def as_percentages(self) -> dict[HRZone, float]:
        """Get zone distribution as percentages."""
        total = self.total_min
        if total == 0:
            return {zone: 0.0 for zone in HRZone}

        return {
            HRZone.ZONE_1: (self.zone_1_min / total) * 100,
            HRZone.ZONE_2: (self.zone_2_min / total) * 100,
            HRZone.ZONE_3: (self.zone_3_min / total) * 100,
            HRZone.ZONE_4: (self.zone_4_min / total) * 100,
            HRZone.ZONE_5: (self.zone_5_min / total) * 100,
        }


# =============================================================================
# HEART RATE MAX ESTIMATION
# =============================================================================


def estimate_hrmax_tanaka(age: int) -> int:
    """Estimate HRmax using Tanaka formula.

    HRmax = 208 - 0.7 × age

    More accurate than traditional 220-age formula.

    Args:
        age: Age in years

    Returns:
        Estimated maximum heart rate
    """
    return round(208 - 0.7 * age)


def estimate_hrmax_traditional(age: int) -> int:
    """Estimate HRmax using traditional formula.

    HRmax = 220 - age

    Simple but less accurate than Tanaka.

    Args:
        age: Age in years

    Returns:
        Estimated maximum heart rate
    """
    return 220 - age


def estimate_hrmax_gulati(age: int) -> int:
    """Estimate HRmax using Gulati formula (for women).

    HRmax = 206 - 0.88 × age

    More accurate for women than Tanaka.

    Args:
        age: Age in years

    Returns:
        Estimated maximum heart rate
    """
    return round(206 - 0.88 * age)


# =============================================================================
# TRIMP (Training Impulse)
# =============================================================================


def _trimp_factor(sex: Sex) -> float:
    """Get TRIMP weighting factor based on sex.

    Args:
        sex: Biological sex

    Returns:
        Weighting factor (1.92 for men, 1.67 for women)
    """
    return 1.92 if sex == Sex.MALE else 1.67


def calculate_hr_ratio(
    hr_avg: int,
    hr_max: int,
    hr_rest: int,
) -> float:
    """Calculate heart rate ratio (HRratio or %HRR).

    HRratio = (HR_avg - HR_rest) / (HR_max - HR_rest)

    Args:
        hr_avg: Average heart rate during session
        hr_max: Maximum heart rate
        hr_rest: Resting heart rate

    Returns:
        Heart rate ratio (0-1)
    """
    hr_reserve = hr_max - hr_rest
    if hr_reserve <= 0:
        return 0.0
    return max(0.0, min(1.0, (hr_avg - hr_rest) / hr_reserve))


def calculate_trimp(
    duration_min: int,
    hr_avg: int,
    hr_max: int,
    hr_rest: int,
    sex: Sex = Sex.MALE,
) -> float:
    """Calculate TRIMP (Training Impulse).

    TRIMP = duration × HRratio × 0.64 × e^(factor × HRratio)

    Where:
    - HRratio = (HR_avg - HR_rest) / (HR_max - HR_rest)
    - factor = 1.92 (men) or 1.67 (women)

    Args:
        duration_min: Session duration in minutes
        hr_avg: Average heart rate
        hr_max: Maximum heart rate
        hr_rest: Resting heart rate
        sex: Biological sex (for weighting factor)

    Returns:
        TRIMP value (arbitrary units)
    """
    import math

    hr_ratio = calculate_hr_ratio(hr_avg, hr_max, hr_rest)
    factor = _trimp_factor(sex)

    return duration_min * hr_ratio * 0.64 * math.exp(factor * hr_ratio)


def calculate_trimp_simplified(
    duration_min: int,
    hr_avg: int,
    hr_max: int,
) -> float:
    """Calculate simplified TRIMP (without resting HR).

    Uses %HRmax instead of HRR.

    TRIMP = duration × (HR_avg / HR_max)²

    Less accurate but useful when resting HR is unknown.

    Args:
        duration_min: Session duration in minutes
        hr_avg: Average heart rate
        hr_max: Maximum heart rate

    Returns:
        Simplified TRIMP value
    """
    if hr_max <= 0:
        return 0.0
    hr_pct = hr_avg / hr_max
    return duration_min * (hr_pct**2)


# =============================================================================
# HEART RATE ZONES
# =============================================================================


def get_hr_zone(hr: int, hr_max: int) -> HRZone:
    """Determine heart rate zone based on %HRmax.

    Args:
        hr: Current heart rate
        hr_max: Maximum heart rate

    Returns:
        HRZone enum value
    """
    if hr_max <= 0:
        return HRZone.ZONE_1

    pct = hr / hr_max

    if pct < 0.60:
        return HRZone.ZONE_1
    if pct < 0.70:
        return HRZone.ZONE_2
    if pct < 0.80:
        return HRZone.ZONE_3
    if pct < 0.90:
        return HRZone.ZONE_4
    return HRZone.ZONE_5


def calculate_zone_boundaries(hr_max: int) -> dict[HRZone, tuple[int, int]]:
    """Calculate HR boundaries for each zone.

    Args:
        hr_max: Maximum heart rate

    Returns:
        Dict mapping zone to (min_hr, max_hr) tuple
    """
    return {
        zone: (
            round(info.hr_min_pct * hr_max),
            round(info.hr_max_pct * hr_max),
        )
        for zone, info in ZONE_DEFINITIONS.items()
    }


def get_zone_info(zone: HRZone) -> ZoneInfo:
    """Get detailed information about a zone.

    Args:
        zone: Heart rate zone

    Returns:
        ZoneInfo with name, description, and boundaries
    """
    return ZONE_DEFINITIONS[zone]


# =============================================================================
# VO2MAX ESTIMATION
# =============================================================================


def estimate_vo2max_hr(
    hr_max: int,
    hr_rest: int,
) -> float:
    """Estimate VO2max from heart rate (Uth method).

    VO2max = 15.3 × (HRmax / HRrest)

    Simple estimation based on heart rate ratio.

    Args:
        hr_max: Maximum heart rate
        hr_rest: Resting heart rate

    Returns:
        Estimated VO2max in ml/kg/min
    """
    if hr_rest <= 0:
        return 0.0
    return 15.3 * (hr_max / hr_rest)


def estimate_vo2max_cooper(distance_km: float) -> float:
    """Estimate VO2max from 12-minute Cooper test.

    VO2max = (distance_m - 504.9) / 44.73

    Args:
        distance_km: Distance covered in 12 minutes (km)

    Returns:
        Estimated VO2max in ml/kg/min
    """
    distance_m = distance_km * 1000
    return (distance_m - 504.9) / 44.73


def estimate_vo2max_running(
    pace_minkm: float,
    hr_avg: int,
    hr_max: int,
    hr_rest: int | None = None,
) -> float:
    """Estimate VO2max from running performance.

    Uses Jack Daniels' formula with HR adjustment.

    Args:
        pace_minkm: Running pace in min/km
        hr_avg: Average heart rate during run
        hr_max: Maximum heart rate
        hr_rest: Resting heart rate (optional, improves accuracy)

    Returns:
        Estimated VO2max in ml/kg/min
    """
    # Convert pace to speed (m/min)
    speed_m_min = 1000 / pace_minkm if pace_minkm > 0 else 0

    # Base VO2 from speed (ACSM running equation)
    # VO2 = 3.5 + 0.2 × speed + 0.9 × speed × grade
    # Simplified for flat running
    vo2_running = 3.5 + 0.2 * speed_m_min

    # Adjust for HR intensity
    if hr_rest:
        hr_ratio = calculate_hr_ratio(hr_avg, hr_max, hr_rest)
    else:
        hr_ratio = hr_avg / hr_max if hr_max > 0 else 0.7

    # Estimated VO2max
    if hr_ratio > 0:
        return vo2_running / hr_ratio
    return vo2_running


# =============================================================================
# EFFICIENCY METRICS
# =============================================================================


def calculate_efficiency_factor(
    pace_minkm: float,
    hr_avg: int,
) -> float:
    """Calculate running efficiency factor (EF).

    EF = pace (sec/km) / HR

    Lower is better. Track over time to monitor fitness.

    Args:
        pace_minkm: Running pace in min/km
        hr_avg: Average heart rate

    Returns:
        Efficiency factor
    """
    if hr_avg <= 0:
        return 0.0
    pace_sec = pace_minkm * 60
    return pace_sec / hr_avg


def calculate_cardiac_drift(
    hr_first_half: int,
    hr_second_half: int,
) -> float:
    """Calculate cardiac drift percentage.

    Cardiac drift = ((HR_second - HR_first) / HR_first) × 100

    Normal: < 5%
    Dehydration/fatigue: > 10%

    Args:
        hr_first_half: Average HR in first half of session
        hr_second_half: Average HR in second half of session

    Returns:
        Cardiac drift as percentage
    """
    if hr_first_half <= 0:
        return 0.0
    return ((hr_second_half - hr_first_half) / hr_first_half) * 100


def calculate_aerobic_decoupling(
    pace_first_half: float,
    pace_second_half: float,
    hr_first_half: int,
    hr_second_half: int,
) -> float:
    """Calculate aerobic decoupling (Pa:HR).

    Measures how well aerobic fitness maintains pace relative to HR.
    Used by TrainingPeaks.

    Decoupling = ((EF_first - EF_second) / EF_first) × 100

    Good aerobic fitness: < 5%
    Needs work: > 5%

    Args:
        pace_first_half: Pace in min/km for first half
        pace_second_half: Pace in min/km for second half
        hr_first_half: Avg HR for first half
        hr_second_half: Avg HR for second half

    Returns:
        Decoupling percentage
    """
    ef_first = calculate_efficiency_factor(pace_first_half, hr_first_half)
    ef_second = calculate_efficiency_factor(pace_second_half, hr_second_half)

    if ef_first <= 0:
        return 0.0

    return ((ef_first - ef_second) / ef_first) * 100


# =============================================================================
# PACE CALCULATIONS
# =============================================================================


def pace_to_speed(pace_minkm: float) -> float:
    """Convert pace (min/km) to speed (km/h).

    Args:
        pace_minkm: Pace in minutes per kilometer

    Returns:
        Speed in km/h
    """
    if pace_minkm <= 0:
        return 0.0
    return 60 / pace_minkm


def speed_to_pace(speed_kmh: float) -> float:
    """Convert speed (km/h) to pace (min/km).

    Args:
        speed_kmh: Speed in km/h

    Returns:
        Pace in min/km
    """
    if speed_kmh <= 0:
        return 0.0
    return 60 / speed_kmh


def format_pace(pace_minkm: float) -> str:
    """Format pace as MM:SS string.

    Args:
        pace_minkm: Pace in minutes per kilometer

    Returns:
        Formatted pace string (e.g., "5:30")
    """
    if pace_minkm <= 0:
        return "0:00"
    minutes = int(pace_minkm)
    seconds = int((pace_minkm - minutes) * 60)
    return f"{minutes}:{seconds:02d}"


def calculate_gap(
    pace_minkm: float,
    elevation_gain_m: float,
    distance_km: float,
) -> float:
    """Calculate Grade Adjusted Pace (GAP).

    Adjusts pace for elevation to compare hilly runs.
    Simple approximation: +6 sec/km per 1% grade

    Args:
        pace_minkm: Actual pace in min/km
        elevation_gain_m: Total elevation gain
        distance_km: Total distance

    Returns:
        GAP in min/km
    """
    if distance_km <= 0:
        return pace_minkm

    # Average grade percentage
    grade_pct = (elevation_gain_m / (distance_km * 1000)) * 100

    # Adjustment: ~6 sec per 1% grade
    adjustment = grade_pct * 0.1  # 0.1 min = 6 sec per 1%

    return max(0.1, pace_minkm - adjustment)
