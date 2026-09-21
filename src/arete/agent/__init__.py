"""Coaching agent (deepagent) — minimal port of Cortex's sidepanel integration.

Three decoupled pieces, mirroring cortex_ai:
- ``context.py``: run context dataclass + panel_context budget constants
- ``middlewares.py``: RuntimeContextMiddleware injecting the open page at the
  request tail every turn (Cortex INTAI-1589 pattern)
- ``filesystem.py``: memory ledger (.md files) scoped to ``data/agent/memory``
- ``tools.py``: ``get_page_context(page)`` — the page-source tool
- ``agent.py``: graph factory + provider mapping
- ``api/agent.py``: REST surface, the only writer of ``panel_context``
"""
