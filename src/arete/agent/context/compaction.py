"""Compaction policy over an explicitly supplied model.

The trigger is an absolute count derived from the deployment's configured
context window; it does not assume a provider router's selected model size.
The final context guard includes schemas, reserves output capacity and refuses
an oversized kept tail instead of silently dropping it.

Raw evicted history stays in the transcript archive outside the writable
coaching ledger. Compaction remains per invocation while the browser owns
conversation history.
"""

from __future__ import annotations

from pathlib import Path

from deepagents.backends import FilesystemBackend
from deepagents.middleware import SummarizationMiddleware
from langchain.agents.middleware import AgentMiddleware

from arete.config import config

#: Where evicted messages land. Beside the ledger, never inside it.
TRANSCRIPTS_DIR_NAME = "agent/transcripts"

#: Upper compaction trigger; smaller configured windows summarize earlier.
#: Sized against this agent's own traffic: a bounded page read is ~8k tokens,
#: so a handful of data-heavy turns crosses it and a short exchange does not.
SUMMARIZE_ABOVE_TOKENS = 40_000

#: Recent messages kept verbatim; the final guard checks their actual size.
KEEP_RECENT_MESSAGES = 12


def transcripts_root() -> Path:
    """Absolute path of the transcript archive, created on demand."""
    root = config.db_path.parent / TRANSCRIPTS_DIR_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def build_summarization(
    model, *, context_tokens: int = 65536, output_tokens: int = 4096
) -> AgentMiddleware:
    """Summarization for the chat agent, on its own filesystem.

    The class rather than ``create_summarization_middleware``: the factory
    takes no trigger, and its fraction-of-window default raises on a model
    with no profile — which is every model the free router can pick.
    """
    return SummarizationMiddleware(
        model,
        backend=FilesystemBackend(root_dir=transcripts_root()),
        trigger=(
            "tokens",
            min(SUMMARIZE_ABOVE_TOKENS, int((context_tokens - output_tokens) * 0.7)),
        ),
        keep=("messages", KEEP_RECENT_MESSAGES),
    )
