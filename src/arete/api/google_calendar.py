"""Calendar HTTP surface; mutations require same-origin application requests."""

import hmac
import secrets
from contextlib import contextmanager
from typing import Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, ConfigDict

from arete.calendar import get_calendar_service
from arete.config import config
from arete.services.calendar_models import CalendarError, CalendarSelection


def no_store(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"


router = APIRouter(
    prefix="/google-calendar",
    tags=["google-calendar"],
    dependencies=[Depends(no_store)],
)
COOKIE = "arete_calendar_consent"


def same_origin(request: Request) -> None:
    # Custom headers cannot be sent by cross-site forms, and CORS is not enabled.
    if request.headers.get("x-arete-calendar") != "1":
        raise HTTPException(403, "Requête Calendar non autorisée.")
    origin = request.headers.get("origin")
    if origin and origin.rstrip("/") != config.frontend_url.rstrip("/"):
        raise HTTPException(403, "Origine Calendar non autorisée.")


@contextmanager
def service():
    try:
        yield get_calendar_service()
    except CalendarError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


@router.get("/status")
def status():
    if not config.google_calendar_configured:
        return {
            "configured": False,
            "connected": False,
            "selection": {"readable": [], "writable": []},
        }
    with service() as calendar:
        return calendar.status()


@router.post("/authorize", dependencies=[Depends(same_origin)])
def authorize(response: Response):
    base = config.frontend_url.rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme != "https" and not (
        parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1"}
    ):
        raise HTTPException(
            503, "FRONTEND_URL doit être HTTPS, ou localhost en développement."
        )
    nonce = secrets.token_urlsafe(32)
    with service() as calendar:
        url = calendar.authorize(
            nonce, base + "/api/google-calendar/callback?state=" + nonce
        )
    response.set_cookie(
        COOKIE,
        nonce,
        max_age=900,
        httponly=True,
        secure=parsed.scheme == "https",
        samesite="lax",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    return {"url": url}


@router.get("/callback")
def callback(request: Request, state: str = "", error: str = ""):
    cookie = request.cookies.get(COOKIE, "")
    if not state or not cookie or not hmac.compare_digest(state, cookie):
        raise HTTPException(403, "Retour Calendar invalide.")
    result = "error"
    try:
        get_calendar_service().complete_consent(state, granted=not bool(error))
        result = "connected"
    except CalendarError:
        # Provider detail can contain secrets. Only a fixed status reaches the URL.
        result = "error"
    response = RedirectResponse(
        config.frontend_url.rstrip("/")
        + "/settings?tab=connections&google_calendar="
        + result,
        status_code=303,
    )
    response.delete_cookie(COOKIE, path="/")
    response.headers["Cache-Control"] = "no-store"
    return response


@router.post("/disconnect", dependencies=[Depends(same_origin)])
def disconnect():
    with service() as calendar:
        return calendar.disconnect()


@router.get("/calendars")
def calendars():
    with service() as calendar:
        return calendar.calendars()


@router.put("/selection", dependencies=[Depends(same_origin)])
def selection(body: CalendarSelection):
    with service() as calendar:
        return calendar.select(body)


@router.get("/events")
def events(start: str, end: str):
    with service() as calendar:
        return calendar.events(start, end)


@router.get("/availability")
def availability(start: str, end: str):
    with service() as calendar:
        return calendar.availability(start, end)


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject"]


@router.get("/actions/{action_id}")
def action(action_id: str):
    with service() as calendar:
        return calendar.repo.get(action_id)


@router.post("/actions/{action_id}/decision", dependencies=[Depends(same_origin)])
def decide(action_id: str, body: Decision):
    with service() as calendar:
        return calendar.decide(action_id, body.decision)


@router.post("/actions/{action_id}/verify", dependencies=[Depends(same_origin)])
def verify(action_id: str):
    with service() as calendar:
        return calendar.verify(action_id)
