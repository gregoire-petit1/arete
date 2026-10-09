"""HTTP contract for versioned facts, edited in Settings > Coach."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from arete.services import athlete_facts as service

router = APIRouter(prefix="/athlete-facts", tags=["coach"])
Kind = Literal["injury", "constraint", "preference", "goal", "other"]
Evidence = Literal["explicit", "hypothesis", "legacy"]


class FactCreate(BaseModel):
    kind: Kind
    text: str = Field(min_length=1, max_length=service.MAX_TEXT)
    since: date | None = None
    valid_until: date | None = None
    source_ref: str = Field(default="", max_length=service.MAX_SOURCE_REF)


class FactUpdate(BaseModel):
    kind: Kind | None = None
    text: str | None = Field(default=None, min_length=1, max_length=service.MAX_TEXT)
    status: Literal["active", "resolved"] | None = None
    since: date | None = None
    evidence: Evidence | None = None
    source_ref: str | None = Field(default=None, max_length=service.MAX_SOURCE_REF)
    valid_until: date | None = None
    expected_revision: int | None = Field(default=None, ge=1)


def _error(exc: ValueError) -> HTTPException:
    return HTTPException(
        status_code=409 if isinstance(exc, service.FactConflict) else 422,
        detail=str(exc),
    )


@router.get("")
def list_facts() -> list[dict[str, Any]]:
    return [f.to_dict() for f in service.list_facts()]


@router.post("", status_code=201)
def add_fact(body: FactCreate) -> dict[str, Any]:
    try:
        return service.add_fact(
            **body.model_dump(), source="athlete", evidence="explicit"
        ).to_dict()
    except ValueError as exc:
        raise _error(exc) from exc


@router.get("/{fact_id}/history")
def fact_history(fact_id: int) -> list[dict[str, Any]]:
    history = service.fact_history(fact_id)
    if not history:
        raise HTTPException(status_code=404, detail="Fait introuvable")
    return history


@router.patch("/{fact_id}")
def update_fact(fact_id: int, body: FactUpdate) -> dict[str, Any]:
    changes = body.model_dump(exclude_unset=True)
    if "valid_until" in changes and changes["valid_until"] is None:
        changes["clear_valid_until"] = True
    # An athlete's text correction is explicit evidence, not a new coach inference.
    if body.text is not None:
        changes["evidence"] = "explicit"
    try:
        fact = service.update_fact(fact_id, **changes)
    except ValueError as exc:
        raise _error(exc) from exc
    if fact is None:
        raise HTTPException(status_code=404, detail="Fait introuvable")
    return fact.to_dict()


@router.delete("/{fact_id}", status_code=204)
def delete_fact(
    fact_id: int, expected_revision: int | None = Query(default=None, ge=1)
) -> None:
    try:
        deleted = service.delete_fact(fact_id, expected_revision=expected_revision)
    except ValueError as exc:
        raise _error(exc) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="Fait introuvable")
