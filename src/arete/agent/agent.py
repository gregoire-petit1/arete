"""Graph factory for the coaching deepagent.

Minimal port of Cortex's ``cortex_agent.py`` (ADR-0030): ``create_agent`` with
a context schema, one page-source tool, and two middlewares — runtime context
(panel page at the request tail) and the deepagents filesystem scoped to the
memory ledger. The full Cortex middleware stack (retry, budget, toolkits,
spawn) is deliberately out of scope for this first integration.
"""

from __future__ import annotations

import logging
from functools import lru_cache

from langchain.agents import create_agent

from arete.agent.context import AgentContext
from arete.agent.filesystem import (
    NOTES_LEDGER,
    SESSIONS_LEDGER,
    build_memory_filesystem,
)
from arete.agent.middlewares import RuntimeContextMiddleware, ToolEventMiddleware
from arete.agent.model import build_chat_model
from arete.agent.toolkit_middleware import ToolkitMiddleware
from arete.agent.tools import get_page_context

logger = logging.getLogger(__name__)

#: Named bound on agent turns per run (tool-call loops included).
AGENT_RECURSION_LIMIT = 25

_SYSTEM_PROMPT = f"""Tu es le coach running/trail de l'app Arete, un assistant \
d'entraînement mono-utilisateur. Tu réponds en français, concrètement, avec les \
chiffres de l'athlète.

Règles:
- Utilise `get_page_context` pour lire les données de la page que l'athlète \
consulte avant de répondre — ne devine jamais un chiffre d'entraînement.
- Des capacités supplémentaires sont des toolkits: cherche avec \
`search_toolkits`, charge avec `load_toolkit`, puis les outils du toolkit \
deviennent disponibles. Aujourd'hui: `planning` (créer et modifier des \
séances prévues) et `analytics` (charge, forme, records, séances récentes sur \
la fenêtre de ton choix).
- `get_page_context` donne la page telle quelle, sur une fenêtre figée. Dès \
qu'il faut une période précise ou comparer deux périodes, charge `analytics`.
- Tu tiens un journal mémoire en markdown:
  - `{SESSIONS_LEDGER}`: une entrée par séance dont tu discutes \
(## YYYY-MM-DD — titre, faits marquants, ressentis, décision prise).
  - `{NOTES_LEDGER}`: observations durables sur l'athlète (blessures, \
préférences, objectifs).
- Lis le journal avant de conseiller; écris après chaque échange qui apporte \
du neuf. Tes fichiers persistent entre les conversations.
- Pas de diagnostic médical. Sur douleur anormale → recommander un avis médical.
"""


@lru_cache(maxsize=1)
def get_agent():
    """Build (once) and return the compiled agent graph.

    The graph is process-wide: single user, single athlete. Raises ValueError
    from ``build_chat_model`` on misconfiguration — callers map it to a 500.
    """
    model = build_chat_model()
    graph = create_agent(
        model,
        tools=[get_page_context],
        middleware=[
            RuntimeContextMiddleware(),
            ToolEventMiddleware(),
            ToolkitMiddleware(),
            build_memory_filesystem(),
        ],
        system_prompt=_SYSTEM_PROMPT,
        context_schema=AgentContext,
        name="arete_coach",
    )
    logger.info(
        "Coaching agent initialized: model=%s", getattr(model, "model_name", "?")
    )
    return graph
