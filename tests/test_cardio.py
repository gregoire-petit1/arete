"""Tests for cardio module."""

import pytest

from arete.features.cardio import (
    HRZone,
    Sex,
    ZoneDistribution,
    calculate_aerobic_decoupling,
    calculate_cardiac_drift,
    calculate_efficiency_factor,
    calculate_gap,
    calculate_hr_ratio,
    calculate_trimp,
    calculate_trimp_simplified,
    calculate_zone_boundaries,
    estimate_hrmax_gulati,
    estimate_hrmax_tanaka,
    estimate_hrmax_traditional,
    estimate_vo2max_cooper,
    estimate_vo2max_hr,
    format_pace,
    get_hr_zone,
    pace_to_speed,
    speed_to_pace,
)


class TestHRMax:
    """Tests for HR max estimation."""

    def test_tanaka_formula(self) -> None:
        """Tanaka: HRmax = 208 - 0.7 × age."""
        assert estimate_hrmax_tanaka(30) == 187
        assert estimate_hrmax_tanaka(40) == 180
        assert estimate_hrmax_tanaka(50) == 173

    def test_traditional_formula(self) -> None:
        """Traditional: HRmax = 220 - age."""
        assert estimate_hrmax_traditional(30) == 190
        assert estimate_hrmax_traditional(40) == 180

    def test_gulati_formula(self) -> None:
        """Gulati (women): HRmax = 206 - 0.88 × age."""
        assert estimate_hrmax_gulati(30) == 180
        assert estimate_hrmax_gulati(40) == 171


class TestTRIMP:
    """Tests for TRIMP calculation."""

    def test_trimp_basic(self) -> None:
        """TRIMP calculation gives positive value."""
        trimp = calculate_trimp(
            duration_min=60,
            hr_avg=150,
            hr_max=190,
            hr_rest=60,
            sex=Sex.MALE,
        )
        assert trimp > 0
        assert trimp < 500  # Reasonable range

    def test_trimp_higher_intensity(self) -> None:
        """Higher intensity gives higher TRIMP."""
        trimp_low = calculate_trimp(60, 120, 190, 60, Sex.MALE)
        trimp_high = calculate_trimp(60, 170, 190, 60, Sex.MALE)
        assert trimp_high > trimp_low

    def test_trimp_simplified(self) -> None:
        """Simplified TRIMP without resting HR."""
        trimp = calculate_trimp_simplified(60, 150, 190)
        assert trimp > 0

    def test_hr_ratio(self) -> None:
        """Heart rate ratio calculation."""
        ratio = calculate_hr_ratio(hr_avg=150, hr_max=190, hr_rest=60)
        # (150 - 60) / (190 - 60) = 90/130 ≈ 0.69
        assert 0.68 < ratio < 0.70


class TestHRZones:
    """Tests for heart rate zones."""

    def test_zone_1(self) -> None:
        """Zone 1: < 60% HRmax."""
        assert get_hr_zone(hr=100, hr_max=190) == HRZone.ZONE_1

    def test_zone_2(self) -> None:
        """Zone 2: 60-70% HRmax."""
        assert get_hr_zone(hr=120, hr_max=190) == HRZone.ZONE_2

    def test_zone_3(self) -> None:
        """Zone 3: 70-80% HRmax."""
        assert get_hr_zone(hr=145, hr_max=190) == HRZone.ZONE_3

    def test_zone_4(self) -> None:
        """Zone 4: 80-90% HRmax."""
        assert get_hr_zone(hr=165, hr_max=190) == HRZone.ZONE_4

    def test_zone_5(self) -> None:
        """Zone 5: 90-100% HRmax."""
        assert get_hr_zone(hr=175, hr_max=190) == HRZone.ZONE_5

    def test_zone_boundaries(self) -> None:
        """Zone boundaries are calculated correctly."""
        boundaries = calculate_zone_boundaries(hr_max=200)
        assert boundaries[HRZone.ZONE_1] == (100, 120)  # 50-60%
        assert boundaries[HRZone.ZONE_2] == (120, 140)  # 60-70%


class TestVO2Max:
    """Tests for VO2max estimation."""

    def test_vo2max_hr(self) -> None:
        """VO2max from HR ratio."""
        vo2max = estimate_vo2max_hr(hr_max=190, hr_rest=60)
        # 15.3 × (190/60) ≈ 48.5
        assert 48 < vo2max < 49

    def test_vo2max_cooper(self) -> None:
        """VO2max from Cooper test."""
        # 3km in 12 min is decent
        vo2max = estimate_vo2max_cooper(distance_km=3.0)
        assert vo2max > 50


class TestEfficiency:
    """Tests for efficiency metrics."""

    def test_efficiency_factor(self) -> None:
        """Efficiency factor = pace(sec) / HR."""
        ef = calculate_efficiency_factor(pace_minkm=5.0, hr_avg=150)
        # (5 × 60) / 150 = 2.0
        assert ef == 2.0

    def test_cardiac_drift(self) -> None:
        """Cardiac drift percentage."""
        drift = calculate_cardiac_drift(hr_first_half=140, hr_second_half=150)
        # ((150-140)/140) × 100 ≈ 7.1%
        assert 7.0 < drift < 7.2

    def test_aerobic_decoupling(self) -> None:
        """Aerobic decoupling (Pa:HR)."""
        decoupling = calculate_aerobic_decoupling(
            pace_first_half=5.0,
            pace_second_half=5.0,
            hr_first_half=140,
            hr_second_half=150,
        )
        # EF changes due to HR increase
        assert decoupling > 0


class TestPace:
    """Tests for pace conversions."""

    def test_pace_to_speed(self) -> None:
        """Pace to speed conversion."""
        assert pace_to_speed(5.0) == 12.0  # 5 min/km = 12 km/h
        assert pace_to_speed(6.0) == 10.0  # 6 min/km = 10 km/h

    def test_speed_to_pace(self) -> None:
        """Speed to pace conversion."""
        assert speed_to_pace(12.0) == 5.0
        assert speed_to_pace(10.0) == 6.0

    def test_format_pace(self) -> None:
        """Format pace as MM:SS."""
        assert format_pace(5.0) == "5:00"
        assert format_pace(5.5) == "5:30"
        assert format_pace(4.25) == "4:15"

    def test_gap_calculation(self) -> None:
        """Grade Adjusted Pace."""
        # Uphill run should have faster GAP than actual
        gap = calculate_gap(
            pace_minkm=6.0,
            elevation_gain_m=200,
            distance_km=5.0,
        )
        assert gap < 6.0  # GAP should be faster


class TestZoneDistribution:
    """Tests for zone distribution."""

    def test_total_time(self) -> None:
        """Total time is sum of all zones."""
        dist = ZoneDistribution(
            zone_1_min=10,
            zone_2_min=30,
            zone_3_min=15,
            zone_4_min=5,
            zone_5_min=0,
        )
        assert dist.total_min == 60

    def test_percentages(self) -> None:
        """Percentages sum to 100."""
        dist = ZoneDistribution(
            zone_1_min=10,
            zone_2_min=30,
            zone_3_min=15,
            zone_4_min=5,
            zone_5_min=0,
        )
        pcts = dist.as_percentages()
        total = sum(pcts.values())
        assert abs(total - 100) < 0.1
