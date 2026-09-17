"""Muscle vocabulary: coarse ids spread onto the regions the silhouette paints."""

from __future__ import annotations

from datetime import date

from arete.features.muscles import (
    CANONICAL,
    LABEL_FR,
    build_stats,
    expand,
    heat_level,
    spread,
)


class TestExpand:
    def test_canonical_id_maps_to_itself(self):
        assert expand("lats") == {"lats": 1.0}

    def test_region_is_split_over_its_heads(self):
        assert expand("shoulders") == {
            "front_delts": 0.4,
            "side_delts": 0.35,
            "rear_delts": 0.25,
        }
        assert sum(expand("back").values()) == 1.0

    def test_anatomical_name_is_an_alias(self):
        assert expand("latissimus_dorsi") == {"lats": 1.0}
        assert expand("Gastrocnemius") == {"calves": 1.0}

    def test_unknown_muscle_is_dropped(self):
        assert expand("wings") == {}
        assert expand("") == {}

    def test_full_body_shares_sum_to_one(self):
        assert round(sum(expand("full_body").values()), 6) == 1.0

    def test_every_alias_target_is_canonical(self):
        for muscle in ("shoulders", "back", "core", "full_body", "inner_thigh"):
            assert set(expand(muscle)) <= set(CANONICAL)

    def test_every_region_has_a_french_label(self):
        assert set(LABEL_FR) == set(CANONICAL)


class TestSpread:
    def test_coarse_volume_is_shared_not_duplicated(self):
        out = spread({"back": 1000.0})
        assert out == {"lats": 500.0, "traps": 250.0, "rhomboids": 250.0}
        assert sum(out.values()) == 1000.0

    def test_fine_and_coarse_add_up(self):
        out = spread({"lats": 100.0, "back": 100.0})
        assert out["lats"] == 150.0


class TestHeatLevel:
    def test_busiest_region_is_the_top_level(self):
        assert heat_level(1000, 1000) == 4

    def test_worked_region_is_never_cold(self):
        assert heat_level(1, 10000) == 1

    def test_untouched_region_is_cold(self):
        assert heat_level(0, 1000) == 0
        assert heat_level(500, 0) == 0


class TestBuildStats:
    def test_one_entry_per_region_sorted_by_volume(self):
        stats = build_stats(
            {"lats": 1000.0, "chest": 500.0},
            {"lats": 10.0, "chest": 6.0},
            {"lats": date(2026, 9, 15), "chest": date(2026, 9, 12)},
        )
        assert len(stats) == len(CANONICAL)
        assert [s.muscle for s in stats[:2]] == ["lats", "chest"]
        assert stats[0].level == 4
        assert stats[0].sets == 10
        assert stats[0].last_trained == date(2026, 9, 15)

    def test_previous_window_is_spread_too(self):
        stats = build_stats({}, {}, {}, previous={"back": 1000.0})
        lats = next(s for s in stats if s.muscle == "lats")
        assert lats.previous_volume == 500.0
        assert lats.volume == 0.0

    def test_no_previous_window_leaves_none(self):
        stats = build_stats({"lats": 10.0}, {}, {})
        assert stats[0].previous_volume is None

    def test_last_trained_takes_the_most_recent_source(self):
        stats = build_stats(
            {"back": 100.0, "lats": 100.0},
            {},
            {"back": date(2026, 9, 10), "lats": date(2026, 9, 14)},
        )
        lats = next(s for s in stats if s.muscle == "lats")
        assert lats.last_trained == date(2026, 9, 14)

    def test_serialised_entry_shape(self):
        stats = build_stats({"lats": 1000.0}, {"lats": 4.0}, {})
        payload = stats[0].as_dict()
        assert payload == {
            "muscle": "lats",
            "label": "Grands dorsaux",
            "volume": 1000.0,
            "sets": 4,
            "level": 4,
            "previous_volume": None,
            "last_trained": None,
        }
