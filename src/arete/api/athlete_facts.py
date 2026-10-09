"""HTTP contract for the athlete's durable facts, edited in Settings > Coach."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from arete.services import athlete_facts as service

router = APIRouter(prefix="/athlete-facts", tags=["coach"])

Kind = Literal["injury", "constraint", "preference", "goal", "other"]


class FactCreate(BaseModel):
    kind: Kind
    text: str = Field(min_length=1, max_length=service.MAX_TEXT)
    since: date | None = None


class FactUpdate(BaseModel):
    kind: Kind | None = None
    text: str | None = Field(default=None, min_length=1, max_length=service.MAX_TEXT)
    status: Literal["active", "resolved"] | None = None
    since: date | None = None


@router.get("")
def list_facts() -> list[dict[str, Any]]:
    return [f.to_dict() for f in service.list_facts()]


@router.post("", status_code=201)
def add_fact(body: FactCreate) -> dict[str, Any]:
    return service.add_fact(
        body.kind, body.text, since=body.since, source="athlete"
    ).to_dict()


@router.patch("/{fact_id}")
def update_fact(fact_id: int, body: FactUpdate) -> dict[str, Any]:
    fact = service.update_fact(fact_id, **body.model_dump(exclude_unset=True))
    if fact is None:
        raise HTTPException(status_code=404, detail="Fait introuvable")
    return fact.to_dict()


@router.delete("/{fact_id}", status_code=204)
def delete_fact(fact_id: int) -> None:
    if not service.delete_fact(fact_id):
        raise HTTPException(status_code=404, detail="Fait introuvable")
