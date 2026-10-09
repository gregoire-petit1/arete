"""Time GET requests against a running Arete API.

Usage:
    uv run python scripts/latency_probe.py --base http://localhost:8001
    uv run python scripts/latency_probe.py --base https://arete-two-woad.vercel.app \
        --prefix /api -n 10 /settings /metrics/player-stats

Behind Vercel Deployment Protection, set VERCEL_AUTOMATION_BYPASS_SECRET.
One client serves every request, so TLS is paid once: the first call of the
first path includes it. Each path prints its first call apart (the cold
number) from the median and maximum of all calls, in milliseconds.
"""

from __future__ import annotations

import argparse
import os
import statistics
import time

import httpx

DEFAULT_PATHS = (
    "/health",
    "/settings",
    "/metrics/player-stats",
    "/analytics/overview",
    "/strength/sessions?limit=200",
)


def probe(client: httpx.Client, url: str, n: int) -> list[float]:
    timings = []
    for _ in range(n):
        start = time.perf_counter()
        client.get(url).raise_for_status()
        timings.append((time.perf_counter() - start) * 1000)
    return timings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="http://localhost:8001")
    parser.add_argument("--prefix", default="", help="e.g. /api on Vercel")
    parser.add_argument("-n", type=int, default=5, help="requests per path")
    parser.add_argument("paths", nargs="*", default=DEFAULT_PATHS)
    args = parser.parse_args()

    headers = {}
    secret = os.environ.get("VERCEL_AUTOMATION_BYPASS_SECRET")
    if secret:
        headers["x-vercel-protection-bypass"] = secret

    print(f"{'path':40} {'n':>3} {'first_ms':>9} {'p50_ms':>8} {'max_ms':>8}")
    with httpx.Client(base_url=args.base, headers=headers, timeout=120) as client:
        for path in args.paths:
            timings = probe(client, args.prefix + path, args.n)
            print(
                f"{path:40} {len(timings):>3} {timings[0]:>9.0f} "
                f"{statistics.median(timings):>8.0f} {max(timings):>8.0f}"
            )


if __name__ == "__main__":
    main()
