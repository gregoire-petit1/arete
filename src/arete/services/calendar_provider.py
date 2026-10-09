"""Bounded HTTP adapters. Connect's wire contract follows @vercel/connect 2.4.1.

No provider credentials are persisted or exposed to the model. A session reuses
one short-lived token only for the current operation, so disconnects/revocations
are checked on the next operation even across separate serverless instances.
"""

import json
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from time import monotonic
from urllib.parse import quote, urlparse

import httpx

from arete.services.calendar_models import (
    HTTP_TIMEOUT_SECONDS,
    MAX_OPERATION_SECONDS,
    MAX_RESPONSE_BYTES,
    MAX_RESPONSE_CHUNKS,
    SCOPES,
    CalendarError,
)


class CalendarHTTP:
    def __init__(self, client: httpx.Client, deadline: float):
        self.client = client
        self.deadline = deadline

    def request(self, method: str, url: str, *, write: bool = False, **kwargs) -> dict:
        remaining = self.deadline - monotonic()
        if remaining <= 0:
            raise CalendarError("Délai Calendar dépassé.", 504)
        try:
            with self.client.stream(
                method, url, timeout=min(HTTP_TIMEOUT_SECONDS, remaining), **kwargs
            ) as response:
                body = bytearray()
                for index, chunk in enumerate(response.iter_bytes()):
                    if (
                        index >= MAX_RESPONSE_CHUNKS
                        or len(body) + len(chunk) > MAX_RESPONSE_BYTES
                        or monotonic() > self.deadline
                    ):
                        raise CalendarError(
                            "Réponse Calendar hors limites.", 502, uncertain=write
                        )
                    body.extend(chunk)
                if response.status_code >= 400:
                    status = response.status_code
                    labels = {
                        401: "Connexion expirée : reconnecte Google Calendar.",
                        403: "Permission Google insuffisante.",
                        404: "Événement ou calendrier introuvable.",
                        409: "Conflit Calendar.",
                        412: "Événement modifié depuis la proposition : nouvelle validation nécessaire.",
                        429: "Quota Google Calendar atteint. Réessaie plus tard.",
                    }
                    raise CalendarError(
                        labels.get(status, "Service Calendar indisponible."),
                        status if status in labels else 502,
                        uncertain=write and status >= 500,
                    )
                if not body:
                    return {}
                result = json.loads(body)
                if not isinstance(result, dict):
                    raise ValueError("object expected")
                return result
        except (httpx.HTTPError, ValueError) as exc:
            raise CalendarError(
                "Réponse du fournisseur indisponible ou invalide.", 502, uncertain=write
            ) from exc


class ConnectProvider:
    def __init__(
        self,
        connector: str,
        subject: str,
        credential: Callable[[], str],
        *,
        transport: httpx.BaseTransport | None = None,
    ):
        self.connector = connector
        self.subject = {"type": "user", "id": subject}
        self.credential = credential
        self.transport = transport

    @contextmanager
    def session(self, deadline: float | None = None) -> Iterator[CalendarHTTP]:
        limit = min(deadline or float("inf"), monotonic() + MAX_OPERATION_SECONDS)
        with httpx.Client(
            transport=self.transport,
            follow_redirects=False,
            timeout=HTTP_TIMEOUT_SECONDS,
        ) as client:
            yield CalendarHTTP(client, limit)

    def connect(
        self, http: CalendarHTTP, method: str, path: str, payload: dict
    ) -> dict:
        credential = self.credential()
        if not credential:
            raise CalendarError(
                "Vercel Connect non configuré : credential serveur manquant.", 503
            )
        return http.request(
            method,
            "https://api.vercel.com/v1/connect/" + path,
            json=payload,
            headers={"Authorization": f"Bearer {credential}"},
        )

    def token(self, http: CalendarHTTP) -> str:
        data = self.connect(
            http,
            "POST",
            "token/" + quote(self.connector, safe=""),
            {"subject": self.subject, "scopes": SCOPES},
        )
        token = data.get("token")
        if not isinstance(token, str) or not token:
            raise CalendarError("Jeton Google manquant dans la réponse Connect.", 502)
        return token

    def authorize(self, http: CalendarHTTP, callback: str) -> str:
        data = self.connect(
            http,
            "POST",
            "authorize/" + quote(self.connector, safe=""),
            {
                "subject": self.subject,
                "scopes": SCOPES,
                "returnUrl": callback,
                "expiresInMs": 900_000,
            },
        )
        url = data.get("url", "")
        if not isinstance(url, str) or urlparse(url).scheme != "https":
            raise CalendarError("URL de consentement Connect invalide.", 502)
        return url

    def revoke(self, http: CalendarHTTP) -> None:
        self.connect(
            http,
            "DELETE",
            "connectors/" + quote(self.connector, safe="") + "/tokens",
            {"subject": self.subject},
        )


class GoogleCalendar:
    def __init__(self, http: CalendarHTTP, token: str):
        self.http, self.token = http, token

    def call(
        self, method: str, path: str, *, etag: str | None = None, **kwargs
    ) -> dict:
        headers = {"Authorization": f"Bearer {self.token}"}
        if etag:
            headers["If-Match"] = etag
        return self.http.request(
            method,
            "https://www.googleapis.com/calendar/v3/" + path,
            headers=headers,
            write=method in {"PATCH", "DELETE", "PUT"}
            or (method == "POST" and path != "freeBusy"),
            **kwargs,
        )

    @staticmethod
    def events_path(calendar_id: str, event_id: str | None = None) -> str:
        base = "calendars/" + quote(calendar_id, safe="") + "/events"
        return base + "/" + quote(event_id, safe="") if event_id else base
