"""Memory ledger filesystem for the coaching agent.

The agent keeps its own notes as markdown under ``data/agent/memory/`` —
Cortex's ``/memory/`` filesystem routes, reduced to one disk backend. The
deepagents ``FilesystemMiddleware`` provides ``ls/read_file/write_file/
edit_file/glob/grep`` tools; a scoped permission keeps every operation inside
the memory root so the agent can never touch DuckDB files, tokens or FITs.
"""

from __future__ import annotations

from pathlib import Path

from deepagents.backends import FilesystemBackend
from deepagents.middleware.filesystem import FilesystemMiddleware, FilesystemPermission

from arete.config import config

#: Agent-writable memory root, inside the existing ``data/`` bind mount so
#: Docker and local runs share the same ledger.
MEMORY_DIR_NAME = "agent/memory"

#: Session-ledger files the system prompt steers the agent toward. Free-form
#: extra files are allowed; these two are the contract.
SESSIONS_LEDGER = "sessions.md"
NOTES_LEDGER = "notes.md"

#: Everything the ledger needs: read anything inside the root, write anything
#: inside the root. Paths are relative to the backend root (deepagents
#: resolves them there), so no ``..`` escape is possible.
MEMORY_PERMISSION = FilesystemPermission(
    operations=["read", "write"],
    paths=["/**"],
    mode="allow",
)


def memory_root() -> Path:
    """Absolute path of the memory directory, created on demand."""
    root = config.db_path.parent / MEMORY_DIR_NAME
    root.mkdir(parents=True, exist_ok=True)
    return root


def build_memory_filesystem() -> FilesystemMiddleware:
    """Filesystem middleware scoped to the memory root.

    Tool set trimmed to ls/read/write/edit/delete: ``glob``/``grep`` ship an
    anyOf-nullable optional param whose JSON schema some OpenRouter free
    providers (strict grammar translation) reject outright — "more than one
    JSON reading of the same emitted value" — killing every request for ALL
    tools. Two ledger files don't need search; ``ls`` + ``read_file`` suffice.
    """
    root = memory_root()
    for name in (SESSIONS_LEDGER, NOTES_LEDGER):
        (root / name).touch(exist_ok=True)
    return FilesystemMiddleware(
        backend=FilesystemBackend(root_dir=root, virtual_mode=True, max_file_size_mb=5),
        tools=["ls", "read_file", "write_file", "edit_file", "delete"],
        _permissions=[MEMORY_PERMISSION],
    )
