"""Keeping a long conversation affordable, without losing what was said.

deepagents ships `SummarizationMiddleware`; `create_deep_agent` wires it in by
default and `create_agent` — which is what this project uses — does not. Two
things had to be decided before it was worth adding.

**The trigger is an absolute token count, and it has to be.** The default
fires at a fraction of the model's context window, which raises outright on
`openrouter/free`: a fraction needs a model profile carrying
`max_input_tokens`, and the free router has none — it picks whichever free
model supports the request's tools, so the real window is not knowable when
the middleware is built.

40k is sized against two things. What this agent sends: one
`get_page_context` read is bounded at 32k characters, about 8k tokens, so a
few data-heavy turns cross the threshold while an ordinary two-turn exchange
does not. And the window it has to fit inside: `openrouter/free` advertises
200k, and the smallest free tool-calling model in the pool is 65k, which
leaves room for the system prompt, the tool schemas and a reply even in the
worst case.

Going over anyway is survivable: deepagents catches `ContextOverflowError`
from the provider and summarizes on the spot. The trigger is there to keep a
long conversation from being re-sent in full on every turn — the cost — while
the overflow path is what keeps it from breaking.

**The archive does not go in the ledger.** Evicted messages are written to
`<backend root>/conversation_history/<thread>.md`, and the ledger backend's
root is the directory the agent `ls` and `read_file` all day. Dropping
transcripts beside `sessions.md` invites exactly the confusion that already
cost us once, when the agent wrote a training session into its journal and
reported it saved. The archive gets its own root, which the agent cannot
reach — so the path the summary cites is for us, not for it.
"""

from __future__ import annotations

from pathlib import Path

from deepagents.backends import FilesystemBackend
from deepagents.middleware import SummarizationMiddleware
from langchain.agents.middleware import AgentMiddleware

from arete.agent.middlewares import is_chat_request
from arete.config import config

#: Where evicted messages land. Beside the ledger, never inside it.
TRANSCRIPTS_DIR_NAME = "agent/transcripts"

#: Summarize past this many tokens of conversation, whatever the window.
#: Sized against this agent's own traffic: a bounded page read is ~8k tokens,
#: so a handful of data-heavy turns crosses it and a short exchange does not.
SUMMARIZE_ABOVE_TOKENS = 40_000

#: Recent messages kept verbatim behind the summary. Small enough that the
#: kept tail cannot itself sit above the trigger.
KEEP_RECENT_MESSAGES = 12


def transcripts_root() -> Path:
    """Absolute path of the transcript archive, created on demand."""
    root = config.db_path.parent / TRANSCRIPTS_DIR_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


class ChatSummarizationMiddleware(SummarizationMiddleware):
    """Unattended tasks have no conversation to compact or archive."""

    def wrap_model_call(self, request, handler):
        if not is_chat_request(request):
            return handler(request)
        return super().wrap_model_call(request, handler)

    async def awrap_model_call(self, request, handler):
        if not is_chat_request(request):
            return await handler(request)
        return await super().awrap_model_call(request, handler)


def build_summarization(model=None) -> AgentMiddleware:
    """Summarization for the chat agent, on its own filesystem.

    The class rather than ``create_summarization_middleware``: the factory
    takes no trigger, and its fraction-of-window default raises on a model
    with no profile — which is every model the free router can pick.
    """
    return ChatSummarizationMiddleware(
        model if model is not None else _summarization_model(),
        backend=FilesystemBackend(root_dir=transcripts_root()),
        trigger=("tokens", SUMMARIZE_ABOVE_TOKENS),
        keep=("messages", KEEP_RECENT_MESSAGES),
    )


def _summarization_model():
    """The same provider as the agent — summarizing is a model call too."""
    from arete.agent.model import build_chat_model

    return build_chat_model()
