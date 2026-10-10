"""HTTP feedback contracts; the LangSmith SDK stays lazy on cold boots."""

from __future__ import annotations

import logging
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field, StrictInt, StrictStr, model_validator

from arete.api.auth import clerk_account
from arete.config import config

logger = logging.getLogger(__name__)
router = APIRouter()
MAX_EMOJI_CODEPOINTS = 32


class TraceReceipt(BaseModel):
    trace_id: UUID
    feedback_token: str = Field(pattern=r"^[0-9a-f]{64}$")


def chat_trace(trace_id: UUID, thread_id: str | None, account_id: str):
    if not config.langsmith_tracing:
        return None
    from arete.observability.feedback import receipt

    return TraceReceipt(
        trace_id=trace_id,
        feedback_token=receipt(
            trace_id, UUID(thread_id) if thread_id else None, account_id
        ),
    )


class FeedbackRequest(BaseModel):
    thread_id: UUID | None = None
    feedback_token: str = Field(pattern=r"^[0-9a-f]{64}$")


class FeedbackWrite(FeedbackRequest):
    key: Literal["user_score", "reaction"]
    value: StrictInt | StrictStr | None = None

    @model_validator(mode="after")
    def valid_value(self):
        if self.value is None:
            return self
        if self.key == "user_score":
            if type(self.value) is not int or self.value not in (0, 1):
                raise ValueError("La note doit être 0 ou 1.")
            return self
        # Grapheme segmentation preserves ZWJ families, flags and skin tones.
        import regex

        if (
            not isinstance(self.value, str)
            or len(self.value) > MAX_EMOJI_CODEPOINTS
            or not regex.fullmatch(r"\X", self.value)
            or not regex.search(
                r"\p{Extended_Pictographic}|\p{Regional_Indicator}{2}|[#*0-9]\ufe0f?\u20e3",
                self.value,
            )
        ):
            raise ValueError("Choisis un seul emoji (32 caractères maximum).")
        return self


class FeedbackState(BaseModel):
    user_score: Literal[0, 1] | None
    reaction: str | None


def _operation(trace_id: UUID, body: FeedbackRequest, request: Request, *, write: bool):
    from langsmith.utils import LangSmithError
    from requests.exceptions import RequestException

    from arete.observability import feedback

    try:
        feedback.authorize(
            trace_id, body.thread_id, clerk_account(request), body.feedback_token
        )
        if write:
            assert isinstance(body, FeedbackWrite)
            feedback.write_feedback(trace_id, body.key, body.value)
            return None
        return feedback.read_state(trace_id)
    except feedback.FeedbackUnavailable as exc:
        raise HTTPException(503, str(exc)) from None
    except PermissionError as exc:
        raise HTTPException(403, str(exc)) from None
    except (LangSmithError, RequestException) as exc:
        # Never expose SDK exception bodies, which can contain credentials.
        logger.warning("LangSmith feedback failed (%s)", type(exc).__name__)
        raise HTTPException(
            502,
            "Enregistrement non confirmé. Vérifie le retour avant de le renvoyer.",
        ) from None


@router.post("/feedback/{trace_id}/read", response_model=FeedbackState)
def read_feedback(trace_id: UUID, body: FeedbackRequest, request: Request):
    # POST keeps the receipt out of URL/access logs; this endpoint only reads.
    return _operation(trace_id, body, request, write=False)


@router.put("/feedback/{trace_id}", status_code=204)
def write_feedback(trace_id: UUID, body: FeedbackWrite, request: Request):
    _operation(trace_id, body, request, write=True)
    return Response(status_code=204)
