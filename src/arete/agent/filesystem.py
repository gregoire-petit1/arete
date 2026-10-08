"""Memory ledger filesystem for the coaching agent.

The agent keeps its own notes as markdown under ``data/agent/memory/`` —
Cortex's ``/memory/`` filesystem routes, reduced to one disk backend. The
deepagents ``FilesystemMiddleware`` provides ``ls/read_file/write_file/
edit_file/glob/grep`` tools; a scoped permission keeps every operation inside
the memory root so the agent can never touch DuckDB files, tokens or FITs.
"""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path

from deepagents.backends import FilesystemBackend
from deepagents.middleware.filesystem import FilesystemMiddleware, FilesystemPermission

from arete.config import config

logger = logging.getLogger(__name__)

#: Agent-writable memory root, inside the existing ``data/`` bind mount so
#: Docker and local runs share the same ledger.
MEMORY_DIR_NAME = "agent/memory"

#: Session-ledger files the system prompt steers the agent toward. Free-form
#: extra files are allowed; these two are the contract.
SESSIONS_LEDGER = "sessions.md"
NOTES_LEDGER = "notes.md"

#: Size at which ``sessions.md`` is rotated. The agent reads it back on every
#: conversation, so an unbounded journal becomes the largest block of context
#: it carries — and with a briefing written every morning it only grows.
#: Roughly ten thousand tokens' worth of French markdown.
MAX_SESSIONS_LEDGER_CHARS = 40_000

#: Rotation keeps at least this much of the tail, so the agent never wakes up
#: to an empty journal right after an archive.
KEEP_SESSIONS_LEDGER_CHARS = 20_000

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


#: The ledger's tools, described for a two-file journal rather than a code
#: base. deepagents' defaults are written for a coding agent — pagination of
#: source files, image reads, batching — and cost 1,131 tokens on every model
#: call. These keep what changes behaviour and drop the rest. Two of the kept
#: lines guard against real failure modes, not style:
#:
#: - ``read_file`` reads 100 lines from the top by default, and the newest
#:   entries of ``sessions.md`` are at the bottom. Past 100 lines a default
#:   read returns the oldest entries and misses the recent ones.
#: - ``write_file`` replaces the whole file. Read 100 lines, rewrite with an
#:   entry appended, and everything past line 100 is gone.
LEDGER_TOOL_DESCRIPTIONS = {
    "ls": "Liste les fichiers de ton journal: sessions.md, notes.md et les "
    "archives mensuelles sessions-AAAA-MM.md.",
    "read_file": "Lit un fichier du journal, 100 lignes par défaut; offset et "
    "limit pour paginer. Dans sessions.md les entrées récentes sont à la fin: "
    "lis la fin du fichier pour les trouver. Les lignes arrivent numérotées, "
    "ne recopie jamais ces numéros.",
    "edit_file": "Remplace un passage exact d'un fichier du journal, recopié à "
    "l'identique et unique dans le fichier. Le journal joint à ton prompt suffit "
    "pour le recopier; read_file seulement si le passage n'y figure pas. C'est "
    "l'outil pour ajouter une entrée.",
    "write_file": "Crée un fichier ou le remplace en entier. N'y passe jamais "
    "pour ajouter à sessions.md ou notes.md: tout ce que tu n'as pas relu "
    "serait effacé. Pour ajouter, edit_file.",
}


def archive_path(root: Path, when: date) -> Path:
    """Where a rotated ledger lands: one archive per month."""
    return root / f"sessions-{when:%Y-%m}.md"


def rotate_sessions_ledger(now: date | None = None) -> Path | None:
    """Archive the old half of ``sessions.md`` when it outgrows its budget.

    Splits on an entry heading (``## ``), never mid-entry: half a session
    reads as a different session. The archive stays inside the memory root, so
    the agent can still open it deliberately; it just stops paying for it on
    every turn. Returns the archive written, or None when nothing was due.
    """
    root = memory_root()
    path = root / SESSIONS_LEDGER
    if not path.exists():
        return None
    content = path.read_text(encoding="utf-8")
    if len(content) <= MAX_SESSIONS_LEDGER_CHARS:
        return None

    cut = len(content) - KEEP_SESSIONS_LEDGER_CHARS
    boundary = content.find("\n## ", cut)
    if boundary == -1:
        # No heading after the cut: keep the whole tail rather than split an
        # entry. The next write will push it over again, and that is fine.
        boundary = content.rfind("\n## ", 0, cut)
        if boundary == -1:
            return None
    head, tail = content[:boundary], content[boundary + 1 :]

    archive = archive_path(root, now or date.today())
    with archive.open("a", encoding="utf-8") as fh:
        fh.write(head.rstrip() + "\n")
    path.write_text(tail, encoding="utf-8")
    logger.info(
        "Rotated %s: %d chars archived to %s", SESSIONS_LEDGER, len(head), archive.name
    )
    return archive


def build_memory_filesystem() -> FilesystemMiddleware:
    """Filesystem middleware scoped to the memory root.

    Tool set trimmed to ls/read/write/edit: ``glob``/``grep`` ship an
    anyOf-nullable optional param whose JSON schema some OpenRouter free
    providers (strict grammar translation) reject outright — "more than one
    JSON reading of the same emitted value" — killing every request for ALL
    tools. Two ledger files don't need search; ``ls`` + ``read_file`` suffice.

    ``delete`` is gone too: rotation is the server's job, and nothing the
    coach does needs to remove a journal file — 146 tokens a call for a
    capability that could only lose data.
    """
    root = memory_root()
    for name in (SESSIONS_LEDGER, NOTES_LEDGER):
        (root / name).touch(exist_ok=True)
    return FilesystemMiddleware(
        backend=FilesystemBackend(root_dir=root, virtual_mode=True, max_file_size_mb=5),
        tools=["ls", "read_file", "write_file", "edit_file"],
        custom_tool_descriptions=LEDGER_TOOL_DESCRIPTIONS,
        _permissions=[MEMORY_PERMISSION],
    )
