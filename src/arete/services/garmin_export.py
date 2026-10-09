"""Durable outbound workout state machine; remote writes are never replayed blindly."""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from time import monotonic
from typing import Any
from uuid import uuid4

from arete.dataio.db import db_connection, transaction
from arete.garmin.workouts import canonical, convert, matches
from arete.services.documents import DocumentError
from arete.services.prescriptions import Prescription

MAX_EXPORT_SECONDS = 120
MAX_EXPORT_REQUESTS = 12
REQUEST_TIMEOUT = 10.0
MAX_REMOTE_WORKOUTS = 500
MAX_DEVICES = 50
MAX_STATUS_ROWS = 500
WORKOUT = "/workout-service/workout"
SCHEDULE = "/workout-service/schedule"


def _get(con, session_id: int) -> dict | None:
    cursor = con.execute(
        "SELECT * FROM app.garmin_exports WHERE session_id=?", [session_id]
    )
    row = cursor.fetchone()
    if not row:
        return None
    result = dict(zip([c[0] for c in cursor.description], row, strict=True))
    for field in ("remote_snapshot", "intended_payload"):
        if result[field]:
            result[field] = json.loads(result[field])
    return result


def _update(session_id: int, operation_id: str, **fields) -> dict:
    allowed = {
        "state",
        "phase",
        "workout_id",
        "schedule_id",
        "fingerprint",
        "remote_snapshot",
        "intended_payload",
        "intended_date",
        "remote_date",
        "device_id",
        "error",
    }
    assert fields.keys() <= allowed
    values = [
        json.dumps(v)
        if k in {"remote_snapshot", "intended_payload"} and v is not None
        else v
        for k, v in fields.items()
    ]
    with db_connection() as con:
        changed = con.execute(
            "UPDATE app.garmin_exports SET "
            + ",".join(f"{key}=?" for key in fields)
            + ",updated_at=current_timestamp WHERE session_id=? AND operation_id=? RETURNING session_id",
            [*values, session_id, operation_id],
        ).fetchone()
        if not changed:
            raise DocumentError(
                "Une vérification plus récente possède cette opération. Recharge son état."
            )
        result = _get(con, session_id)
    assert result
    return result


def statuses() -> list[dict]:
    with db_connection() as con:
        rows = con.execute(
            "SELECT session_id FROM app.garmin_exports ORDER BY updated_at DESC LIMIT ?",
            [MAX_STATUS_ROWS + 1],
        ).fetchall()
        if len(rows) > MAX_STATUS_ROWS:
            raise DocumentError(
                "Plus de 500 exports : réduis l’historique avant de continuer."
            )
        return [
            {
                k: v
                for k, v in (_get(con, row[0]) or {}).items()
                if k not in {"remote_snapshot", "intended_payload"}
            }
            for row in rows
        ]


class Exchange:
    def __init__(self, client=None):
        if client is None:
            from arete.garmin.client import GarminClient

            client = GarminClient()
        self.client = client
        self.deadline = monotonic() + MAX_EXPORT_SECONDS
        self.calls = 0
        self.reservation: tuple[int, str] | None = None

    def call(self, method: str, path: str, payload: Any = None):
        remaining = self.deadline - monotonic()
        if self.calls >= MAX_EXPORT_REQUESTS or remaining <= 0:
            raise DocumentError(
                "Limite de synchronisation atteinte ; vérifie l’état avant de reprendre."
            )
        if self.reservation:
            with db_connection() as con:
                row = con.execute(
                    "SELECT operation_id,state FROM app.garmin_exports WHERE session_id=?",
                    [self.reservation[0]],
                ).fetchone()
            if not row or row != (self.reservation[1], "working"):
                raise DocumentError(
                    "La réservation Garmin a changé ; aucune autre requête envoyée."
                )
        self.calls += 1
        return self.client.workout_request(
            method, path, timeout=min(REQUEST_TIMEOUT, remaining), payload=payload
        )


