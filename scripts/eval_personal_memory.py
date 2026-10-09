"""Synthetic context-selection ablation; never opens the athlete database.

Default: offline source recall and timing. --live adds ONE tool-free answer per
case/variant, using a pinned model, zero retries/fallbacks, no judge model. Answers
and rubrics are exported for human review: retrieval recall is NOT answer quality.
"""

from __future__ import annotations

import argparse
import json
import math
import os
from dataclasses import replace
from pathlib import Path
from time import perf_counter

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_core.messages.utils import count_tokens_approximately

from arete.agent.prompts.coach import SYSTEM_SKILL
from arete.services.personal_context import Passage, SearchLimits, retrieve

CASES = Path(__file__).resolve().parents[1] / "tests/data/personal_memory_cases.jsonl"
MAX_CASES = 60
MAX_CALLS = 180
MAX_OUTPUT_TOKENS = 4096
CONTEXT_TOKENS = 16384
RETRIEVAL_TOKENS = 2048
TIMEOUT_SECONDS = 60
VARIANTS = ("baseline", "bm25", "bm25_graph")
RATING_KEYS = ("preference_followed", "temporal_error", "unsupported_claim")


def load_cases() -> list[dict]:
    cases = [json.loads(line) for line in CASES.read_text().splitlines()]
    assert len(cases) == MAX_CASES and len({c["id"] for c in cases}) == MAX_CASES
    assert sum(c["split"] == "validation" for c in cases) == 20
    return cases


def context_for(case: dict, variant: str) -> tuple[str, list[str], float]:
    started = perf_counter()
    corpus = [Passage(**{**p, "links": tuple(p["links"])}) for p in case["passages"]]
    if variant == "baseline":
        # Frozen selection baseline: 30 latest facts and five recent journal entries.
        mandatory = case["mandatory"][-30:]
        candidates = sorted(corpus, key=lambda p: p.date)[-5:]
    else:
        mandatory = case["mandatory"]
        result = retrieve(
            corpus, case["query"], limits=SearchLimits(graph=variant == "bm25_graph")
        )
        candidates = [hit.passage for hit in result.hits]
    selected: list[dict] = []
    for passage in candidates:
        selected.append(
            {"source": passage.source, "date": passage.date, "text": passage.text}
        )
        if (
            count_tokens_approximately(
                [SystemMessage(json.dumps(selected, ensure_ascii=False))]
            )
            > RETRIEVAL_TOKENS
        ):
            selected.pop()
    context = json.dumps(
        {"date_actuelle": "2026-10-10", "faits": mandatory, "souvenirs": selected},
        ensure_ascii=False,
    )
    return context, [p["source"] for p in selected], (perf_counter() - started) * 1000


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--split", choices=("development", "validation", "all"), default="development"
    )
    parser.add_argument("--live", action="store_true")
    parser.add_argument(
        "--model", help="Exact model ID; required with --live, no fallback routing"
    )
    parser.add_argument("--limit", type=int, default=MAX_CASES)
    parser.add_argument(
        "--output", type=Path, default=Path(".context/personal-memory-eval.json")
    )
    parser.add_argument(
        "--ratings",
        type=Path,
        help="Human ratings JSON: list of {id, variant, preference_followed, temporal_error, unsupported_claim}",
    )
    args = parser.parse_args()
    if not 1 <= args.limit <= MAX_CASES:
        parser.error("--limit must be 1..60")
    if args.live and (
        os.getenv("ARETE_EVAL") != "1"
        or not args.model
        or args.model == "openrouter/free"
    ):
        parser.error("--live requires ARETE_EVAL=1 and a pinned --model")
    model = None
    if args.live:
        from arete.agent.models.providers import build_chat_model
        from arete.agent.models.routing import resolve_route

        route = replace(
            resolve_route(),
            model=args.model,
            fallbacks=(),
            context_tokens=CONTEXT_TOKENS,
        )
        model = build_chat_model(
            route=route,
            max_tokens=MAX_OUTPUT_TOKENS,
            timeout=TIMEOUT_SECONDS,
            max_retries=0,
            temperature=0,
            openrouter_reasoning=False,
        )
    cases = [
        c for c in load_cases() if args.split == "all" or c["split"] == args.split
    ][: args.limit]
    rows = []
    calls = 0
    for case in cases:
        for variant in VARIANTS:
            context, sources, elapsed = context_for(case, variant)
            expected = set(case["expected_sources"])
            messages = [
                SystemMessage(
                    SYSTEM_SKILL
                    + "\nAucun outil disponible. Réponds avec les preuves fournies et indique ce qui manque.\n"
                    + context
                ),
                HumanMessage(case["query"]),
            ]
            tokens = int(count_tokens_approximately(messages))
            assert tokens + MAX_OUTPUT_TOKENS + 1024 <= CONTEXT_TOKENS
            row = {
                "id": case["id"],
                "split": case["split"],
                "category": case["category"],
                "variant": variant,
                "sources": sources,
                "recall": len(expected.intersection(sources)) / len(expected)
                if expected
                else None,
                "context_tokens_estimated": tokens,
                "retrieval_ms": elapsed,
                "model_calls": 0,
                "model_ms": None,
                "answer": None,
                "expected_behavior": case["expected_behavior"],
                **dict.fromkeys(RATING_KEYS),
            }
            if model is not None:
                assert calls < MAX_CALLS
                calls += 1
                started = perf_counter()
                # Fail explicitly on provider errors; never replay an ambiguous call.
                response = model.invoke(messages)
                row.update(
                    answer=response.text,
                    model_calls=1,
                    model_ms=(perf_counter() - started) * 1000,
                    served_model=response.response_metadata.get("model_name"),
                    usage=response.usage_metadata,
                )
            rows.append(row)
    if args.ratings:
        ratings = json.loads(args.ratings.read_text())
        indexed = {(r["id"], r["variant"]): r for r in rows}
        assert len(ratings) <= MAX_CALLS
        for rating in ratings:
            target = indexed[(rating["id"], rating["variant"])]
            assert all(isinstance(rating[k], bool) for k in RATING_KEYS)
            target.update({k: rating[k] for k in RATING_KEYS})
    summary = {}
    for variant in VARIANTS:
        subset = [r for r in rows if r["variant"] == variant]
        recall = [r["recall"] for r in subset if r["recall"] is not None]
        times = sorted(r["retrieval_ms"] for r in subset)
        summary[variant] = {
            "source_recall": sum(recall) / len(recall) if recall else None,
            "p95_retrieval_ms": times[math.ceil(0.95 * len(times)) - 1],
            "model_calls": sum(r["model_calls"] for r in subset),
        }
        for key in RATING_KEYS:
            rated = [r[key] for r in subset if r[key] is not None]
            summary[variant][key] = sum(rated) / len(rated) if rated else None
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {"model": args.model, "calls": calls, "summary": summary, "rows": rows},
            indent=2,
            ensure_ascii=False,
        )
    )
    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print(f"Report: {args.output}")


if __name__ == "__main__":
    main()
