"""Server-selected profiles sharing one coaching runtime."""

from arete.agent.profiles.models import AgentProfile, ProfileId
from arete.agent.prompts.briefing import BRIEFING_PROMPT
from arete.agent.prompts.coach import CHAT_INSTRUCTIONS
from arete.agent.prompts.session_feedback import FEEDBACK_PROMPT

PROFILES: dict[ProfileId, AgentProfile] = {
    "chat": AgentProfile(
        "chat",
        "arete_coach",
        CHAT_INSTRUCTIONS,
        ("analytics", "planning", "strength"),
        # Loading a toolkit cost one model request per turn (the loaded set
        # lives in the run's state); on a free tier requests are the budget,
        # tokens are not. Binding is not authorization: RunPolicy still
        # filters what each profile may execute.
        preloaded=("analytics", "planning", "strength"),
        training_writes=True,
        page_context=True,
        suggestions=True,
    ),
    "briefing": AgentProfile(
        "briefing",
        "arete_briefing",
        BRIEFING_PROMPT,
        ("analytics",),
        preloaded=("analytics",),
    ),
    "feedback": AgentProfile("feedback", "arete_session_feedback", FEEDBACK_PROMPT, ()),
}


def get_profile(profile_id: str) -> AgentProfile:
    if profile_id not in PROFILES:
        raise ValueError(f"Unknown agent profile: {profile_id}")
    return PROFILES[profile_id]  # type: ignore[index]