def devices(client=None, *, exchange: Exchange | None = None) -> list[dict]:
    exchange = exchange or Exchange(client)
    raw = exchange.call("GET", "/device-service/deviceregistration/devices")
    if not isinstance(raw, list) or len(raw) > MAX_DEVICES:
        raise DocumentError("Liste des appareils Garmin invalide ou trop grande.")
    # Only claim documented support; unknown models can still use Connect's UI.
    result = []
    for device in raw:
        name = str(
            device.get("productDisplayName")
            or device.get("displayName")
            or "Appareil Garmin"
        )
        normalized = name.lower().replace("ē", "e").replace("®", "")
        supported = (
            ["running", "cycling", "swimming", "strength"]
            if "fenix 8" in normalized or "forerunner 965" in normalized
            else []
        )
        result.append(
            {
                "id": device["deviceId"],
                "name": name,
                "sports": supported,
                "compatibility": "documented" if supported else "unknown",
                "documentation": (
                    "https://www8.garmin.com/manuals/webhelp/GUID-0221611A-992D-495E-8DED-1DD448F7A066/EN-US/GUID-92B2952D-C8D5-4F66-9FBF-5A00549F0390.html"
                    if "forerunner 965" in normalized
                    else "https://www8.garmin.com/manuals/webhelp/GUID-EECCAC99-90D6-4AB1-9A3A-EC433D3365E2/EN-US/GUID-3AA7B50B-EBE5-4A29-A15A-316849BA9BDB.html"
                )
                if supported
                else None,
            }
        )
    return result


def _payload(session_id: int) -> tuple[dict, date, str, int]:
    from arete.dataio.settings import get_user_settings
    from arete.features.hr_zones import ZoneModel

    with db_connection() as con:
        row = con.execute(
            "SELECT description,sport,prescription,date,revision,garmin_workout_id,garmin_schedule_id FROM app.planned_sessions WHERE id=?",
            [session_id],
        ).fetchone()
    if not row or not row[2]:
        raise DocumentError(
            "Cette séance n’a pas de prescription structurée exportable."
        )
    if row[5] or row[6]:
        raise DocumentError(
            "Cette séance a déjà un export Garmin dans le parcours quotidien."
        )
    settings = get_user_settings() or {}
    ranges = (
        ZoneModel.from_reference(
            lthr=settings.get("lthr"), max_hr=settings.get("max_hr")
        ).ranges()
        if settings.get("lthr") or settings.get("max_hr")
        else None
    )
    payload = convert(
        session_id,
        row[0] or "Séance Arete",
        row[1],
        Prescription.model_validate_json(row[2]),
        hr_ranges=ranges,
    )
    return payload, row[3], row[1], row[4]


def _fingerprint(payload: dict, day: date) -> str:
    return hashlib.sha256(
        json.dumps([payload, day.isoformat()], sort_keys=True).encode()
    ).hexdigest()


def _claim(
    session_id: int, *, reconcile: bool = False, revision: int | None = None
) -> dict:
    with transaction() as con:
        if revision is not None:
            locked = con.execute(
                "UPDATE app.planned_sessions SET revision=revision WHERE id=? AND revision=? RETURNING id",
                [session_id, revision],
            ).fetchone()
            if not locked:
                raise DocumentError(
                    "La séance a changé avant l’export. Recharge le planning."
                )
        old = _get(con, session_id)
        clock = con.execute("SELECT current_timestamp::TIMESTAMP").fetchone()
        assert clock is not None
        now = clock[0]
        if (
            old
            and old["state"] == "working"
            and old["updated_at"] > now - timedelta(seconds=MAX_EXPORT_SECONDS + 30)
        ):
            raise DocumentError(
                "Une synchronisation de cette séance est déjà en cours."
            )
        if (
            old
            and old["state"] in {"working", "uncertain", "conflict"}
            and not reconcile
        ):
            raise DocumentError(
                "Résultat Garmin indéterminé ou conflit : lance « Vérifier Garmin » avant de renvoyer."
            )
        if old:
            con.execute(
                "UPDATE app.garmin_exports SET state='working',operation_id=?,updated_at=current_timestamp WHERE session_id=?",
                [str(uuid4()), session_id],
            )
        else:
            if reconcile:
                raise DocumentError("Aucun export à vérifier.")
            con.execute(
                "INSERT INTO app.garmin_exports (session_id,operation_id,state) VALUES (?,?,'working')",
                [session_id, str(uuid4())],
            )
        result = _get(con, session_id)
    assert result
    return result


