"""HTTP settings adapter."""

from fastapi import APIRouter

from arete.services import settings as service
from arete.services.settings import UserSettingsOut, UserSettingsUpdate

router = APIRouter()


@router.get("/settings", response_model=UserSettingsOut)
def get_settings():
    return service.get_settings()


@router.put("/settings", response_model=UserSettingsOut)
def update_settings(payload: UserSettingsUpdate):
    return service.update_settings(payload)
