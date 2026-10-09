"""HTTP contract for goal races; services own validation and storage."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from arete.services import goals as service

router = APIRouter(prefix="/goals", tags=["goals"])


class GoalCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    race_date: date
    distance_km: float = Field(ge=1, le=250)
    target_time_sec: int | None = Field(default=None, gt=0)
    priority: Literal["A", "B", "C"] = "A"


class GoalUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    race_date: date | None = None
    distance_km: float | None = Field(default=None, ge=1, le=250)
    target_time_sec: int | None = Field(default=None, gt=0)
    priority: Literal["A", "B", "C"] | None = None
    status: Literal["active", "done", "cancelled"] | None = None


def _found(goal: service.Goal | None) -> dict[str, Any]:
    if goal is None:
        raise HTTPException(status_code=404, detail="Objectif introuvable")
    return goal.to_dict()


@router.get("")
def list_goals(include_past: bool = False) -> list[dict[str, Any]]:
    return [g.to_dict() for g in service.list_goals(include_past=include_past)]


@router.get("/next")
def next_goal() -> dict[str, Any] | None:
    goal = service.next_goal()
    return goal.to_dict() if goal else None


@router.post("", status_code=201)
def create_goal(body: GoalCreate) -> dict[str, Any]:
    if body.race_date < date.today():
        raise HTTPException(status_code=422, detail="La date de course est passée")
    return service.create_goal(**body.model_dump()).to_dict()


@router.patch("/{goal_id}")
def update_goal(goal_id: int, body: GoalUpdate) -> dict[str, Any]:
    return _found(service.update_goal(goal_id, **body.model_dump(exclude_unset=True)))


@router.delete("/{goal_id}", status_code=204)
def delete_goal(goal_id: int) -> None:
    if not service.delete_goal(goal_id):
        raise HTTPException(status_code=404, detail="Objectif introuvable")
