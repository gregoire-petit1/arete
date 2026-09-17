"""Card builders: the numbers, the deltas and the gap-filled series."""

from __future__ import annotations

import json
from datetime import date, timedelta

from arete.features.fitness import DailyTSS
from arete.features.overview import (
    build_health_card,
    build_pace_card,
    build_pmc_card,
    build_recovery_cards,
    build_sports_card,
    build_volume_card,
    build_zones_card,
    empty_card,
    format_duration,
    format_hms,
    format_pace,
    headline,
)
from arete.features.periods import resolve_period

TODAY = date(2026, 6, 30)
RUNNING = ("running", "trail_running")


def window(period: str = "30d"):
    return resolve_period(period, TODAY)


class TestFormatting:
    def test_pace(self):
        assert format_pace(285) == "4:45 /km"
        assert format_pace(None) == "—"
        assert format_pace(0) == "—"

    def test_hms_switches_to_hours(self):
        assert format_hms(1235) == "20:35"
        assert format_hms(5535) == "1:32:15"
        assert format_hms(None) == "—"

    def test_duration(self):
        assert format_duration(1800) == "30 min"
        assert format_duration(5400) == "1h30"

    def test_headline_delta(self):
        h = headline(120.0, "km", "120 km", 100.0, "up")
        assert h["delta"] == 20.0
        assert h["delta_pct"] == 20.0
        assert headline(None, "km", "—")["delta"] is None
        assert headline(10.0, "km", "10 km", 0.0)["delta_pct"] is None


class TestVolumeCard:
    def rows(self):
        return [
            (TODAY - timedelta(days=2), "running", 3600, 12000.0),
            (TODAY - timedelta(days=5), "strength", 2700, None),
            (TODAY - timedelta(days=40), "running", 3600, 10000.0),  # previous window
        ]

    def test_headline_counts_running_km_only(self):
        card = build_volume_card(self.rows(), window(), RUNNING)
        assert card["headline"]["value"] == 12.0
        assert card["headline"]["previous"] == 10.0
        assert card["secondary"][0]["value"] == 1.8  # hours, all sports

    def test_series_is_gap_filled(self):
        card = build_volume_card(self.rows(), window(), RUNNING)
        assert len(card["series"]) == 30
        assert card["series"][0]["km"] == 0.0
        assert sum(p["km"] for p in card["series"]) == 12.0

    def test_no_sessions(self):
        card = build_volume_card([], window(), RUNNING)
        assert card["headline"]["value"] == 0.0
        assert "Aucune séance" in card["insight"]["text"]


class TestPmcCard:
    def series(self):
        start = TODAY - timedelta(days=60)
        return [
            (DailyTSS(date=start + timedelta(days=i), tss=50.0), 40.0 + i, 35.0 + i)
            for i in range(61)
        ]

    def test_headline_is_latest_ctl(self):
        card = build_pmc_card(self.series(), window(), 1.1, "optimal")
        assert card["headline"]["value"] == 100.0  # 40 + 60
        assert card["secondary"][0]["value"] == 5.0  # tsb = ctl - atl
        assert card["secondary"][2]["value"] == 1.1

    def test_previous_state_taken_at_prev_end(self):
        card = build_pmc_card(self.series(), window(), None, None)
        assert card["headline"]["previous"] == 70.0  # day 30 of the series

    def test_empty_series(self):
        card = build_pmc_card([], window(), None, None)
        assert card["headline"]["value"] == 0.0
        assert len(card["series"]) == 30


class TestZonesCard:
    def rows(self):
        easy = json.dumps({"Z1": 1800, "Z2": 3600, "Z3": 600, "Z4": 300, "Z5": 0})
        return [(TODAY - timedelta(days=1), easy)]

    def test_zone_names_are_case_insensitive(self):
        card = build_zones_card(self.rows(), window())
        assert card["headline"]["value"] == 85.7
        assert card["secondary"][0]["value"] == 4.8

    def test_percentages_in_series(self):
        card = build_zones_card(self.rows(), window())
        day = next(p for p in card["series"] if p["total_min"])
        assert day["z2"] == 60
        assert day["z2_pct"] == 57.1

    def test_no_hr_data(self):
        card = build_zones_card([], window())
        assert card["headline"]["value"] is None
        assert "Pas assez" in card["insight"]["text"]


