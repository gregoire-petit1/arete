"""Native skills discovery with fail-closed validation of the server bundle."""

from deepagents.middleware.skills import SkillsMiddleware

from arete.agent.backends.skills import SYSTEM_SKILLS_ROUTE


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

    def before_agent(self, state, runtime, config):
        # Browser threads do not persist trusted discovery state. Always load
        # from the server backend once per invocation, ignoring supplied metadata.
        return self._validated(super().before_agent({}, runtime, config))

    async def abefore_agent(self, state, runtime, config):
        return self._validated(await super().abefore_agent({}, runtime, config))