def export(session_id: int, device_id: int | None = None, *, client=None) -> dict:
    try:
        payload, day, sport, revision = _payload(session_id)
    except ValueError as exc:
        raise DocumentError(str(exc)) from exc
    exchange = Exchange(client)
    if device_id is not None:
        target = next(
            (d for d in devices(exchange=exchange) if d["id"] == device_id), None
        )
        if not target or sport not in target["sports"]:
            raise DocumentError(
                "Compatibilité de cette montre non vérifiée pour ce sport. Choisis Garmin Connect uniquement."
            )
    state = _claim(session_id, revision=revision)
    exchange.reservation = (session_id, state["operation_id"])
    if state["deleted"]:
        _update(session_id, state["operation_id"], state="pending_removal")
        raise DocumentError("Cette séance a été supprimée ; utilise le retrait Garmin.")
    writing = False
    try:
        _update(
            session_id,
            state["operation_id"],
            intended_payload=payload,
            intended_date=day,
            device_id=device_id,
            error=None,
        )
        workout_id = state["workout_id"]
        schedule_id = state["schedule_id"]
        if workout_id:
            remote = exchange.call("GET", f"{WORKOUT}/{workout_id}")
            if state["remote_snapshot"] and canonical(remote) != canonical(
                state["remote_snapshot"]
            ):
                return _update(
                    session_id,
                    state["operation_id"],
                    state="conflict",
                    error="L’entraînement a changé dans Garmin Connect. Il n’a pas été écrasé.",
                )
            if not matches(payload, remote):
                _update(session_id, state["operation_id"], phase="updating")
                writing = True
                exchange.call(
                    "PUT",
                    f"{WORKOUT}/{workout_id}",
                    {**remote, **payload, "workoutId": workout_id},
                )
                _update(session_id, state["operation_id"], phase="updated")
                writing = False
        else:
            _update(session_id, state["operation_id"], phase="creating")
            writing = True
            created = exchange.call("POST", WORKOUT, payload)
            workout_id = int(created["workoutId"])
            _update(
                session_id,
                state["operation_id"],
                workout_id=workout_id,
                phase="created",
            )
            writing = False
        remote = exchange.call("GET", f"{WORKOUT}/{workout_id}")
        if not matches(payload, remote):
            return _update(
                session_id,
                state["operation_id"],
                state="conflict",
                error="La relecture Garmin ne correspond pas à la prescription demandée.",
            )
        _update(session_id, state["operation_id"], remote_snapshot=remote)
        if schedule_id:
            scheduled = exchange.call("GET", f"{SCHEDULE}/{schedule_id}")
            remote_date = str(scheduled.get("date", ""))[:10]
            if state["remote_date"] and remote_date != str(state["remote_date"]):
                return _update(
                    session_id,
                    state["operation_id"],
                    state="conflict",
                    error="La date a changé dans Garmin Connect.",
                )
            if remote_date != day.isoformat():
                _update(session_id, state["operation_id"], phase="unscheduling")
                writing = True
                exchange.call("DELETE", f"{SCHEDULE}/{schedule_id}")
                _verify_absent(exchange, f"{SCHEDULE}/{schedule_id}")
                _update(
                    session_id,
                    state["operation_id"],
                    schedule_id=None,
                    remote_date=None,
                    phase="unscheduled",
                )
                writing = False
                schedule_id = None
        if not schedule_id:
            _update(session_id, state["operation_id"], phase="scheduling")
            writing = True
            scheduled = exchange.call(
                "POST", f"{SCHEDULE}/{workout_id}", {"date": day.isoformat()}
            )
            schedule_id = int(scheduled["workoutScheduleId"])
            _update(
                session_id,
                state["operation_id"],
                schedule_id=schedule_id,
                phase="scheduled",
            )
            writing = False
        verified = exchange.call("GET", f"{SCHEDULE}/{schedule_id}")
        if (
            str(verified.get("date", ""))[:10] != day.isoformat()
            or int(verified.get("workoutId", 0)) != workout_id
        ):
            return _update(
                session_id,
                state["operation_id"],
                state="conflict",
                error="La programmation Garmin n’a pas pu être vérifiée.",
            )
        _update(
            session_id,
            state["operation_id"],
            remote_date=day,
            fingerprint=_fingerprint(payload, day),
            phase="scheduled",
        )
        already_pushed = (
            state["phase"] == "pushed"
            and state["device_id"] == device_id
            and state["fingerprint"] == _fingerprint(payload, day)
        )
        if device_id is not None and not already_pushed:
            _update(session_id, state["operation_id"], phase="pushing")
            writing = True
            exchange.call(
                "POST",
                "/device-service/devicemessage/messages",
                [
                    {
                        "deviceId": device_id,
                        "messageUrl": f"workout-service/workout/FIT/{workout_id}",
                        "messageType": "workouts",
                        "groupName": None,
                        "messageName": payload["workoutName"],
                        "priority": 1,
                        "fileType": "FIT",
                        "metaDataId": workout_id,
                    }
                ],
            )
            _update(session_id, state["operation_id"], phase="pushed")
            writing = False
        return _update(
            session_id,
            state["operation_id"],
            state="transfer_requested" if device_id else "scheduled",
            phase="pushed" if device_id else "scheduled",
        )
    except Exception as exc:
        return _update(
            session_id,
            state["operation_id"],
            state="uncertain"
            if writing and not isinstance(exc, PermissionError)
            else "failed",
            error=f"{type(exc).__name__}: {exc}. Aucun renvoi automatique.",
        )


