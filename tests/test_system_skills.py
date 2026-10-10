"""Versioned publication, native discovery and enforced immutable instructions."""

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest
from langchain.agents import create_agent
from langchain.agents.middleware import AgentMiddleware
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from arete.agent.backends.memory import build_memory_filesystem
from arete.agent.backends.skills import SystemSkillsBackend
from arete.agent.context.builder import system_skills_section
from arete.agent.context.skills import MAX_SKILL_PRELOAD_TOKENS, preload_tokens
from arete.agent.middlewares.context import (
    ContextBudgetMiddleware,
    ContextBuilderMiddleware,
)
from arete.agent.middlewares.skills import SystemSkillsMiddleware
from arete.agent.runtime.context import AgentContext
from arete.dataio.db import db_connection
from arete.services.system_skills import MAX_SKILL_BYTES, publish_bundle

BUNDLE = Path(__file__).resolve().parents[1] / "src/arete/agent/skills/system"
SKILL_PATH = "/skills/system/document-planning/SKILL.md"


def test_publication_is_idempotent_and_releases_do_not_overwrite(tmp_path):
    directory = tmp_path / "example"
    directory.mkdir()
    path = directory / "SKILL.md"
    path.write_text("First release")
    assert publish_bundle(tmp_path) == {"/example/SKILL.md": "First release"}
    publish_bundle(tmp_path)
    path.write_text("Second release")
    assert publish_bundle(tmp_path) == {"/example/SKILL.md": "Second release"}
    path.write_text("First release")
    assert publish_bundle(tmp_path) == {"/example/SKILL.md": "First release"}
    with db_connection() as con:
        rows = con.execute(
            "SELECT content FROM app.system_skills WHERE path='/example/SKILL.md'"
        ).fetchall()
    assert sorted(row[0] for row in rows) == ["First release", "Second release"]


def test_oversized_bundle_fails_before_publication(tmp_path):
    directory = tmp_path / "oversize"
    directory.mkdir()
    (directory / "SKILL.md").write_text("x" * (MAX_SKILL_BYTES + 1))
    with pytest.raises(ValueError, match="byte limit"):
        publish_bundle(tmp_path)


