"""Deep Agents filesystem adapter, restricted to the coaching ledger."""

from deepagents.backends import FilesystemBackend
from deepagents.middleware.filesystem import FilesystemMiddleware, FilesystemPermission

from arete.services.memory import NOTES_LEDGER, SESSIONS_LEDGER, memory_root

MEMORY_PERMISSION = FilesystemPermission(
    operations=["read", "write"],
    paths=["/**"],
    mode="allow",
)


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


def build_memory_filesystem() -> FilesystemMiddleware:
    """Filesystem middleware scoped to the memory root.

    Tool set trimmed to ls/read/write/edit: ``glob``/``grep`` ship an
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
        tools=["ls", "read_file", "write_file", "edit_file"],
        custom_tool_descriptions=LEDGER_TOOL_DESCRIPTIONS,
        _permissions=[MEMORY_PERMISSION],
    )
