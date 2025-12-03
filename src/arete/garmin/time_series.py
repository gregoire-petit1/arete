"""Time series data structures and metrics for detailed activity analysis.

Handles extraction, storage, and compression of activity time series data
for efficient LLM analysis while staying within token limits.
"""

from __future__ import annotations

import json
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class LapIntensity(str, Enum):
    """Lap intensity types from Garmin FIT files."""

    WARMUP = "warmup"
    ACTIVE = "active"  # Main work interval
    REST = "rest"  # Recovery between intervals
    COOLDOWN = "cooldown"
    OTHER = "other"

    @classmethod
    def from_fit_value(cls, value: Any) -> LapIntensity:
        """Convert FIT intensity value to enum."""
        if value is None:
            return cls.OTHER

        # FIT SDK intensity values
        value_str = str(value).lower()
        if value_str == "warmup":
            return cls.WARMUP
        elif value_str == "active":
            return cls.ACTIVE
        elif value_str in ("4", "rest", "recovery"):
            return cls.REST
        elif value_str == "cooldown":
            return cls.COOLDOWN
        else:
            return cls.OTHER


@dataclass
class LapData:
    """Data for a single lap/interval from FIT file."""

    lap_number: int
    intensity: LapIntensity
    trigger: str  # 'manual', 'distance', 'time', 'session_end'

    # Timing
    duration_sec: float = 0
    start_time: datetime | None = None

    # Distance/Pace
    distance_m: float = 0
    avg_speed_mps: float | None = None
    max_speed_mps: float | None = None

    # Heart rate
    avg_hr: int | None = None
    max_hr: int | None = None

    # Cadence
    avg_cadence: int | None = None

    # Power (if available)
    avg_power: int | None = None

    # Running dynamics
    avg_stance_time: float | None = None
    avg_vertical_oscillation: float | None = None

    @property
    def duration_min(self) -> float:
        """Duration in minutes."""
        return self.duration_sec / 60.0

    @property
    def distance_km(self) -> float:
        """Distance in kilometers."""
        return self.distance_m / 1000.0

    @property
    def pace_sec_km(self) -> int | None:
        """Average pace in seconds per km."""
        if self.avg_speed_mps and self.avg_speed_mps > 0.5:
            return int(1000 / self.avg_speed_mps)
        return None

    @property
    def pace_str(self) -> str:
        """Pace as MM:SS string."""
        pace = self.pace_sec_km
        if pace is None:
            return "N/A"
        return f"{pace // 60}:{pace % 60:02d}"

    def to_compact_dict(self) -> dict[str, Any]:
        """Convert to compact dict for JSON."""
        d: dict[str, Any] = {
            "n": self.lap_number,
            "type": self.intensity.value,
            "dur": f"{self.duration_min:.1f}m",
        }
        if self.distance_m > 100:
            d["dist"] = f"{self.distance_km:.2f}km"
        if self.pace_sec_km:
            d["pace"] = self.pace_str
        if self.avg_hr:
            d["hr"] = self.avg_hr
        if self.avg_cadence:
            d["cad"] = self.avg_cadence
        return d


