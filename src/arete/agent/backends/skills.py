"""Read-only DB snapshot using the pinned Deep Agents file/search operations."""

from deepagents.backends import StateBackend
from deepagents.backends.protocol import (
    DeleteResult,
    EditResult,
    FileUploadResponse,
    WriteResult,
)
from deepagents.backends.utils import create_file_data

SYSTEM_SKILLS_ROUTE = "/skills/system/"
DENIED = "permission denied: system skills are versioned by the server"


class SystemSkillsBackend(StateBackend):
    """Never read graph state: client files cannot shadow trusted instructions."""

    def __init__(self, files: dict[str, str]):
        self._files = {path: create_file_data(text) for path, text in files.items()}

    def _read_files(self):
        return self._files

    def _send_files_update(self, update):
        # Backstop if a future upstream mutation method is added.
        raise PermissionError(DENIED)

    def write(self, file_path: str, content: str) -> WriteResult:
        return WriteResult(error=DENIED)

    def edit(self, file_path, old_string, new_string, replace_all=False) -> EditResult:
        return EditResult(error=DENIED)

    def delete(self, file_path: str) -> DeleteResult:
        return DeleteResult(error=DENIED)

    def upload_files(self, files: list[tuple[str, bytes]]) -> list[FileUploadResponse]:
        return [
            FileUploadResponse(path=path, error="permission_denied")
            for path, _ in files
        ]
