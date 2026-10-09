"""HTTP contract for the day's plan decisions; services own the rules."""

from __future__ import annotations

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException

from arete.services import plan_adaptation as service
from arete.services.plan_repository import PlanDecisionRepository

router = APIRouter(prefix="/plan", tags=["plan"])


def _today(decisions: list) -> dict[str, Any]:
    return {
        "date": date.today().isoformat(),
        "decisions": [d.to_dict() for d in decisions],
    }


@router.get("/today")
def get_today() -> dict[str, Any]:
    """What this morning's readiness did to today's plan."""
    return _today(PlanDecisionRepository().list_for_day(date.today()))


@router.post("/today/adapt")
def adapt_today() -> dict[str, Any]:
    """Decide now for today's sessions without a decision (ignores the switch)."""
    return _today(service.adapt_today(respect_setting=False))


@router.post("/decisions/{decision_id}/revert")
def revert_decision(decision_id: int) -> dict[str, Any]:
    """Restore the planned session as it was before the decision."""
    try:
        return service.revert(decision_id).to_dict()
    except LookupError:
        raise HTTPException(status_code=404, detail="Décision introuvable") from None
    except service.NothingToRevert:
        raise HTTPException(
            status_code=409, detail="Rien à rétablir pour cette décision"
        ) from None