@dataclass
class WorkoutStructure:
    """Analyzed workout structure with grouped laps."""

    laps: list[LapData] = field(default_factory=list)

    # Grouped phases
    warmup_laps: list[LapData] = field(default_factory=list)
    work_intervals: list[LapData] = field(default_factory=list)
    rest_intervals: list[LapData] = field(default_factory=list)
    cooldown_laps: list[LapData] = field(default_factory=list)

    # Interval analysis
    is_interval_workout: bool = False
    num_work_intervals: int = 0
    avg_work_duration_sec: float = 0
    avg_rest_duration_sec: float = 0

    # Consistency metrics
    work_pace_consistency_cv: float | None = None  # CV of paces across work intervals
    work_hr_progression: float | None = None  # HR drift across work intervals

    def analyze(self) -> None:
        """Analyze the workout structure and calculate metrics."""
        if not self.laps:
            return

        # Group laps by intensity
        for lap in self.laps:
            if lap.intensity == LapIntensity.WARMUP:
                self.warmup_laps.append(lap)
            elif lap.intensity == LapIntensity.ACTIVE:
                self.work_intervals.append(lap)
            elif lap.intensity == LapIntensity.REST:
                self.rest_intervals.append(lap)
            elif lap.intensity == LapIntensity.COOLDOWN:
                self.cooldown_laps.append(lap)

        # Determine if this is an interval workout
        self.num_work_intervals = len(self.work_intervals)
        self.is_interval_workout = (
            self.num_work_intervals >= 2 and len(self.rest_intervals) >= 1
        )

        if self.is_interval_workout:
            # Calculate averages
            if self.work_intervals:
                self.avg_work_duration_sec = statistics.mean(
                    [lap.duration_sec for lap in self.work_intervals]
                )
            if self.rest_intervals:
                self.avg_rest_duration_sec = statistics.mean(
                    [lap.duration_sec for lap in self.rest_intervals]
                )

            # Pace consistency across work intervals
            work_paces = [
                lap.pace_sec_km for lap in self.work_intervals if lap.pace_sec_km
            ]
            if len(work_paces) >= 2:
                avg_pace = statistics.mean(work_paces)
                std_pace = statistics.stdev(work_paces)
                self.work_pace_consistency_cv = (
                    (std_pace / avg_pace) * 100 if avg_pace else None
                )

            # HR progression (first vs last work interval)
            work_hrs = [lap.avg_hr for lap in self.work_intervals if lap.avg_hr]
            if len(work_hrs) >= 2:
                first_hr = work_hrs[0]
                last_hr = work_hrs[-1]
                self.work_hr_progression = ((last_hr - first_hr) / first_hr) * 100

    def to_compact_json(self) -> str:
        """Convert to compact JSON for LLM."""
        if not self.is_interval_workout:
            # Simple workout - just show laps
            return json.dumps(
                {
                    "laps": [
                        lap.to_compact_dict() for lap in self.laps[:10]
                    ],  # Max 10 laps
                },
                separators=(",", ":"),
            )

        # Interval workout - show structure
        data: dict[str, Any] = {
            "type": "intervals",
            "structure": f"{self.num_work_intervals}x work + rest",
        }

        # Warmup summary
        if self.warmup_laps:
            total_warmup = sum(lap.duration_sec for lap in self.warmup_laps)
            data["warmup"] = f"{total_warmup / 60:.0f}min"

        # Work intervals detail
        data["intervals"] = []
        for i, lap in enumerate(self.work_intervals):
            interval_data = {
                "n": i + 1,
                "dur": f"{lap.duration_min:.1f}m",
                "pace": lap.pace_str,
                "hr": lap.avg_hr,
            }
            if lap.avg_cadence:
                interval_data["cad"] = lap.avg_cadence
            data["intervals"].append(interval_data)

        # Rest summary
        if self.rest_intervals:
            data["rest_avg"] = f"{self.avg_rest_duration_sec / 60:.1f}min"

        # Consistency metrics
        if self.work_pace_consistency_cv is not None:
            data["pace_cv%"] = round(self.work_pace_consistency_cv, 1)
        if self.work_hr_progression is not None:
            data["hr_drift%"] = round(self.work_hr_progression, 1)

        # Cooldown
        if self.cooldown_laps:
            total_cooldown = sum(lap.duration_sec for lap in self.cooldown_laps)
            data["cooldown"] = f"{total_cooldown / 60:.0f}min"

        return json.dumps(data, separators=(",", ":"))

    def get_summary(self) -> str:
        """Get human-readable summary."""
        if not self.is_interval_workout:
            return f"Simple workout: {len(self.laps)} laps"

        work_paces = [lap.pace_str for lap in self.work_intervals]
        return (
            f"Interval workout: {self.num_work_intervals}x "
            f"{self.avg_work_duration_sec / 60:.0f}min work / "
            f"{self.avg_rest_duration_sec / 60:.0f}min rest. "
            f"Paces: {', '.join(work_paces)}"
        )


@dataclass
class TimeSeriesPoint:
    """Single point in activity time series."""

    timestamp: datetime
    elapsed_sec: int = 0

    # Core metrics
    heart_rate: int | None = None
    speed_mps: float | None = None  # meters per second
    cadence: int | None = None  # steps per minute (running) or rpm (cycling)
    power: int | None = None  # watts
    altitude: float | None = None  # meters

    # Running dynamics (HRM-Pro)
    stance_time: float | None = None  # ms
    stance_time_balance: float | None = None  # % left
    step_length: float | None = None  # mm
    vertical_oscillation: float | None = None  # mm
    vertical_ratio: float | None = None  # %

    # GPS
    lat: float | None = None
    lon: float | None = None


