from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from arete.dataio import repository as repo

router = APIRouter()


# ---------- User Settings ----------
class UserSettingsUpdate(BaseModel):
    display_name: str = "HUNTER"
    email: str | None = None
    timezone: str = "Europe/Paris"
    weekly_training_goal: int = Field(ge=1, le=14, default=6)
    rest_day_preference: list[str] = ["monday"]
    fatigue_threshold: int = Field(ge=50, le=100, default=85)
    fitness_goal: Literal["maintenance", "build", "peak", "recovery"] = "build"
    notifications_enabled: bool = True
    theme: Literal["dark", "darker", "abyss"] = "dark"
    exercise_abbreviations: dict[str, str] = {}


class UserSettingsOut(BaseModel):
    user_id: int
    display_name: str
    email: str | None
    timezone: str
    weekly_training_goal: int
    rest_day_preference: list[str]
    fatigue_threshold: int
    fitness_goal: str
    notifications_enabled: bool
    theme: str
    exercise_abbreviations: dict[str, str]


@router.get("/settings", response_model=UserSettingsOut)
def get_settings():
    """Get current user settings."""
    settings = repo.get_user_settings(user_id=1)
    if not settings:
        # Return defaults if no settings exist
        return UserSettingsOut(
            user_id=1,
            display_name="HUNTER",
            email=None,
            timezone="Europe/Paris",
            weekly_training_goal=6,
            rest_day_preference=["monday"],
            fatigue_threshold=85,
            fitness_goal="build",
            notifications_enabled=True,
            theme="dark",
            exercise_abbreviations={},
        )
    return UserSettingsOut(**settings)


@router.put("/settings", response_model=UserSettingsOut)
def update_settings(payload: UserSettingsUpdate):
    """Update user settings."""
    settings = repo.upsert_user_settings(
        user_id=1,
        display_name=payload.display_name,
        email=payload.email,
        timezone=payload.timezone,
        weekly_training_goal=payload.weekly_training_goal,
        rest_day_preference=payload.rest_day_preference,
        fatigue_threshold=payload.fatigue_threshold,
        fitness_goal=payload.fitness_goal,
        notifications_enabled=payload.notifications_enabled,
        theme=payload.theme,
        exercise_abbreviations=payload.exercise_abbreviations,
    )
    return UserSettingsOut(**settings)
