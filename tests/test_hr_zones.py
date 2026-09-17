"""Zone boundaries: built on the athlete's threshold, not a generic max."""

from __future__ import annotations

import json

from arete.features.hr_zones import (
    DEFAULT_MAX_HR,
    ZoneModel,
    samples_from_laps,
)
from arete.garmin.sync import zones_from_laps


class TestReference:
    def test_threshold_wins_over_max_hr(self):
        model = ZoneModel.from_reference(lthr=176, max_hr=199)
        assert model.basis == "lthr"
        assert model.reference == 176
        assert model.boundaries == (150, 158, 167, 176)

    def test_max_hr_used_without_a_threshold(self):
        model = ZoneModel.from_reference(max_hr=199)
        assert model.basis == "max_hr"
        assert model.boundaries == (119, 139, 159, 179)

    def test_falls_back_to_a_generic_max(self):
        model = ZoneModel.from_reference()
        assert model.reference == DEFAULT_MAX_HR
        assert model.basis == "max_hr"

    def test_zero_is_treated_as_unset(self):
        assert ZoneModel.from_reference(lthr=0, max_hr=0).reference == DEFAULT_MAX_HR

    def test_boundaries_stay_strictly_increasing(self):
        boundaries = ZoneModel.from_reference(lthr=100).boundaries
        assert list(boundaries) == sorted(set(boundaries))


class TestZoneOf:
    model = ZoneModel.from_reference(lthr=176)

    def test_easy_run_is_not_threshold_work(self):
        # 153 bpm on a 176 threshold is endurance, not Z4
        assert self.model.zone_of(153) == 2

    def test_every_boundary_opens_its_zone(self):
        for index, boundary in enumerate(self.model.boundaries):
            assert self.model.zone_of(boundary) == index + 2
            assert self.model.zone_of(boundary - 1) == index + 1

    def test_above_threshold_is_z5(self):
        assert self.model.zone_of(199) == 5

    def test_ranges_cover_without_overlap(self):
        spans = self.model.ranges()
        assert spans[0][0] == 0
        assert spans[-1][1] is None
        for (_, high), (low, _) in zip(spans, spans[1:], strict=False):
            assert high is not None and low == high + 1


class TestSeconds:
    model = ZoneModel.from_reference(lthr=176)

    def test_seconds_are_bucketed(self):
        totals = self.model.seconds_in_zones([(140, 600), (160, 300), (180, 120)])
        assert totals == {"z1": 600, "z2": 0, "z3": 300, "z4": 0, "z5": 120}

    def test_missing_heart_rate_is_ignored(self):
        assert sum(self.model.seconds_in_zones([(0, 600), (None, 300)]).values()) == 0

    def test_laps_become_samples(self):
        laps = [
            {"average_heartrate": 143, "moving_time": 341},
            {"average_heartrate": None, "moving_time": 300},
            {"average_heartrate": 170, "elapsed_time": 200},
        ]
        assert samples_from_laps(laps) == [(143.0, 341.0), (170.0, 200.0)]


class TestZonesFromLaps:
    model = ZoneModel.from_reference(lthr=176)

    def test_json_in_json_out(self):
        laps = json.dumps([{"average_heartrate": 180, "moving_time": 60}])
        assert json.loads(zones_from_laps(laps, self.model))["z5"] == 60

    def test_nothing_usable_returns_none(self):
        assert zones_from_laps(None, self.model) is None
        assert zones_from_laps("not json", self.model) is None
        assert zones_from_laps("[]", self.model) is None
        assert (
            zones_from_laps('[{"moving_time": 60}]', self.model) is None
        )  # no heart rate
