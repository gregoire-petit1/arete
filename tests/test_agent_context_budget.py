"""The budget script has to keep running, or nobody re-measures before a change."""

from __future__ import annotations

import runpy
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "agent_context_budget.py"


def test_the_budget_script_runs_against_the_suite_database(capsys, monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    runpy.run_path(str(SCRIPT), run_name="__main__")
    out = capsys.readouterr().out
    for section in ("FIXED COST", "PAGE READS", "TOOLKITS", "ANALYTICS TOOLKIT READS"):
        assert section in out