@dataclass
class TimeSeriesData:
    """Complete time series data from an activity."""

    points: list[TimeSeriesPoint] = field(default_factory=list)
    sample_rate_sec: float = 1.0  # Typical FIT sample rate

    @property
    def duration_sec(self) -> int:
        """Total duration based on points."""
        if not self.points:
            return 0
        return self.points[-1].elapsed_sec

    @property
    def heart_rates(self) -> list[int]:
        """All HR values (non-null)."""
        return [p.heart_rate for p in self.points if p.heart_rate]

    @property
    def speeds(self) -> list[float]:
        """All speed values (non-null)."""
        return [p.speed_mps for p in self.points if p.speed_mps]

    @property
    def cadences(self) -> list[int]:
        """All cadence values (non-null)."""
        return [p.cadence for p in self.points if p.cadence]

    @property
    def altitudes(self) -> list[float]:
        """All altitude values (non-null)."""
        return [p.altitude for p in self.points if p.altitude is not None]

    @property
    def powers(self) -> list[int]:
        """All power values (non-null)."""
        return [p.power for p in self.points if p.power]

    def has_running_dynamics(self) -> bool:
        """Check if running dynamics data is available."""
        return any(p.stance_time is not None for p in self.points)

    def has_power(self) -> bool:
        """Check if power data is available."""
        return any(p.power is not None for p in self.points)


@dataclass
class DerivedMetrics:
    """Computed metrics from time series analysis.

    These are the compressed, meaningful metrics we send to the LLM.
    """

    # HR Analysis
    hr_avg: float | None = None
    hr_max: int | None = None
    hr_min: int | None = None
    hr_std: float | None = None  # Variability
    hr_drift_pct: float | None = None  # First half vs second half avg
    hr_decoupling_pct: float | None = None  # HR:pace ratio drift

    # Pace Analysis
    pace_avg_sec_km: int | None = None
    pace_std_sec_km: int | None = None  # Variability
    pace_cv: float | None = None  # Coefficient of variation (stability)
    pace_first_half_sec_km: int | None = None
    pace_second_half_sec_km: int | None = None
    pace_fade_pct: float | None = None  # Negative split vs positive split

    # Cadence Analysis
    cadence_avg: int | None = None
    cadence_std: float | None = None
    cadence_cv: float | None = None  # Stability indicator

    # Power Analysis (if available)
    power_avg: int | None = None
    power_normalized: int | None = None
    power_variability_index: float | None = None  # NP/Avg

    # Running Dynamics (if available)
    stance_time_avg: float | None = None
    stance_time_drift_pct: float | None = None  # Fatigue indicator
    step_length_avg: float | None = None
    step_length_drift_pct: float | None = None
    vertical_oscillation_avg: float | None = None
    vertical_ratio_avg: float | None = None
    ground_contact_balance: float | None = None  # Asymmetry

    # Elevation Impact
    total_ascent: float | None = None
    total_descent: float | None = None
    avg_grade_pct: float | None = None
    pace_vs_elevation_correlation: float | None = None  # How much hills slow you

    # Splits (5 equal segments)
    splits: list[dict[str, Any]] = field(default_factory=list)

    # Anomalies detected
    anomalies: list[str] = field(default_factory=list)

    def to_compact_json(self) -> str:
        """Convert to compact JSON for LLM prompt (~300 tokens max)."""
        data: dict[str, Any] = {}

        # HR section
        if self.hr_avg:
            data["hr"] = {
                "avg": round(self.hr_avg),
                "max": self.hr_max,
                "drift%": round(self.hr_drift_pct, 1) if self.hr_drift_pct else None,
                "decoupling%": round(self.hr_decoupling_pct, 1)
                if self.hr_decoupling_pct
                else None,
            }

        # Pace section
        if self.pace_avg_sec_km:
            data["pace"] = {
                "avg": self._sec_to_pace(self.pace_avg_sec_km),
                "cv%": round(self.pace_cv * 100, 1) if self.pace_cv else None,
                "fade%": round(self.pace_fade_pct, 1) if self.pace_fade_pct else None,
            }

        # Cadence
        if self.cadence_avg:
            data["cadence"] = {
                "avg": self.cadence_avg,
                "cv%": round(self.cadence_cv * 100, 1) if self.cadence_cv else None,
            }

        # Power
        if self.power_avg:
            data["power"] = {
                "avg": self.power_avg,
                "np": self.power_normalized,
                "vi": round(self.power_variability_index, 2)
                if self.power_variability_index
                else None,
            }

        # Running dynamics
        if self.stance_time_avg:
            data["dynamics"] = {
                "stance_ms": round(self.stance_time_avg),
                "stance_drift%": round(self.stance_time_drift_pct, 1)
                if self.stance_time_drift_pct
                else None,
                "step_mm": round(self.step_length_avg)
                if self.step_length_avg
                else None,
                "vert_osc_mm": round(self.vertical_oscillation_avg, 1)
                if self.vertical_oscillation_avg
                else None,
                "vert_ratio%": round(self.vertical_ratio_avg, 1)
                if self.vertical_ratio_avg
                else None,
                "balance%": round(self.ground_contact_balance, 1)
                if self.ground_contact_balance
                else None,
            }

        # Elevation
        if self.total_ascent and self.total_ascent > 10:
            data["elevation"] = {
                "ascent_m": round(self.total_ascent),
                "descent_m": round(self.total_descent) if self.total_descent else None,
                "impact": round(self.pace_vs_elevation_correlation, 2)
                if self.pace_vs_elevation_correlation
                else None,
            }

        # Splits (simplified)
        if self.splits:
            data["splits"] = [
                {
                    "km": s.get("km"),
                    "pace": self._sec_to_pace(s.get("pace_sec_km")),
                    "hr": s.get("hr_avg"),
                }
                for s in self.splits[:5]  # Max 5 splits
            ]

        # Anomalies
        if self.anomalies:
            data["anomalies"] = self.anomalies[:3]  # Max 3

        return json.dumps(data, separators=(",", ":"))

    @staticmethod
    def _sec_to_pace(sec: int | None) -> str | None:
        """Convert seconds per km to MM:SS string."""
        if sec is None:
            return None
        minutes = sec // 60
        seconds = sec % 60
        return f"{minutes}:{seconds:02d}"


