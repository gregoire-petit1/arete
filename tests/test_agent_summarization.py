"""Summarization has to actually fire, or it is decoration.

The default trigger is a fraction of the model's context window. It raises on
a model with no profile — every model `openrouter/free` can pick — and where
it does work it sits around 890k tokens on a 1M model, far above anything the
panel can send. So the trigger is an absolute token count, and these tests say
it is wired to a real threshold rather than a comfortable one.
"""

from __future__ import annotations

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from arete.agent.context.compaction import (
    KEEP_RECENT_MESSAGES,
    SUMMARIZE_ABOVE_TOKENS,
    build_summarization,
    transcripts_root,
)


@pytest.fixture
def middleware(tmp_path, monkeypatch):
    monkeypatch.setenv("ARETE_DB", str(tmp_path / "s.duckdb"))
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    from arete.agent.models.providers import build_chat_model

    return build_summarization(build_chat_model())


# ---------------------------------------------------------------------------
# Where the archive goes
# ---------------------------------------------------------------------------


def test_transcripts_never_land_in_the_memory_ledger(tmp_path, monkeypatch):
    """Evicted messages are written to the backend root.

    Pointed at the ledger they would sit beside `sessions.md`, in the one
    directory the agent lists and reads on every turn — the same confusion
    that already had it writing a training session into its journal.
    """
    monkeypatch.setenv("ARETE_DB", str(tmp_path / "s.duckdb"))
    from arete.services.memory import memory_root

    assert transcripts_root() != memory_root()
    assert memory_root() not in transcripts_root().parents


def test_the_agent_cannot_reach_the_transcripts(tmp_path, monkeypatch):
    # The filesystem middleware is scoped to the memory root, so the archive
    # is for us to read, not for the agent to quote back.
    monkeypatch.setenv("ARETE_DB", str(tmp_path / "s.duckdb"))
    from arete.services.memory import memory_root

    assert transcripts_root().resolve() not in memory_root().resolve().parents
    assert not str(transcripts_root()).startswith(str(memory_root()) + "/")


# ---------------------------------------------------------------------------
# The threshold
# ---------------------------------------------------------------------------


def test_it_builds_without_a_model_profile(middleware):
    """A fraction trigger raises here; an absolute one must not.

    `openrouter/free` carries no profile, so this is the configuration that
    actually ships.
    """
    assert middleware is not None


def test_the_threshold_fits_the_default_configured_window():
    # The configured default leaves room for schemas, instructions and output.
    assert SUMMARIZE_ABOVE_TOKENS < 65_536 * 0.7


def test_the_threshold_is_reachable_by_this_agent():
    """Sized against what the agent sends, not against the window.

    A page read is bounded at 32k characters, roughly 8k tokens, so a handful
    of data-heavy turns has to be able to cross the line.
    """
    from arete.agent.runtime.budget import MAX_TOOL_OUTPUT_CHARS

    biggest_tool_result_tokens = MAX_TOOL_OUTPUT_CHARS / 4
    assert biggest_tool_result_tokens * 6 >= SUMMARIZE_ABOVE_TOKENS


def test_the_kept_tail_cannot_sit_above_the_trigger():
    # Keeping too many messages would summarize and immediately re-trigger.
    assert 0 < KEEP_RECENT_MESSAGES <= 20


# ---------------------------------------------------------------------------
# It fires
# ---------------------------------------------------------------------------


def test_a_short_conversation_is_left_alone(middleware):
    messages = [HumanMessage("salut"), AIMessage("bonjour")]
    assert middleware._should_summarize(messages, 120) is False


def test_a_conversation_just_under_the_line_is_left_alone(middleware):
    messages = [HumanMessage("x"), AIMessage("y")]
    assert middleware._should_summarize(messages, SUMMARIZE_ABOVE_TOKENS - 1) is False


def test_a_long_conversation_trips_the_trigger(middleware):
    messages = [HumanMessage("x"), AIMessage("y")]
    assert middleware._should_summarize(messages, SUMMARIZE_ABOVE_TOKENS + 1) is True


def test_the_counted_tokens_come_from_real_text(middleware):
    """The threshold has to be reachable by text this agent really sends.

    A bounded page read is 32k characters; a few of those must cross 40k
    tokens, or the trigger is decorative.
    """
    from arete.agent.runtime.budget import MAX_TOOL_OUTPUT_CHARS

    page_read = "detail " * (MAX_TOOL_OUTPUT_CHARS // 7)
    messages = [HumanMessage(page_read) for _ in range(6)]
    counted = middleware.token_counter(messages)
    assert counted > SUMMARIZE_ABOVE_TOKENS
    assert middleware._should_summarize(messages, counted) is True
