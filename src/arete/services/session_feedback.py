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
from dataclasses import dataclass
from datetime import date
from typing import Literal

from arete.services.memory import SESSIONS_LEDGER, append_entry

logger = logging.getLogger(__name__)

#: A card under an upload, not an essay.
MAX_FEEDBACK_CHARS = 900


@dataclass(frozen=True)
class SessionEvidence:
    """Who the session is: what the ledger entry is filed under."""

    date: date
    title: str
    rpe: float | None = None
    notes: str | None = None
    session_ref: str | None = None


def _facts(
    rule_feedback: str, highlights: list[str], evidence: SessionEvidence | None
) -> str:
    lines = []
    if evidence is not None:
        lines.append(f"Séance du {evidence.date.isoformat()} : {evidence.title}")
        if evidence.rpe:
            lines.append(f"RPE ressenti : {evidence.rpe}/10")
        if evidence.notes:
            lines.append(f"Notes de l'athlète : {evidence.notes}")
    lines.append(rule_feedback)
    facts = "\n".join(lines)
    if highlights:
        facts += "\n\nPoints clés:\n" + "\n".join(f"- {h}" for h in highlights)
    return facts


def enrich_session_feedback(
    rule_feedback: str,
    highlights: list[str],
    *,
    produce: Callable[[str], str],
    evidence: SessionEvidence | None = None,
) -> tuple[str, Literal["agent", "rules"]]:
    """The coach's word on a finished session, with the rule text as floor.

    Returns ``(text, source)`` where source is ``"agent"`` or ``"rules"``.
    Never raises: an athlete who just uploaded a session gets an answer either
    way. With ``evidence``, the server files the session in ``sessions.md``
    itself — once, whatever the model does — so tomorrow's briefing knows it
    happened; the model only writes the answer.
    """
    facts = _facts(rule_feedback, highlights, evidence)
    try:
        text, source = produce(facts), "agent"
    except Exception:
        logger.warning("Session feedback agent run failed", exc_info=True)
        text, source = rule_feedback, "rules"
    if evidence is not None:
        reference = (
            f"Source séance : {evidence.session_ref}\n" if evidence.session_ref else ""
        )
        body = (
            reference
            + facts
            + (f"\n\nRetour du coach : {text}" if source == "agent" else "")
        )
        try:
            append_entry(SESSIONS_LEDGER, evidence.title, body, when=evidence.date)
        except OSError:
            logger.warning("Could not file the session in the journal", exc_info=True)
    return text, source  # type: ignore[return-value]
