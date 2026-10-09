"""Exercise actual filesystem tools, including permission routing and async calls."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from deepagents.backends import FilesystemBackend
from deepagents.backends.utils import create_file_data
from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, ToolMessage

from arete.agent.backends.memory import build_memory_filesystem
from arete.services import memory
from arete.services.journal import journal_block


@pytest.fixture
def ledger(tmp_path, monkeypatch):
    import arete.agent.backends.memory as backend

    monkeypatch.setattr(memory, "memory_root", lambda: tmp_path)
    monkeypatch.setattr(backend, "memory_root", lambda: tmp_path)
    for name in ("notes.md", "sessions.md", "sessions-2026-09.md", "other.md"):
        (tmp_path / name).write_text("keep\nobsolete\n", encoding="utf-8")
    return tmp_path


@pytest.fixture(params=[False, True], ids=["sync", "async"])
def run_tools(request):
    def run(calls):
        class Model(GenericFakeChatModel):
            def bind_tools(self, tools, **kwargs):
                return self

        model = Model(
            messages=iter(
                [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": name,
                                "args": args,
                                "id": str(i),
                                "type": "tool_call",
                            }
                            for i, (name, args) in enumerate(calls)
                        ],
                    ),
                    AIMessage(content="Terminé."),
                ]
            )
        )
        graph = create_agent(model, middleware=[build_memory_filesystem()])
        state = {
            "messages": [{"role": "user", "content": "Mets le journal à jour."}],
            "files": {"/attachments/source.md": create_file_data("keep\nobsolete\n")},
        }
        config = {"recursion_limit": 5}
        result = (
            asyncio.run(graph.ainvoke(state, config=config))
            if request.param
            else graph.invoke(state, config=config)
        )
        return [m for m in result["messages"] if isinstance(m, ToolMessage)], result

    return run


@pytest.mark.parametrize("name", ["notes.md", "sessions.md"])
def test_correct_remove_and_delete_current_ledger(ledger, run_tools, name):
    def edit(old, new):
        return run_tools(
            [
                (
                    "edit_file",
                    {"file_path": f"/{name}", "old_string": old, "new_string": new},
                )
            ]
        )[0][0]

    assert edit("obsolete", "corrected").status == "success"
    assert (ledger / name).read_text() == "keep\ncorrected\n"
    assert "corrected" in journal_block(ledger)
    assert edit("corrected\n", "").status == "success"
    assert (ledger / name).read_text() == "keep\n"
    messages, _ = run_tools([("delete", {"file_path": f"/{name}"})])
    assert messages[0].status == "success"
    assert not (ledger / name).exists()
    # The ordinary append path recreates a deleted file, still with a dated heading.
    assert memory.append_entry(name, "new", "entry")
    assert "new" in (ledger / name).read_text()


@pytest.mark.parametrize(
    "path", ["/sessions-2026-09.md", "/other.md", "/attachments/source.md", "/"]
)
def test_archives_attachments_other_files_and_root_remain_protected(
    ledger, run_tools, path
):
    messages, state = run_tools(
        [
            (
                "edit_file",
                {"file_path": path, "old_string": "obsolete", "new_string": "bad"},
            ),
            ("delete", {"file_path": path}),
        ]
    )
    assert all(
        m.status == "error" and "permission denied" in m.content for m in messages
    )
    assert (ledger / "sessions-2026-09.md").read_text() == "keep\nobsolete\n"
    assert (ledger / "other.md").read_text() == "keep\nobsolete\n"
    assert state["files"]["/attachments/source.md"]["content"] == "keep\nobsolete\n"


@pytest.mark.parametrize("old", ["missing", "keep"])
def test_stale_or_ambiguous_edits_fail_without_changing_the_file(
    ledger, run_tools, old
):
    path = ledger / "notes.md"
    path.write_text("keep\nkeep\n")
    messages, _ = run_tools(
        [
            (
                "edit_file",
                {"file_path": "/notes.md", "old_string": old, "new_string": "bad"},
            )
        ]
    )
    assert messages[0].status == "error"
    assert path.read_text() == "keep\nkeep\n"


def test_append_waits_for_edit_and_neither_write_is_lost(ledger, monkeypatch):
    backend = build_memory_filesystem().backend
    editing, release, appending = Event(), Event(), Event()
    original_edit = FilesystemBackend.edit

    def paused_edit(self, *args, **kwargs):
        editing.set()
        assert release.wait(timeout=5)
        return original_edit(self, *args, **kwargs)

    def append():
        appending.set()
        return memory.append_entry("notes.md", "new", "entry")

    monkeypatch.setattr(FilesystemBackend, "edit", paused_edit)
    with ThreadPoolExecutor(max_workers=2) as pool:
        edit = pool.submit(backend.edit, "/notes.md", "obsolete", "corrected")
        try:
            assert editing.wait(timeout=5)
            added = pool.submit(append)
            assert appending.wait(timeout=5)
            assert not added.done()
        finally:
            release.set()
        assert edit.result(timeout=5).error is None
        assert added.result(timeout=5)
    content = (ledger / "notes.md").read_text()
    assert "corrected" in content and "new : entry" in content
