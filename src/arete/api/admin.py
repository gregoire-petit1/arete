"""Accounts and athletes for administrators; roles for the owner alone.

Reads and writes only the account tables (``app.users``, ``app.athletes``),
never an athlete's private data. The rules live in ``services.users``.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from datetime import datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from arete import scheduler
from arete.api.auth import require_admin, require_owner
from arete.services import users
from arete.services.users import AccountError, AppUser

router = APIRouter(
    prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)]
)


class AccountOut(BaseModel):
    athlete_id: int
    user_id: int | None
    email: str | None
    name: str | None
    role: str
    is_owner: bool
    last_seen_at: datetime | None
    last_sync_at: datetime | None
    sync_lease_until: datetime | None
    lease_stuck: bool
    deactivated_at: datetime | None


class RoleUpdate(BaseModel):
    role: Literal["athlete", "admin"]


@contextmanager
def _rules() -> Iterator[None]:
    try:
        yield
    except AccountError as e:
        raise HTTPException(status_code=e.status, detail=str(e)) from None


@router.get("/accounts", response_model=list[AccountOut])
def list_accounts() -> list[dict[str, Any]]:
    """Every athlete with its logins, roles, last activity and daily sync."""
    return [account.to_dict() for account in users.list_accounts()]


@router.post("/accounts/{user_id}/role", dependencies=[Depends(require_owner)])
def set_role(user_id: int, body: RoleUpdate) -> dict[str, Any]:
    with _rules():
        return users.set_role(user_id, body.role).to_dict()


@router.post("/athletes/{athlete_id}/deactivate", status_code=204)
def deactivate(athlete_id: int, actor: AppUser = Depends(require_admin)) -> Response:
    with _rules():
        users.deactivate_athlete(athlete_id, actor=actor)
    return Response(status_code=204)


@router.post("/athletes/{athlete_id}/reactivate", status_code=204)
def reactivate(athlete_id: int) -> Response:
    with _rules():
        users.reactivate_athlete(athlete_id)
    return Response(status_code=204)


@router.post("/athletes/{athlete_id}/release-lease")
def release_lease(athlete_id: int) -> dict[str, bool]:
    """After a failed or stopped daily sync, let the next window run it again."""
    return {"released": scheduler.release_sync_lease(athlete_id)}
