"""The fixed corpus is split before tuning and never conflates recall with behavior."""

import runpy
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/eval_personal_memory.py"


def test_memory_comparison_has_60_cases_and_20_held_out():
    module = runpy.run_path(str(SCRIPT))
    cases = module["load_cases"]()
    assert len(cases) == 60
    assert sum(c["split"] == "development" for c in cases) == 40
    assert len({c["query"] for c in cases}) == 60
    assert all(c["expected_behavior"] for c in cases)
    for case in cases:
        for variant in module["VARIANTS"]:
            text, sources, elapsed = module["context_for"](case, variant)
            assert text and elapsed >= 0
            assert set(sources) <= {p["source"] for p in case["passages"]}


def test_graph_retrieves_a_provenance_target_without_lexical_overlap():
    module = runpy.run_path(str(SCRIPT))
    case = next(c for c in module["load_cases"]() if c["category"] == "relations")
    _, lexical, _ = module["context_for"](case, "bm25")
    _, expanded, _ = module["context_for"](case, "bm25_graph")
    assert not set(case["expected_sources"]) & set(lexical)
    assert set(case["expected_sources"]) <= set(expanded)
