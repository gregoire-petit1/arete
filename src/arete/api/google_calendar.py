"""Calendar HTTP surface; mutations require same-origin application requests.

Each signed-in account has its own calendar: the service is built from the
verified identity, never from anything the browser sends.
"""

from contextlib import contextmanager
from typing import Literal
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict

from arete.api.auth import clerk_account
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


def same_origin(request: Request) -> None:
    # Custom headers cannot be sent by cross-site forms, and CORS is not enabled.
    if request.headers.get("x-arete-calendar") != "1":
        raise HTTPException(403, "Requête Calendar non autorisée.")
    origin = request.headers.get("origin")
    if origin and not _trusted_origin(request, origin):
        raise HTTPException(403, "Origine Calendar non autorisée.")


def _trusted_origin(request: Request, origin: str) -> bool:
    """The configured frontend, or the very host the request was sent to.

    A deployment answers on several hosts (preview URLs, aliases) behind one
    ``FRONTEND_URL``; a page served by the same host is same-origin by
    definition. The dev server proxies from another port and matches the first.
    """
    if origin.rstrip("/") == config.frontend_url.rstrip("/"):
        return True
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    return bool(host) and urlparse(origin).netloc == host


@contextmanager
def service(request: Request):
    try:
        yield get_calendar_service(clerk_account(request))
    except CalendarError as exc:
        raise HTTPException(exc.status, str(exc)) from exc


@router.get("/status")
def status(request: Request):
    if not config.google_calendar_configured:
        return {
            "configured": False,
            "connected": False,
            "selection": {"readable": [], "writable": []},
        }
    with service(request) as calendar:
        return calendar.status()


@router.post("/connect", dependencies=[Depends(same_origin)])
def connect(request: Request):
    """After Google's consent in the browser: turn access on if it was granted."""
    with service(request) as calendar:
        return calendar.connect()


@router.post("/disconnect", dependencies=[Depends(same_origin)])
def disconnect(request: Request):
    with service(request) as calendar:
        return calendar.disconnect()


@router.get("/calendars")
def calendars(request: Request):
    with service(request) as calendar:
        return calendar.calendars()


@router.put("/selection", dependencies=[Depends(same_origin)])
def selection(request: Request, body: CalendarSelection):
    with service(request) as calendar:
        return calendar.select(body)


@router.get("/events")
def events(request: Request, start: str, end: str):
    with service(request) as calendar:
        return calendar.events(start, end)


@router.get("/availability")
def availability(request: Request, start: str, end: str):
    with service(request) as calendar:
        return calendar.availability(start, end)


class Decision(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject"]


@router.get("/actions/{action_id}")
def action(request: Request, action_id: str):
    with service(request) as calendar:
        return calendar.repo.get(action_id)


@router.post("/actions/{action_id}/decision", dependencies=[Depends(same_origin)])
def decide(request: Request, action_id: str, body: Decision):
    with service(request) as calendar:
        return calendar.decide(action_id, body.decision)


@router.post("/actions/{action_id}/verify", dependencies=[Depends(same_origin)])
def verify(request: Request, action_id: str):
    with service(request) as calendar:
        return calendar.verify(action_id)
