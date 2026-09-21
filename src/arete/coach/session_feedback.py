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

logger = logging.getLogger(__name__)

#: Shorter than the briefing's: the facts arrive in the prompt, so this run is
#: read-the-journal, write-the-answer, append-the-entry.
FEEDBACK_RECURSION_LIMIT = 20

#: A card under an upload, not an essay.
MAX_FEEDBACK_CHARS = 900

FEEDBACK_PROMPT = """Tu es le coach running/trail de l'athlète. Il vient de \
terminer une séance et tu lui réponds à chaud.

On te donne les faits de la séance, déjà calculés. Ne les recalcule pas, ne \
les invente pas, ne va pas chercher d'autres chiffres.

Ta tâche:
1. Relis ton journal mémoire pour situer cette séance dans ce que tu sais déjà \
de l'athlète.
2. Ajoute une entrée dans `sessions.md`: `## AAAA-MM-JJ — titre`, puis les \
faits marquants, le ressenti et ce que tu en retiens. C'est ce qui permettra \
au briefing de demain d'en tenir compte.
3. Réponds à l'athlète.

Ta réponse: 2 à 3 phrases, en français, à la deuxième personne. Reprends les \
chiffres qu'on t'a donnés, souligne ce qui s'est bien passé, et donne au plus \
un point d'amélioration. Pas de préambule, pas de liste, pas de diagnostic \
médical. Ta réponse finale est ce message seul, rien d'autre."""


def _run_agent(facts: str) -> str:
    """One agent run over the session facts. Raises on any failure."""
    from arete.agent.agent import build_unattended_agent
    from arete.agent.context import AgentContext
    from arete.agent.filesystem import rotate_sessions_ledger

    # This run appends to the journal, so give it a bounded one to append to.
    rotate_sessions_ledger()

    graph = build_unattended_agent(FEEDBACK_PROMPT, "arete_session_feedback")
    result = graph.invoke(
        {"messages": [{"role": "user", "content": facts}]},
        context=AgentContext(source={}),
        config={"recursion_limit": FEEDBACK_RECURSION_LIMIT},
    )
    messages = result.get("messages", [])
    if not messages:
        raise RuntimeError("Agent returned no messages")
    text = (messages[-1].text or "").strip()
    if not text:
        raise RuntimeError("Agent returned empty feedback")
    if len(text) > MAX_FEEDBACK_CHARS:
        raise RuntimeError(f"Feedback too long for the card ({len(text)} chars)")
    return text


def enrich_session_feedback(
    rule_feedback: str, highlights: list[str]
) -> tuple[str, str]:
    """The coach's word on a finished session, with the rule text as floor.

    Returns ``(text, source)`` where source is ``"agent"`` or ``"rules"``.
    Never raises: an athlete who just uploaded a session gets an answer either
    way.
    """
    facts = rule_feedback
    if highlights:
        facts += "\n\nPoints clés:\n" + "\n".join(f"- {h}" for h in highlights)

    try:
        return _run_agent(facts), "agent"
    except Exception:
        logger.warning("Session feedback agent run failed", exc_info=True)
        return rule_feedback, "rules"
