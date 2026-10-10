"""Native skills discovery with fail-closed validation of the server bundle."""

import logging

from deepagents.middleware.skills import SkillsMiddleware
from langchain_core.messages import HumanMessage

from arete.agent.backends.skills import SYSTEM_SKILLS_ROUTE
from arete.agent.context.skills import (
    MAX_PRELOADED_SKILLS,
    preload_tokens,
    prioritize_requested,
    requested_skill_paths,
    select_preloads,
    skill_retriever,
)
from arete.agent.runtime.context import AgentContext

logger = logging.getLogger(__name__)


class SystemSkillsMiddleware(SkillsMiddleware):
    def __init__(self, *, backend, paths: set[str]):
        super().__init__(
            backend=backend,
            sources=[(SYSTEM_SKILLS_ROUTE, "Système")],
            # The context builder owns prompt ordering and token accounting.
            system_prompt=None,
        )
        self.expected_paths = {SYSTEM_SKILLS_ROUTE + path.lstrip("/") for path in paths}

    def _validated(self, update):
        # Native discovery warns and skips malformed files. Server instructions
        # must instead fail visibly if any versioned skill disappears.
        skills = update.get("skills_metadata", []) if update is not None else []
        if (
            update is None
            or update.get("skills_load_errors")
            or len(skills) != len(self.expected_paths)
            or {skill["path"] for skill in skills} != self.expected_paths
        ):
            raise RuntimeError("System skill discovery differs from the server bundle")
        return update

    def _prepare(self, state, runtime, update):
        context = getattr(runtime, "context", None)
        if not isinstance(context, AgentContext):
            return None
        # The compiled middleware is shared by overlapping invocations. Never
        # keep selection on self or accept a preload from conversation state.
        context.preloaded_skills = {}
        context.skills_preload_limited = False
        question = next(
            (
                m
                for m in reversed(state.get("messages", []))
                if isinstance(m, HumanMessage)
            ),
            None,
        )
        if context.profile != "chat" or question is None:
            return None
        retriever = skill_retriever(
            update["skills_metadata"], has_attachments=bool(context.attachment_paths)
        )
        return context, retriever, question.text

    def _preload(self, context, matches, responses, required):
        bodies, limited = select_preloads(matches, responses, required=required)
        context.preloaded_skills = bodies
        context.skills_preload_limited = limited
        logger.info(
            "System skills: matched=%d preloaded=%d tokens=%d limited=%s",
            len(matches),
            len(bodies),
            preload_tokens(bodies) if bodies else 0,
            context.skills_preload_limited,
        )

    def before_agent(self, state, runtime, config):
        # Browser threads do not persist trusted discovery state. Always load
        # from the server backend once per invocation, ignoring supplied metadata.
        update = self._validated(super().before_agent({}, runtime, config))
        prepared = self._prepare(state, runtime, update)
        if prepared is not None:
            context, retriever, query = prepared
            required = requested_skill_paths(query, update["skills_metadata"])
            matches = prioritize_requested(
                retriever.invoke(query, config=config), required
            )
            paths = [doc.metadata["path"] for doc in matches[:MAX_PRELOADED_SKILLS]]
            self._preload(
                context,
                matches,
                self._backend.download_files(paths) if paths else [],
                required,
            )
        return update

    async def abefore_agent(self, state, runtime, config):
        update = self._validated(await super().abefore_agent({}, runtime, config))
        prepared = self._prepare(state, runtime, update)
        if prepared is not None:
            context, retriever, query = prepared
            required = requested_skill_paths(query, update["skills_metadata"])
            matches = prioritize_requested(
                await retriever.ainvoke(query, config=config), required
            )
            paths = [doc.metadata["path"] for doc in matches[:MAX_PRELOADED_SKILLS]]
            responses = await self._backend.adownload_files(paths) if paths else []
            self._preload(context, matches, responses, required)
        return update
