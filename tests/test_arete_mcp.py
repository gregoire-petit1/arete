"""The read-only MCP server: GET only, bounded, Strava left out."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import httpx
import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "arete_mcp.py"
spec = importlib.util.spec_from_file_location("arete_mcp", SCRIPT)
assert spec and spec.loader
arete_mcp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(arete_mcp)


def _api(seen: list[httpx.Request]):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path
        if path.endswith("/analytics/overview"):
            body = {"cards": {"pmc": {"headline": {"value": 40}, "series": [1, 2, 3]}}}
        elif path.endswith("/goals/next"):
            body = {"id": 7, "name": "Semi"}
        else:
            body = {"path": path, "query": dict(request.url.params)}
        return httpx.Response(200, json=body)

    return arete_mcp.AreteApi(
        "https://arete.example/api",
        bypass="s3cret",
        api_key="arete-key",
        transport=httpx.MockTransport(handler),
    )


def test_every_tool_only_reads():
    seen: list[httpx.Request] = []
    api = _api(seen)
    for fn in arete_mcp.TOOLS:
        fn(api)
    assert seen and all(r.method == "GET" for r in seen)
    assert all(r.headers["x-vercel-protection-bypass"] == "s3cret" for r in seen)
    assert all(r.headers["authorization"] == "Bearer arete-key" for r in seen)


def test_sessions_leave_strava_out_and_are_bounded():
    seen: list[httpx.Request] = []
    out = arete_mcp.recent_sessions(_api(seen), limit=1000)
    assert out["query"] == {"limit": "100", "offset": "0", "for_model": "true"}


def test_overview_drops_chart_points_and_ranges_are_capped():
    seen: list[httpx.Request] = []
    api = _api(seen)
    assert "series" not in arete_mcp.training_overview(api)["cards"]["pmc"]
    out = arete_mcp.health(api, start="2025-01-01", end="2026-10-01")
    assert out["query"]["start"] == "2026-06-03"  # 120 days before the end


def test_goals_bring_the_next_projection():
    seen: list[httpx.Request] = []
    out = arete_mcp.goals(_api(seen))
    assert out["projection"]["path"].endswith("/goals/7/projection")


def test_the_server_lists_and_calls_the_tools():
    pytest.importorskip("mcp")
    import asyncio

    seen: list[httpx.Request] = []
    server = arete_mcp.build_server(_api(seen))

    async def run():
        tools = {t.name: t for t in await server.list_tools()}
        result = await server.call_tool("recent_sessions", {"limit": 3})
        return tools, result

    tools, result = asyncio.run(run())
    assert set(tools) == {fn.__name__ for fn in arete_mcp.TOOLS}
    assert sorted(tools["health"].input_schema["properties"]) == ["end", "start"]
    assert seen[-1].url.params["limit"] == "3"
    assert "for_model" in json.dumps(str(result))