class TestSportsCard:
    def test_top_sport_share(self):
        card = build_sports_card(
            [("running", 6.0, 4), ("strength", 2.0, 2)], [("running", 4.0, 3)]
        )
        assert card["headline"]["value"] == 8.0
        assert card["headline"]["previous"] == 4.0
        assert card["secondary"][0]["value"] == 75.0
        assert card["series"][0]["sport"] == "running"

    def test_empty(self):
        card = build_sports_card([], [])
        assert card["secondary"][0]["display"] == "—"
        assert "Aucune séance" in card["insight"]["text"]


class TestPaceCard:
    def rows(self):
        return [
            (TODAY - timedelta(days=i * 3), 300 - i, 8000.0, 2400) for i in range(8)
        ]

    def test_median_and_trend(self):
        card = build_pace_card(self.rows(), window("90d"))
        assert card["secondary"][0]["value"] == 296.5
        assert card["headline"]["value"] is not None  # slope computed

    def test_outliers_dropped(self):
        rows = [
            (TODAY - timedelta(days=1), 60, 8000.0, 2400),  # too fast
            (TODAY - timedelta(days=2), 300, 500.0, 200),  # too short
            (TODAY - timedelta(days=3), 300, 8000.0, 2400),
        ]
        card = build_pace_card(rows, window())
        assert card["secondary"][0]["value"] == 300.0
        assert "Trop peu de sorties (1)" in card["insight"]["text"]

    def test_empty(self):
        card = build_pace_card([], window())
        assert card["headline"]["value"] is None
        assert len(card["series"]) == 30


class TestRecoveryCards:
    def days(self):
        return [
            {
                "date": (TODAY - timedelta(days=i)).isoformat(),
                "readiness_score": 70 + i,
                "hrv_last_night": 60,
                "sleep_duration_sec": 25200,
                "sleep_score": 80,
                "resting_hr": 48,
            }
            for i in range(40)
        ]

    def test_four_cards(self):
        cards = build_recovery_cards(self.days(), window())
        assert set(cards) == {"readiness", "hrv", "sleep", "resting_hr"}
        assert cards["hrv"]["headline"]["value"] == 60.0
        assert cards["resting_hr"]["headline"]["better"] == "down"

    def test_mean_against_previous_window(self):
        cards = build_recovery_cards(self.days(), window())
        readiness = cards["readiness"]["headline"]
        assert readiness["value"] == 84.5  # mean of 70..99 over 30 days
        assert readiness["previous"] == 104.5  # only 10 days of previous window

    def test_missing_values_ignored(self):
        days = [
            {"date": TODAY.isoformat(), "readiness_score": None},
            {"date": (TODAY - timedelta(days=1)).isoformat(), "readiness_score": 80},
        ]
        card = build_health_card(
            days,
            window(),
            "readiness_score",
            "pts",
            "up",
            lambda mean, prev: {"text": "", "tone": "neutral"},
        )
        assert card["headline"]["value"] == 80.0
        assert card["secondary"][0]["value"] == 80.0

    def test_no_data(self):
        cards = build_recovery_cards([], window())
        assert cards["hrv"]["headline"]["display"] == "—"
        assert "Aucune mesure de VFC" in cards["hrv"]["insight"]["text"]


def test_empty_card_has_full_series():
    card = empty_card("Rien à afficher.", window("7d"), {"km": 0.0})
    assert len(card["series"]) == 7
    assert card["series"][0]["km"] == 0.0
    assert card["insight"]["text"] == "Rien à afficher."
