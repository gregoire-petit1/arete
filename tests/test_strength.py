"""Tests for strength module."""

from arete.features.strength import (
    StrengthZone,
    VBTZone,
    calculate_average_intensity,
    calculate_inol,
    calculate_relative_intensity,
    calculate_session_inol,
    calculate_volume,
    estimate_1rm_average,
    estimate_1rm_brzycki,
    estimate_1rm_epley,
    estimate_1rm_lombardi,
    estimate_1rm_rpe,
    get_strength_zone,
    get_vbt_zone,
    get_zone_boundaries,
    percentage_from_reps,
    weight_for_reps_at_percentage,
    weight_for_target_reps,
)
from arete.strength.models import (
    Exercise,
    ExerciseSet,
    SessionExercise,
    StrengthSession,
)


class TestOneRMEstimation:
    """Tests for 1RM estimation formulas."""

    def test_epley_formula(self) -> None:
        """Epley: 1RM = weight × (1 + reps/30)."""
        # 100kg × 10 reps
        one_rm = estimate_1rm_epley(100, 10)
        assert 130 < one_rm < 135  # ~133

    def test_brzycki_formula(self) -> None:
        """Brzycki: 1RM = weight × 36 / (37 - reps)."""
        one_rm = estimate_1rm_brzycki(100, 10)
        assert 130 < one_rm < 140  # ~133

    def test_lombardi_formula(self) -> None:
        """Lombardi: 1RM = weight × reps^0.10."""
        one_rm = estimate_1rm_lombardi(100, 10)
        assert one_rm > 100

    def test_average_formula(self) -> None:
        """Average of multiple formulas."""
        one_rm = estimate_1rm_average(100, 10)
        assert 125 < one_rm < 140

    def test_rpe_based(self) -> None:
        """RPE-based 1RM estimation."""
        # 100kg × 10 @ RPE 8 (2 RIR) = 12 effective reps
        one_rm = estimate_1rm_rpe(100, 10, rpe=8)
        assert one_rm > estimate_1rm_epley(100, 10)

    def test_single_rep(self) -> None:
        """Single rep = actual 1RM."""
        assert estimate_1rm_epley(100, 1) == 100
        assert estimate_1rm_brzycki(100, 1) == 100

    def test_zero_reps(self) -> None:
        """Zero reps returns zero."""
        assert estimate_1rm_epley(100, 0) == 0
        assert estimate_1rm_brzycki(100, 0) == 0


class TestWeightCalculations:
    """Tests for weight calculations from 1RM."""

    def test_weight_for_percentage(self) -> None:
        """Weight for target percentage."""
        weight = weight_for_reps_at_percentage(one_rm=100, target_pct=0.8)
        assert weight == 80

    def test_weight_for_target_reps(self) -> None:
        """Weight for target reps."""
        # For 10 reps at 100kg 1RM
        weight = weight_for_target_reps(one_rm=100, target_reps=10)
        assert 70 < weight < 80  # ~75kg

    def test_percentage_from_reps(self) -> None:
        """Percentage from rep count."""
        pct = percentage_from_reps(10)
        assert 0.7 < pct < 0.8  # ~75%

        pct_single = percentage_from_reps(1)
        assert pct_single == 1.0


class TestStrengthZones:
    """Tests for strength training zones."""

    def test_technique_zone(self) -> None:
        """Zone 1: 50-65% 1RM."""
        assert get_strength_zone(0.55) == StrengthZone.TECHNIQUE
        assert get_strength_zone(0.64) == StrengthZone.TECHNIQUE

    def test_hypertrophy_zone(self) -> None:
        """Zone 2: 65-75% 1RM."""
        assert get_strength_zone(0.65) == StrengthZone.HYPERTROPHY
        assert get_strength_zone(0.70) == StrengthZone.HYPERTROPHY

    def test_strength_zone(self) -> None:
        """Zone 3: 75-85% 1RM."""
        assert get_strength_zone(0.75) == StrengthZone.STRENGTH
        assert get_strength_zone(0.80) == StrengthZone.STRENGTH

    def test_power_zone(self) -> None:
        """Zone 4: 85-93% 1RM."""
        assert get_strength_zone(0.85) == StrengthZone.POWER
        assert get_strength_zone(0.90) == StrengthZone.POWER

    def test_max_zone(self) -> None:
        """Zone 5: 93-100% 1RM."""
        assert get_strength_zone(0.93) == StrengthZone.MAX
        assert get_strength_zone(1.00) == StrengthZone.MAX

    def test_zone_boundaries(self) -> None:
        """Zone weight boundaries."""
        boundaries = get_zone_boundaries(one_rm=100)
        assert boundaries[StrengthZone.TECHNIQUE] == (50.0, 65.0)
        assert boundaries[StrengthZone.MAX] == (93.0, 100.0)


