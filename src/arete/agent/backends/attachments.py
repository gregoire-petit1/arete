"""Translate public attachment paths to CompositeBackend's mounted state keys."""

from deepagents.backends.protocol import FileData
from deepagents.backends.utils import create_file_data

ATTACHMENTS_ROUTE = "/attachments/"


def attachment_key(path: str) -> str:
    assert path.startswith(ATTACHMENTS_ROUTE), "Attachment outside its mount"
    return "/" + path.removeprefix(ATTACHMENTS_ROUTE)


def attachment_files(files: dict[str, str]) -> dict[str, FileData]:
    # CompositeBackend strips the mount before calling StateBackend. Keep full
    # extracted content here; only the model-context preview is bounded.
    return {
        attachment_key(path): create_file_data(text) for path, text in files.items()
    }
