"""Pure execution policy resolved from server-selected configuration."""

from dataclasses import dataclass

from arete.agent.profiles.catalog import get_profile
from arete.agent.profiles.models import AgentProfile


@dataclass(frozen=True)
class RunPolicy:
    profile: AgentProfile

    def can_execute(
        self, capability: str, tool_name: str, read_tools: frozenset[str]
    ) -> bool:
        return capability in self.profile.capabilities and (
            self.profile.training_writes or tool_name in read_tools
        )


def resolve_policy(profile_id: str) -> RunPolicy:
    return RunPolicy(get_profile(profile_id))