class TestVBT:
    """Tests for Velocity Based Training."""

    def test_vbt_zones(self) -> None:
        """VBT zone classification."""
        assert get_vbt_zone(1.1) == VBTZone.STARTING_STRENGTH
        assert get_vbt_zone(0.85) == VBTZone.STRENGTH_SPEED
        assert get_vbt_zone(0.6) == VBTZone.POWER
        assert get_vbt_zone(0.4) == VBTZone.ACCELERATIVE_STRENGTH
        assert get_vbt_zone(0.2) == VBTZone.ABSOLUTE_STRENGTH


class TestINOL:
    """Tests for INOL calculation."""

    def test_inol_calculation(self) -> None:
        """INOL = reps / (100 - intensity%)."""
        # 5 reps at 80% = 5 / 20 = 0.25
        inol = calculate_inol(reps=5, intensity_pct=80)
        assert inol == 0.25

    def test_high_intensity_inol(self) -> None:
        """Higher intensity = higher INOL."""
        inol_80 = calculate_inol(5, 80)
        inol_90 = calculate_inol(5, 90)
        assert inol_90 > inol_80


def _session(*exercises: tuple[str, list[tuple[int, float]]]) -> StrengthSession:
    """Build a StrengthSession from (name, [(reps, weight), ...]) tuples."""
    return StrengthSession(
        exercises=[
            SessionExercise(
                exercise=Exercise(name=name),
                sets=[
                    ExerciseSet(set_number=i + 1, reps=reps, weight_kg=weight)
                    for i, (reps, weight) in enumerate(sets)
                ],
            )
            for name, sets in exercises
        ]
    )


class TestSessionMetrics:
    """Session-level metrics on arete.strength.models objects."""

    def test_set_volume(self) -> None:
        assert ExerciseSet(reps=10, weight_kg=100).volume == 1000

    def test_session_volume_and_sets(self) -> None:
        session = _session(("Squat", [(5, 100)] * 3), ("Bench", [(8, 60)] * 3))
        assert session.total_volume == 1500 + 1440
        assert session.total_sets == 6

    def test_session_inol(self) -> None:
        session = _session(("Squat", [(5, 100), (5, 110)]))  # ~71 % and ~79 % of 140
        inol = calculate_session_inol(session, {"squat": 140})
        assert inol is not None and inol > 0

    def test_session_inol_without_known_1rm(self) -> None:
        assert calculate_session_inol(_session(("Squat", [(5, 100)])), {}) is None


class TestIntensityMetrics:
    """Tests for intensity calculations."""

    def test_relative_intensity(self) -> None:
        """Relative intensity = weight / 1RM."""
        ri = calculate_relative_intensity(weight=80, one_rm=100)
        assert ri == 0.8

    def test_average_intensity(self) -> None:
        session = _session(("Squat", [(5, 80)]))
        assert calculate_average_intensity(session, {"squat": 100}) == 0.8

    def test_epley_single_implementation(self) -> None:
        """models.ExerciseSet.estimated_1rm delegates to features.estimate_1rm_epley."""
        assert ExerciseSet(reps=10, weight_kg=100).estimated_1rm == estimate_1rm_epley(
            100, 10
        )


class TestVolume:
    """Tests for volume calculations."""

    def test_simple_volume(self) -> None:
        """Volume = sets × reps × weight."""
        vol = calculate_volume(sets=3, reps=10, weight=100)
        assert vol == 3000
