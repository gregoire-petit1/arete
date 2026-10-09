"""Deep Agents filesystem adapter, restricted to the coaching ledger."""

from deepagents.backends import CompositeBackend, FilesystemBackend, StateBackend
from deepagents.middleware.filesystem import (
    FilesystemMiddleware,
    FilesystemPermission,
    GlobSchema,
    GrepSchema,
    ReadFileSchema,
)
from pydantic import BaseModel, Field

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


class PortableGlob(GlobSchema):
    path: str = "/"


class PortableGrep(GrepSchema):
    path: str = "/"
    glob: str = "**/*"
    max_count: int = Field(default=100, ge=1, le=100)


class BoundedRead(ReadFileSchema):
    offset: int = Field(default=0, ge=0)
    limit: int = Field(default=100, ge=1, le=200)


def build_memory_filesystem() -> FilesystemMiddleware:
    """Read-only ledger plus invocation-local documents, with portable schemas."""
    root = memory_root()
    for name in (SESSIONS_LEDGER, NOTES_LEDGER):
        (root / name).touch(exist_ok=True)
    middleware = FilesystemMiddleware(
        backend=CompositeBackend(
            default=FilesystemBackend(
                root_dir=root, virtual_mode=True, max_file_size_mb=5
            ),
            routes={"/attachments/": StateBackend()},
        ),
        tools=["read_file", "ls", "glob", "grep"],
        custom_tool_descriptions={
            "read_file": LEDGER_TOOL_DESCRIPTIONS["read_file"]
            + " Lis aussi les documents normalisés sous /attachments/ ; conserve leurs références de source."
        },
        tool_token_limit_before_evict=None,
        human_message_token_limit_before_evict=None,
        grep_max_count=100,
        _permissions=[MEMORY_PERMISSION],
    )
    # Some free providers reject anyOf/null; adapt schemas without forking tools.
    schemas: dict[str, type[BaseModel]] = {
        "glob": PortableGlob,
        "grep": PortableGrep,
        "read_file": BoundedRead,
    }
    for tool in middleware.tools:
        if tool.name in schemas:
            tool.args_schema = schemas[tool.name]
    return middleware
