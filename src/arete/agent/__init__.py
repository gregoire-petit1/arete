"""Coaching agent (deepagent) — minimal port of Cortex's sidepanel integration.

Decoupled pieces, mirroring cortex_ai:
- ``context.py``: run context dataclass + panel_context budget constants
- ``middlewares.py``: RuntimeContextMiddleware injecting the open page at the
  request tail every turn (Cortex INTAI-1589 pattern), and ToolEventMiddleware
  emitting tool_start/tool_end stream events for the UI
- ``filesystem.py``: memory ledger (.md files) scoped to ``data/agent/memory``
- ``tools.py``: ``get_page_context(page)`` — the page-source tool
- ``toolkits.py`` / ``toolkit_middleware.py``: progressive tool loading, with
  the loaded set carried in the graph state
- ``planning_tools.py``: the tools of the ``planning`` toolkit
- ``model.py``: LLM_* env vars → LangChain chat model
- ``agent.py``: graph factory
- ``api.py``: REST surface, the only writer of ``panel_context``
"""