def reconcile(session_id: int, *, client=None) -> dict:
    state = _claim(session_id, reconcile=True)
    exchange = Exchange(client)
    exchange.reservation = (session_id, state["operation_id"])
    try:
        workout_id = state["workout_id"]
        if not workout_id:
            candidates: list[dict] = []
            for start in range(0, MAX_REMOTE_WORKOUTS, 100):
                page = exchange.call(
                    "GET", f"/workout-service/workouts?start={start}&limit=100"
                )
                if not isinstance(page, list) or len(page) > 100:
                    raise DocumentError("Réponse Garmin inattendue.")
                candidates.extend(
                    w
                    for w in page
                    if w.get("description") == f"ARETE_SESSION:{session_id}"
                )
                if len(page) < 100:
                    break
            if len(candidates) != 1:
                raise DocumentError(
                    "Impossible d’identifier un entraînement unique. Vérifie Garmin Connect ; aucun nouvel entraînement ne sera créé automatiquement."
                )
            workout_id = int(candidates[0]["workoutId"])
        try:
            remote = exchange.call("GET", f"{WORKOUT}/{workout_id}")
        except LookupError:
            if state["deleted"] and state["phase"] == "removing":
                return _update(
                    session_id,
                    state["operation_id"],
                    state="removed",
                    workout_id=None,
                    schedule_id=None,
                    error=None,
                )
            raise
        expected = state["intended_payload"]
        if not expected or not matches(expected, remote):
            return _update(
                session_id,
                state["operation_id"],
                state="conflict",
                error="Le contenu Garmin diffère du contenu attendu.",
            )
        schedule_id = state["schedule_id"]
        remote_date = state["remote_date"]
        if state["phase"] in {"unscheduling", "removing"} and schedule_id:
            try:
                scheduled = exchange.call("GET", f"{SCHEDULE}/{schedule_id}")
                if int(scheduled.get("workoutId", 0)) != workout_id:
                    raise DocumentError(
                        "La programmation ne correspond plus à cette séance."
                    )
            except LookupError:
                schedule_id = None
                remote_date = None
        elif state["phase"] == "scheduling":
            day = state["intended_date"] or remote_date
            calendar = exchange.call(
                "GET", f"/calendar-service/year/{day.year}/month/{day.month - 1}"
            )
            entries = calendar.get("calendarItems", [])
            if len(entries) > 1000:
                raise DocumentError("Calendrier Garmin trop volumineux.")
            found = [
                e
                for e in entries
                if int(e.get("workoutId") or 0) == workout_id
                and str(e.get("date", ""))[:10] == day.isoformat()
            ]
            if len(found) != 1:
                raise DocumentError(
                    "Programmation indéterminée ; vérification manuelle requise dans Garmin Connect."
                )
            schedule_id = int(found[0].get("workoutScheduleId") or found[0]["id"])
            remote_date = day
        elif schedule_id:
            scheduled = exchange.call("GET", f"{SCHEDULE}/{schedule_id}")
            remote_date = date.fromisoformat(str(scheduled["date"])[:10])
            if state["remote_date"] and remote_date != state["remote_date"]:
                return _update(
                    session_id,
                    state["operation_id"],
                    state="conflict",
                    error="La date distante a été modifiée.",
                )
        if state["phase"] == "pushing":
            return _update(
                session_id,
                state["operation_id"],
                state="uncertain",
                error="Le calendrier est vérifiable, mais le transfert vers la montre a un résultat inconnu. Vérifie la montre avant toute nouvelle demande.",
            )
        return _update(
            session_id,
            state["operation_id"],
            state="pending_removal" if state["deleted"] else "ready",
            workout_id=workout_id,
            schedule_id=schedule_id,
            remote_snapshot=remote,
            remote_date=remote_date,
            error=None,
        )
    except Exception as exc:
        return _update(
            session_id, state["operation_id"], state="uncertain", error=str(exc)
        )