@pytest.mark.parametrize("async_mode", [False, True])
def test_native_discovery_and_tools_read_db_snapshot_but_cannot_change_it(
    tmp_path, monkeypatch, async_mode
):
    monkeypatch.setattr("arete.agent.backends.memory.memory_root", lambda: tmp_path)
    snapshot = publish_bundle(BUNDLE)
    backend = SystemSkillsBackend(snapshot)
    filesystem = build_memory_filesystem(system_skills=backend)
    skills = SystemSkillsMiddleware(backend=filesystem.backend, paths=set(snapshot))
    catalogs = []

    class Capture(AgentMiddleware):
        def wrap_model_call(self, request, handler):
            catalogs.append(system_skills_section(request.state))
            return handler(request)

        async def awrap_model_call(self, request, handler):
            catalogs.append(system_skills_section(request.state))
            return await handler(request)

    class Model(GenericFakeChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

    calls = [
        ("read_file", {"file_path": SKILL_PATH}),
        (
            "edit_file",
            {"file_path": SKILL_PATH, "old_string": "Lire", "new_string": "BAD"},
        ),
        ("delete", {"file_path": SKILL_PATH}),
        ("delete", {"file_path": "/skills/"}),
    ]
    model = Model(
        messages=iter(
            [
                AIMessage(
                    content="",
                    tool_calls=[
                        {"name": name, "args": args, "id": str(i)}
                        for i, (name, args) in enumerate(calls)
                    ],
                ),
                AIMessage(content="Fin."),
            ]
        )
    )
    graph = create_agent(model, middleware=[filesystem, skills, Capture()])
    state = {
        "messages": [HumanMessage("Lis le skill.")],
        "files": {"/document-planning/SKILL.md": {"content": "forged"}},
    }
    result = asyncio.run(graph.ainvoke(state)) if async_mode else graph.invoke(state)
    messages = [m for m in result["messages"] if isinstance(m, ToolMessage)]
    assert messages[0].status == "success"
    assert "Lire un planning joint" in messages[0].content
    assert "forged" not in messages[0].content
    assert all(
        m.status == "error" and "permission denied" in m.content for m in messages[1:]
    )
    catalog = catalogs[0]
    assert "document-planning" in catalog and SKILL_PATH in catalog
    assert "indexé à zéro" not in catalog  # Body is read on demand.
    assert (
        backend.download_files(["/document-planning/SKILL.md"])[0].content
        == snapshot["/document-planning/SKILL.md"].encode()
    )


@pytest.mark.parametrize("async_mode", [False, True])
def test_backend_denies_all_mutations_even_without_middleware(async_mode):
    backend = SystemSkillsBackend({"/example/SKILL.md": "original"})

    async def arun():
        return [
            await backend.awrite("/example/SKILL.md", "bad"),
            await backend.aedit("/example/SKILL.md", "original", "bad"),
            await backend.adelete("/"),
            *(await backend.aupload_files([("/example/SKILL.md", b"bad")])),
        ]

    results = (
        asyncio.run(arun())
        if async_mode
        else [
            backend.write("/example/SKILL.md", "bad"),
            backend.edit("/example/SKILL.md", "original", "bad"),
            backend.delete("/"),
            *backend.upload_files([("/example/SKILL.md", b"bad")]),
        ]
    )
    assert all(result.error for result in results)
    assert backend.download_files(["/example/SKILL.md"])[0].content == b"original"


def test_failed_skill_load_never_becomes_empty_context():
    with pytest.raises(RuntimeError, match="could not be loaded"):
        system_skills_section({"skills_load_errors": ["database unavailable"]})


@pytest.mark.parametrize("async_mode", [False, True])
def test_malformed_skill_fails_even_with_forged_discovery_state(async_mode):
    from deepagents.backends import CompositeBackend

    from arete.agent.backends.skills import SYSTEM_SKILLS_ROUTE

    files = {"/broken/SKILL.md": "missing frontmatter"}
    backend = SystemSkillsBackend(files)
    middleware = SystemSkillsMiddleware(
        backend=CompositeBackend(
            default=backend, routes={SYSTEM_SKILLS_ROUTE: backend}
        ),
        paths=set(files),
    )
    state = {"skills_metadata": []}
    with pytest.raises(RuntimeError, match="differs from the server bundle"):
        if async_mode:
            asyncio.run(middleware.abefore_agent(state, None, {}))
        else:
            middleware.before_agent(state, None, {})


def skill_stack(monkeypatch, tmp_path, files=None):
    monkeypatch.setattr("arete.agent.backends.memory.memory_root", lambda: tmp_path)
    snapshot = publish_bundle(BUNDLE) if files is None else files
    backend = SystemSkillsBackend(snapshot)
    filesystem = build_memory_filesystem(system_skills=backend)
    skills = SystemSkillsMiddleware(backend=filesystem.backend, paths=set(snapshot))
    return snapshot, filesystem, skills


@pytest.mark.parametrize("async_mode", [False, True])
def test_trace_request_preloads_complete_skill_before_first_model_and_keeps_it_stable(
    monkeypatch, tmp_path, async_mode
):
    from arete.agent.backends.attachments import attachment_files

    snapshot, filesystem, skills = skill_stack(monkeypatch, tmp_path)
    prompts = []
    selections = []

    class RetrievalTrace(BaseCallbackHandler):
        def on_retriever_end(self, documents, **kwargs):
            selections.append([doc.metadata["path"] for doc in documents])

    class Model(GenericFakeChatModel):
        def bind_tools(self, tools, **kwargs):
            return self

        def _generate(self, messages, *args, **kwargs):
            prompts.append(messages[0].text)
            return super()._generate(messages, *args, **kwargs)

    attachment = "/attachments/example.md"
    graph = create_agent(
        Model(
            messages=iter(
                [
                    AIMessage(
                        content="",
                        tool_calls=[
                            {
                                "name": "read_file",
                                "args": {"file_path": attachment},
                                "id": "read",
                            }
                        ],
                    ),
                    AIMessage(content="Séance retrouvée."),
                ]
            )
        ),
        middleware=[
            filesystem,
            skills,
            ContextBuilderMiddleware(),
            ContextBudgetMiddleware(context_tokens=65536, output_tokens=4096),
        ],
        context_schema=AgentContext,
    )
    context = AgentContext(attachment_paths=(attachment,))
    state = {
        "messages": [HumanMessage("regarde la prépa semi ci jointe")],
        "files": attachment_files({attachment: "2026-10-10 : 3 x 10 minutes"}),
        "skills_metadata": [],  # Client state cannot suppress native discovery.
    }
    config = {"callbacks": [RetrievalTrace()]}
    result = (
        asyncio.run(graph.ainvoke(state, context=context, config=config))
        if async_mode
        else graph.invoke(state, context=context, config=config)
    )
    body = snapshot["/document-planning/SKILL.md"]
    assert context.preloaded_skills == {SKILL_PATH: body}
    assert preload_tokens(context.preloaded_skills) <= MAX_SKILL_PRELOAD_TOKENS
    assert len(prompts) == 2
    assert selections == [[SKILL_PATH]]  # One traced retrieval for both model calls.
    assert all(prompt.count(body) == 1 for prompt in prompts)
    assert prompts[0] == prompts[1]
    assert prompts[0].index(body) < prompts[0].index("Date actuelle")
    assert [m.name for m in result["messages"] if isinstance(m, ToolMessage)] == [
        "read_file"
    ]


@pytest.mark.parametrize("async_mode", [False, True])
@pytest.mark.parametrize(
    "question,attachments,expected",
    [
        ("regarde la prepa semi ci jointe", True, True),
        ("Lis ce fichier Excel", True, True),
        ("Importe le programme", True, True),
        ("Quelle est ma forme aujourd’hui ?", True, False),
        ("Le plan est joint", False, False),
    ],
)
def test_relevance_uses_latest_question_and_available_attachments(
    monkeypatch, tmp_path, async_mode, question, attachments, expected
):
    _, _, skills = skill_stack(monkeypatch, tmp_path)
    context = AgentContext(
        attachment_paths=("/attachments/example.md",) if attachments else ()
    )
    runtime = SimpleNamespace(context=context)
    # Earlier mentions must not keep reloading a skill for an unrelated question.
    state = {
        "messages": [
            HumanMessage("regarde la prépa jointe"),
            AIMessage(content="Lu."),
            HumanMessage(question),
        ]
    }
    update = (
        asyncio.run(skills.abefore_agent(state, runtime, {}))
        if async_mode
        else skills.before_agent(state, runtime, {})
    )
    assert bool(context.preloaded_skills) == expected
    section = system_skills_section(update, context)
    assert SKILL_PATH in section  # Progressive disclosure survives a retrieval miss.
    assert ("indexé à zéro" in section) == expected


def test_overlapping_runs_do_not_share_preloaded_bodies(monkeypatch, tmp_path):
    _, _, skills = skill_stack(monkeypatch, tmp_path)
    relevant = AgentContext(attachment_paths=("/attachments/example.md",))
    unrelated = AgentContext(attachment_paths=("/attachments/example.md",))

    async def invoke_both():
        await asyncio.gather(
            skills.abefore_agent(
                {"messages": [HumanMessage("Lis le fichier")]},
                SimpleNamespace(context=relevant),
                {},
            ),
            skills.abefore_agent(
                {"messages": [HumanMessage("Ma fatigue ?")]},
                SimpleNamespace(context=unrelated),
                {},
            ),
        )

    asyncio.run(invoke_both())
    assert set(relevant.preloaded_skills) == {SKILL_PATH}
    assert unrelated.preloaded_skills == {}


def test_oversized_skill_keeps_metadata_without_partial_body(monkeypatch, tmp_path):
    body = (
        "---\nname: large\ndescription: Large skill\nmetadata:\n  preload-keywords: document\n---\n"
        + "Complete instruction. " * 1000
    )
    _, _, skills = skill_stack(monkeypatch, tmp_path, {"/large/SKILL.md": body})
    context = AgentContext()
    update = skills.before_agent(
        {"messages": [HumanMessage("document")]}, SimpleNamespace(context=context), {}
    )
    assert context.preloaded_skills == {}
    assert context.skills_preload_limited
    section = system_skills_section(update, context)
    assert "/skills/system/large/SKILL.md" in section
    assert "limite de préchargement" in section
    assert "Complete instruction" not in section


def test_matching_skills_beyond_count_limit_stay_discoverable(monkeypatch, tmp_path):
    files = {
        f"/skill-{i}/SKILL.md": f"---\nname: skill-{i}\ndescription: Skill {i}\nmetadata:\n  preload-keywords: document\n---\nInstruction {i}."
        for i in range(4)
    }
    _, _, skills = skill_stack(monkeypatch, tmp_path, files)
    context = AgentContext()
    update = skills.before_agent(
        {"messages": [HumanMessage("document")]}, SimpleNamespace(context=context), {}
    )
    assert len(context.preloaded_skills) == 3
    assert context.skills_preload_limited
    section = system_skills_section(update, context)
    assert all(f"/skills/system/skill-{i}/SKILL.md" in section for i in range(4))
    assert "Instruction 3." not in section


@pytest.mark.parametrize("async_mode", [False, True])
def test_failed_body_read_is_not_silently_downgraded_to_metadata(
    monkeypatch, tmp_path, async_mode
):
    from deepagents.backends.protocol import FileDownloadResponse

    _, _, skills = skill_stack(monkeypatch, tmp_path)
    method = "adownload_files" if async_mode else "download_files"
    original = getattr(skills._backend, method)
    reads = []

    def failure(paths):
        return [
            FileDownloadResponse(path=path, content=None, error="file_not_found")
            for path in paths
        ]

    def download(paths):
        reads.append(paths)
        return original(paths) if len(reads) == 1 else failure(paths)

    async def adownload(paths):
        reads.append(paths)
        return await original(paths) if len(reads) == 1 else failure(paths)

    monkeypatch.setattr(skills._backend, method, adownload if async_mode else download)
    runtime = SimpleNamespace(
        context=AgentContext(attachment_paths=("/attachments/example.md",))
    )
    state = {"messages": [HumanMessage("Lis le fichier")]}
    with pytest.raises(RuntimeError, match="preload failed"):
        if async_mode:
            asyncio.run(skills.abefore_agent(state, runtime, {}))
        else:
            skills.before_agent(state, runtime, {})
    assert runtime.context.preloaded_skills == {}


def test_skill_preload_is_included_in_complete_request_budget(monkeypatch, tmp_path):
    from langchain_core.messages import SystemMessage

    from arete.agent.context.builder import ContextBudgetExceeded, validate_context

    _, _, skills = skill_stack(monkeypatch, tmp_path)
    context = AgentContext(attachment_paths=("/attachments/example.md",))
    update = skills.before_agent(
        {"messages": [HumanMessage("regarde la prépa jointe")]},
        SimpleNamespace(context=context),
        {},
    )
    request = SimpleNamespace(
        messages=[],
        tools=[],
        system_message=SystemMessage(system_skills_section(update, context)),
    )
    used = validate_context(request, context_tokens=65536, output_tokens=4096)
    with pytest.raises(ContextBudgetExceeded):
        validate_context(request, context_tokens=used + 4096 + 1023, output_tokens=4096)


@pytest.mark.parametrize("async_mode", [False, True])
def test_slash_command_forces_complete_skill_without_a_retrieval_match(
    monkeypatch, tmp_path, async_mode
):
    snapshot, _, skills = skill_stack(monkeypatch, tmp_path)
    # No attachments: automatic activation is ineligible, explicit selection wins.
    context = AgentContext()
    state = {"messages": [HumanMessage("/document-planning Aide-moi.")]}
    runtime = SimpleNamespace(context=context)
    if async_mode:
        asyncio.run(skills.abefore_agent(state, runtime, {}))
    else:
        skills.before_agent(state, runtime, {})
    assert context.preloaded_skills == {
        SKILL_PATH: snapshot["/document-planning/SKILL.md"]
    }


@pytest.mark.parametrize("command", ["/unknown", "/", "/document-planning /unknown"])
def test_unknown_slash_command_is_an_explicit_error(monkeypatch, tmp_path, command):
    from arete.agent.context.skills import SkillSelectionError

    _, _, skills = skill_stack(monkeypatch, tmp_path)
    with pytest.raises(SkillSelectionError):
        skills.before_agent(
            {"messages": [HumanMessage(command)]},
            SimpleNamespace(context=AgentContext()),
            {},
        )


def test_required_skill_never_silently_falls_back_to_metadata(monkeypatch, tmp_path):
    from arete.agent.context.skills import SkillSelectionError

    body = (
        "---\nname: large\ndescription: Large skill\n---\n"
        + "Complete instruction. " * 1000
    )
    _, _, skills = skill_stack(monkeypatch, tmp_path, {"/large/SKILL.md": body})
    with pytest.raises(SkillSelectionError, match="budget"):
        skills.before_agent(
            {"messages": [HumanMessage("/large Lis.")]},
            SimpleNamespace(context=AgentContext()),
            {},
        )


def test_explicit_skills_are_bounded_and_not_activated_by_prose():
    from arete.agent.context.skills import SkillSelectionError, requested_skill_paths

    catalog = [
        {"name": f"skill-{i}", "path": f"/skills/system/skill-{i}/SKILL.md"}
        for i in range(4)
    ]
    with pytest.raises(SkillSelectionError, match="maximum 3"):
        requested_skill_paths("/skill-0 /skill-1 /skill-2 /skill-3", catalog)
    assert requested_skill_paths("Explique /skill-0", catalog) == ()
    assert requested_skill_paths("https://example.com/skill-0", catalog) == ()
    assert requested_skill_paths("/skill-0 /skill-0", catalog) == (catalog[0]["path"],)
