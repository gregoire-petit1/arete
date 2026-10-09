"""Deep Agents filesystem adapter, restricted to the coaching ledger."""

from deepagents.backends import FilesystemBackend
from deepagents.middleware.filesystem import FilesystemMiddleware, FilesystemPermission

from arete.services.memory import NOTES_LEDGER, SESSIONS_LEDGER, memory_root

#: Writes go through ``append_journal`` (server-dated, deduplicated); the
#: filesystem only reads, so a model can no longer rewrite or lose the journal.
MEMORY_PERMISSION = FilesystemPermission(
    operations=["read"],
    paths=["/**"],
    mode="allow",
)


LEDGER_TOOL_DESCRIPTIONS = {
    "read_file": "Lit un fichier du journal: sessions.md, notes.md ou une "
    "archive mensuelle sessions-AAAA-MM.md. 100 lignes par défaut; offset et "
    "limit pour paginer. Dans sessions.md les entrées récentes sont à la fin: "
    "lis la fin du fichier pour les trouver. Les lignes arrivent numérotées, "
    "ne recopie jamais ces numéros.",
}


def build_memory_filesystem() -> FilesystemMiddleware:
    """Read-only filesystem middleware scoped to the memory root.

    ``read_file`` only: ``glob``/``grep`` ship an anyOf-nullable optional
    param whose JSON schema some OpenRouter free providers (strict grammar
    translation) reject outright, killing every request for ALL tools; and
    ``ls``/``write_file``/``edit_file`` cost 500 tokens of schema on every
    call for what ``append_journal`` does in one bounded, dated write.
    """
    root = memory_root()
    for name in (SESSIONS_LEDGER, NOTES_LEDGER):
        (root / name).touch(exist_ok=True)
    return FilesystemMiddleware(
        backend=FilesystemBackend(root_dir=root, virtual_mode=True, max_file_size_mb=5),
        tools=["read_file"],
        custom_tool_descriptions=LEDGER_TOOL_DESCRIPTIONS,
        _permissions=[MEMORY_PERMISSION],
    )