def _verify_absent(exchange: Exchange, path: str) -> None:
    try:
        exchange.call("GET", path)
    except LookupError:
        return
    raise DocumentError("La suppression distante n’est pas confirmée par relecture.")


def remove(session_id: int, *, client=None) -> dict:
    state = _claim(session_id)
    if not state["deleted"]:
        _update(session_id, state["operation_id"], state="ready")
        raise DocumentError("Le retrait est réservé aux séances supprimées dans Arete.")
    exchange = Exchange(client)
    exchange.reservation = (session_id, state["operation_id"])
    writing = False
    try:
        workout_id = state["workout_id"]
        if workout_id:
            remote = exchange.call("GET", f"{WORKOUT}/{workout_id}")
            if remote.get("description") != f"ARETE_SESSION:{session_id}" or (
                state["remote_snapshot"]
                and canonical(remote) != canonical(state["remote_snapshot"])
            ):
                return _update(
                    session_id,
                    state["operation_id"],
                    state="conflict",
                    error="L’entraînement distant a changé ; retrait bloqué.",
                )
            _update(session_id, state["operation_id"], phase="removing")
            writing = True
            if state["schedule_id"]:
                exchange.call("DELETE", f"{SCHEDULE}/{state['schedule_id']}")
                _verify_absent(exchange, f"{SCHEDULE}/{state['schedule_id']}")
                _update(session_id, state["operation_id"], schedule_id=None)
            exchange.call("DELETE", f"{WORKOUT}/{workout_id}")
            _verify_absent(exchange, f"{WORKOUT}/{workout_id}")
        return _update(
            session_id,
            state["operation_id"],
            state="removed",
            workout_id=None,
            schedule_id=None,
            error=None,
        )
    except Exception as exc:
        return _update(
            session_id,
            state["operation_id"],
            state="uncertain"
            if writing and not isinstance(exc, PermissionError)
            else "failed",
            error=str(exc),
        )


def update_session(
    session_id: int,
    revision: int,
    day: date,
    description: str,
    prescription: Prescription,
) -> None:
    with transaction() as con:
        current = con.execute(
            "SELECT prescription,garmin_workout_id,garmin_schedule_id FROM app.planned_sessions WHERE id=?",
            [session_id],
        ).fetchone()
        # Keep the two export owners disjoint: a daily session may already be
        # uploading, even before its remote IDs have been saved locally.
        if current and (not current[0] or current[1] or current[2]):
            raise DocumentError("Cette séance utilise le parcours Garmin quotidien.")
        state = _get(con, session_id)
        if state and state["state"] in {"working", "uncertain", "conflict"}:
            raise DocumentError("Vérifie l’export Garmin avant de modifier la séance.")
        changed = con.execute(
            "UPDATE app.planned_sessions SET date=?,description=?,prescription=?,revision=revision+1 WHERE id=? AND revision=? RETURNING id",
            [day, description, prescription.model_dump_json(), session_id, revision],
        ).fetchone()
        if not changed:
            raise DocumentError(
                "La séance a changé ou n’existe plus. Recharge le planning."
            )
        con.execute(
            "UPDATE app.garmin_exports SET state='dirty',updated_at=current_timestamp WHERE session_id=? AND state<>'removed'",
            [session_id],
        )