class ActivityMetricsCalculator:
    """Calculate derived metrics from time series data.

    Compresses raw data into meaningful, LLM-friendly metrics.
    """

    def calculate(self, ts: TimeSeriesData) -> DerivedMetrics:
        """Calculate all derived metrics from time series.

        Args:
            ts: Time series data from activity

        Returns:
            DerivedMetrics with computed values
        """
        metrics = DerivedMetrics()

        # HR metrics
        hrs = ts.heart_rates
        if hrs:
            metrics.hr_avg = statistics.mean(hrs)
            metrics.hr_max = max(hrs)
            metrics.hr_min = min(hrs)
            metrics.hr_std = statistics.stdev(hrs) if len(hrs) > 1 else 0
            metrics.hr_drift_pct = self._calculate_drift(hrs)

        # Pace metrics
        speeds = ts.speeds
        if speeds:
            paces = [int(1000 / s) for s in speeds if s > 0.5]  # Filter walking
            if paces:
                metrics.pace_avg_sec_km = int(statistics.mean(paces))
                metrics.pace_std_sec_km = (
                    int(statistics.stdev(paces)) if len(paces) > 1 else 0
                )
                metrics.pace_cv = (
                    metrics.pace_std_sec_km / metrics.pace_avg_sec_km
                    if metrics.pace_avg_sec_km
                    else None
                )

                # Pace fade (positive = slowing down)
                mid = len(paces) // 2
                if mid > 0:
                    first_half = statistics.mean(paces[:mid])
                    second_half = statistics.mean(paces[mid:])
                    metrics.pace_first_half_sec_km = int(first_half)
                    metrics.pace_second_half_sec_km = int(second_half)
                    metrics.pace_fade_pct = (
                        (second_half - first_half) / first_half
                    ) * 100

        # HR:Pace decoupling
        if hrs and speeds and len(hrs) == len(speeds):
            metrics.hr_decoupling_pct = self._calculate_decoupling(hrs, speeds)

        # Cadence metrics
        cadences = ts.cadences
        if cadences:
            metrics.cadence_avg = int(statistics.mean(cadences))
            metrics.cadence_std = statistics.stdev(cadences) if len(cadences) > 1 else 0
            metrics.cadence_cv = (
                metrics.cadence_std / metrics.cadence_avg
                if metrics.cadence_avg
                else None
            )

        # Power metrics
        powers = ts.powers
        if powers:
            metrics.power_avg = int(statistics.mean(powers))
            # Normalized power (simplified: 30-sec rolling avg, then 4th power average)
            np = self._calculate_normalized_power(powers)
            if np:
                metrics.power_normalized = np
                metrics.power_variability_index = (
                    np / metrics.power_avg if metrics.power_avg else None
                )

        # Running dynamics
        if ts.has_running_dynamics():
            self._calculate_running_dynamics(ts, metrics)

        # Elevation analysis
        alts = ts.altitudes
        if alts and len(alts) > 10:
            self._calculate_elevation_metrics(ts, metrics)

        # Splits (5 equal parts)
        metrics.splits = self._calculate_splits(ts, num_splits=5)

        # Detect anomalies
        metrics.anomalies = self._detect_anomalies(ts, metrics)

        return metrics

    def _calculate_drift(self, values: list) -> float:
        """Calculate drift % between first and second half."""
        if len(values) < 10:
            return 0.0
        mid = len(values) // 2
        first_avg = statistics.mean(values[:mid])
        second_avg = statistics.mean(values[mid:])
        if first_avg == 0:
            return 0.0
        return ((second_avg - first_avg) / first_avg) * 100

    def _calculate_decoupling(self, hrs: list[int], speeds: list[float]) -> float:
        """Calculate HR:Pace decoupling (aerobic efficiency indicator).

        Decoupling > 5% suggests aerobic fatigue / glycogen depletion.
        """
        if len(hrs) < 20:
            return 0.0

        mid = len(hrs) // 2

        # First half ratio
        hr1 = statistics.mean(hrs[:mid])
        pace1 = statistics.mean([1000 / s for s in speeds[:mid] if s > 0.5])

        # Second half ratio
        hr2 = statistics.mean(hrs[mid:])
        pace2 = statistics.mean([1000 / s for s in speeds[mid:] if s > 0.5])

        if pace1 == 0 or pace2 == 0:
            return 0.0

        ratio1 = hr1 / pace1
        ratio2 = hr2 / pace2

        return ((ratio2 - ratio1) / ratio1) * 100

    def _calculate_normalized_power(
        self, powers: list[int], window: int = 30
    ) -> int | None:
        """Calculate Normalized Power (cycling/running power metric)."""
        if len(powers) < window:
            return None

        # Rolling 30-sec average
        rolling = []
        for i in range(len(powers) - window + 1):
            rolling.append(statistics.mean(powers[i : i + window]))

        # 4th power average, then 4th root
        fourth_powers = [p**4 for p in rolling]
        np = (statistics.mean(fourth_powers)) ** 0.25

        return int(np)

    def _calculate_running_dynamics(
        self, ts: TimeSeriesData, metrics: DerivedMetrics
    ) -> None:
        """Calculate running dynamics metrics."""
        stance_times = [p.stance_time for p in ts.points if p.stance_time]
        step_lengths = [p.step_length for p in ts.points if p.step_length]
        vert_oscs = [
            p.vertical_oscillation for p in ts.points if p.vertical_oscillation
        ]
        vert_ratios = [p.vertical_ratio for p in ts.points if p.vertical_ratio]
        balances = [p.stance_time_balance for p in ts.points if p.stance_time_balance]

        if stance_times:
            metrics.stance_time_avg = statistics.mean(stance_times)
            metrics.stance_time_drift_pct = self._calculate_drift(stance_times)

        if step_lengths:
            metrics.step_length_avg = statistics.mean(step_lengths)
            metrics.step_length_drift_pct = self._calculate_drift(step_lengths)

        if vert_oscs:
            metrics.vertical_oscillation_avg = statistics.mean(vert_oscs)

        if vert_ratios:
            metrics.vertical_ratio_avg = statistics.mean(vert_ratios)

        if balances:
            metrics.ground_contact_balance = statistics.mean(balances)

    def _calculate_elevation_metrics(
        self, ts: TimeSeriesData, metrics: DerivedMetrics
    ) -> None:
        """Calculate elevation impact metrics."""
        alts = ts.altitudes
        speeds = ts.speeds

        # Total ascent/descent
        ascent = 0.0
        descent = 0.0
        for i in range(1, len(alts)):
            diff = alts[i] - alts[i - 1]
            if diff > 0:
                ascent += diff
            else:
                descent += abs(diff)

        metrics.total_ascent = ascent
        metrics.total_descent = descent

        # Correlation between altitude change and pace
        if len(alts) == len(speeds) and len(alts) > 20:
            try:
                # Calculate altitude changes and corresponding paces
                alt_changes = [alts[i] - alts[i - 1] for i in range(1, len(alts))]
                pace_values = [1000 / s if s > 0.5 else 0 for s in speeds[1:]]

                # Simple correlation
                if alt_changes and pace_values:
                    metrics.pace_vs_elevation_correlation = self._pearson_correlation(
                        alt_changes, pace_values
                    )
            except Exception:
                pass

    def _pearson_correlation(self, x: list, y: list) -> float:
        """Calculate Pearson correlation coefficient."""
        n = len(x)
        if n < 3:
            return 0.0

        mean_x = sum(x) / n
        mean_y = sum(y) / n

        numerator = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
        denom_x = sum((xi - mean_x) ** 2 for xi in x) ** 0.5
        denom_y = sum((yi - mean_y) ** 2 for yi in y) ** 0.5

        if denom_x * denom_y == 0:
            return 0.0

        return numerator / (denom_x * denom_y)

    def _calculate_splits(self, ts: TimeSeriesData, num_splits: int = 5) -> list[dict]:
        """Calculate per-km or equal splits."""
        if not ts.points:
            return []

        splits = []
        points_per_split = len(ts.points) // num_splits

        for i in range(num_splits):
            start = i * points_per_split
            end = (i + 1) * points_per_split if i < num_splits - 1 else len(ts.points)
            segment = ts.points[start:end]

            if not segment:
                continue

            hrs = [p.heart_rate for p in segment if p.heart_rate]
            speeds = [p.speed_mps for p in segment if p.speed_mps and p.speed_mps > 0.5]

            split_data = {"km": i + 1}
            if hrs:
                split_data["hr_avg"] = int(statistics.mean(hrs))
            if speeds:
                avg_pace = int(1000 / statistics.mean(speeds))
                split_data["pace_sec_km"] = avg_pace

            splits.append(split_data)

        return splits

    def _detect_anomalies(
        self, ts: TimeSeriesData, metrics: DerivedMetrics
    ) -> list[str]:
        """Detect notable patterns or issues."""
        anomalies = []

        # HR drift > 10% suggests poor pacing or fatigue
        if metrics.hr_drift_pct and metrics.hr_drift_pct > 10:
            anomalies.append(
                f"HR drift élevé ({metrics.hr_drift_pct:.0f}%): fatigue ou pacing"
            )

        # Decoupling > 5% suggests aerobic fatigue
        if metrics.hr_decoupling_pct and metrics.hr_decoupling_pct > 5:
            anomalies.append(
                f"Découplage cardiaque ({metrics.hr_decoupling_pct:.0f}%): efficacité aérobie réduite"
            )

        # Pace fade > 5% suggests pacing issue
        if metrics.pace_fade_pct and metrics.pace_fade_pct > 5:
            anomalies.append(
                f"Allure en baisse ({metrics.pace_fade_pct:.0f}%): départ trop rapide?"
            )

        # Cadence variability high
        if metrics.cadence_cv and metrics.cadence_cv > 0.1:
            anomalies.append("Cadence instable: travaillez la régularité")

        # Stance time drift (fatigue indicator)
        if metrics.stance_time_drift_pct and metrics.stance_time_drift_pct > 8:
            anomalies.append(
                f"Temps de contact augmente ({metrics.stance_time_drift_pct:.0f}%): fatigue musculaire"
            )

        # Asymmetry
        if metrics.ground_contact_balance:
            deviation = abs(50 - metrics.ground_contact_balance)
            if deviation > 3:
                side = "gauche" if metrics.ground_contact_balance > 50 else "droit"
                anomalies.append(f"Asymétrie foulée ({deviation:.1f}% vers {side})")

        return anomalies
