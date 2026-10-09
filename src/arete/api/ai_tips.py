"""HTTP coaching cards: domain evidence plus optional model enrichment."""

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from arete.services import coaching_rules as rules
from arete.services.coaching_repository import BriefingRepository
from arete.services.coaching_rules import PostSessionResponse

router = APIRouter(prefix="/tips", tags=["tips"])


class DailyTipResponse(BaseModel):
    """Daily tip response."""

    tip: str = Field(description="Contextual training tip in French")
    priority: Literal["info", "warning", "alert"] = Field(
        description="Tip priority level"
    )
    source: Literal["agent", "rules"] = Field(
        default="rules",
        description="Whether the coaching agent wrote it, or the rule engine did",
    )
    generated_at: str = Field(description="ISO 8601 generation timestamp")


class PostSessionRequest(BaseModel):
    """Request body for post-session feedback."""

    session_type: Literal["strength", "cardio"]
    session_id: int


@router.get("/daily", response_model=DailyTipResponse)
def get_daily_tip() -> DailyTipResponse:
    # The stored briefing first: importing the agent stack (`arete.coaching`)
    # costs a second on a cold instance, and most visits find one written.
    briefing = BriefingRepository().get_for_day()
    if briefing is None:
        from arete import coaching

        briefing = coaching.get_or_create_briefing(trigger="api")
    return DailyTipResponse(
        tip=briefing.text,
        priority=briefing.priority,  # type: ignore[arg-type]
        source=briefing.source,  # type: ignore[arg-type]
        generated_at=(briefing.created_at or datetime.now(UTC)).isoformat(),
    )


@router.post("/post-session", response_model=PostSessionResponse)
def post_session_feedback(body: PostSessionRequest) -> PostSessionResponse:
    try:
        result, evidence = (
            rules._generate_strength_feedback(body.session_id)
            if body.session_type == "strength"
            else rules._generate_cardio_feedback(body.session_id)
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    from arete import coaching

    feedback, source = coaching.enrich_session_feedback(
        result.feedback, result.highlights, evidence
    )
    return PostSessionResponse(
        feedback=feedback, highlights=result.highlights, source=source
    )
