"""Post-session feedback, written by the coach and filed in its journal.

Replaces the one-shot "reformulate this sentence" call that used to sit
behind ``POST /tips/post-session``. Two things change for the athlete:

- the feedback is written by the agent that can read the rest of their
  training, instead of a model that only saw a pre-rendered sentence;
- the session lands in ``sessions.md``, so tomorrow's briefing — and the next
  conversation in the side panel — already know it happened.

Same contract as the briefing: the rule-based text is the floor, computed by
the caller and handed in. A failure here returns that floor, never an error.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Literal

logger = logging.getLogger(__name__)

#: A card under an upload, not an essay.
MAX_FEEDBACK_CHARS = 900


def enrich_session_feedback(
    rule_feedback: str, highlights: list[str], *, produce: Callable[[str], str]
) -> tuple[str, Literal["agent", "rules"]]:
    """The coach's word on a finished session, with the rule text as floor.

    Returns ``(text, source)`` where source is ``"agent"`` or ``"rules"``.
    Never raises: an athlete who just uploaded a session gets an answer either
    way.
    """
    facts = rule_feedback
    if highlights:
        facts += "\n\nPoints clés:\n" + "\n".join(f"- {h}" for h in highlights)

    try:
        return produce(facts), "agent"
    except Exception:
        logger.warning("Session feedback agent run failed", exc_info=True)
        return rule_feedback, "rules"
