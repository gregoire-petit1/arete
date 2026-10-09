"""Outbound Garmin contracts with a stateful fake, including lost responses."""

import copy
import json
from datetime import date

import pytest

from arete.dataio.db import db_connection
from arete.dataio.init_duckdb import main
from arete.garmin.repository import GarminRepository
from arete.garmin.workouts import convert
from arete.services import garmin_export as service
from arete.services.documents import DocumentError
from arete.services.prescriptions import Prescription, Step, Target


class Garmin:
    def __init__(self):
        self.calls = []
        self.workouts = {}
        self.schedules = {}
        self.fail = None
        self.on_create = None

    def workout_request(self, method, path, *, timeout, payload=None):
        assert 0 < timeout <= 15
        self.calls.append((method, path, copy.deepcopy(payload)))
        if self.fail == "read":
            raise ConnectionError("offline")
        if path == "/device-service/deviceregistration/devices":
            return [{"deviceId": 10, "displayName": "fēnix 8"}]
        if path.startswith("/workout-service/workouts?"):
            return list(self.workouts.values())
        if path.startswith("/calendar-service"):
            return {"calendarItems": list(self.schedules.values())}
        if path == "/workout-service/workout" and method == "POST":
            if self.on_create:
                self.on_create()
            identifier = len(self.workouts) + 1
            self.workouts[identifier] = {
                **copy.deepcopy(payload),
                "workoutId": identifier,
            }
            if self.fail == "create":
                self.fail = None
                raise TimeoutError("response lost after committed creation")
            return {"workoutId": identifier}
        if path.startswith("/workout-service/workout/"):
            identifier = int(path.rsplit("/", 1)[1])
            if identifier not in self.workouts:
                raise LookupError("404")
            if method == "GET":
                return copy.deepcopy(self.workouts[identifier])
            if method == "PUT":
                self.workouts[identifier] = copy.deepcopy(payload)
                return copy.deepcopy(payload)
            if method == "DELETE":
                del self.workouts[identifier]
                if self.fail == "delete":
                    self.fail = None
                    raise TimeoutError("deleted remotely")
                return {}
        if path.startswith("/workout-service/schedule/"):
            identifier = int(path.rsplit("/", 1)[1])
            if method == "POST":
                schedule_id = len(self.schedules) + 100
                record = {
                    "workoutId": identifier,
                    "workoutScheduleId": schedule_id,
                    "date": payload["date"],
                }
                self.schedules[schedule_id] = record
                if self.fail == "schedule":
                    self.fail = None
                    raise TimeoutError("response lost after committed schedule")
                return record
            if identifier not in self.schedules:
                raise LookupError("404")
            if method == "GET":
                return copy.deepcopy(self.schedules[identifier])
            if method == "DELETE":
                del self.schedules[identifier]
                return {}
        if path == "/device-service/devicemessage/messages":
            return {"accepted": True}
        raise AssertionError((method, path))


@pytest.fixture
def planned(tmp_path, monkeypatch):
    monkeypatch.setenv("ARETE_DB", str(tmp_path / "export.duckdb"))
    main()
    prescription = Prescription(
        steps=[Step(kind="effort", duration_kind="seconds", value=1800)]
    )
    with db_connection() as con:
        identifier = con.execute(
            "INSERT INTO app.planned_sessions (date,sport,session_type,description,prescription) VALUES ('2027-01-12','running','endurance','Footing',?) RETURNING id",
            [prescription.model_dump_json()],
        ).fetchone()[0]
    return identifier


@pytest.mark.parametrize(
    "sport,identifier",
    [
        ("running", 1),
        ("cycling", 2),
        ("swimming", 4),
        ("strength", 5),
        ("walking", 17),
        ("hiking", 18),
    ],
)
def test_sport_conversion_preserves_workout_units(sport, identifier):
    step = Step(kind="effort", duration_kind="meters", value=400)
    if sport == "strength":
        step = Step(
            kind="effort",
            duration_kind="reps",
            value=8,
            exercise="Barbell Bench Press",
            weight_kg=60,
        )
    prescription = Prescription(
        steps=[step], pool_length_m=25 if sport == "swimming" else None
    )
    payload = convert(42, "Test", sport, prescription)
    assert payload["sportType"]["sportTypeId"] == identifier
    converted = payload["workoutSegments"][0]["workoutSteps"][0]
    assert converted["endConditionValue"] == (8 if sport == "strength" else 400)
    if sport == "strength":
        assert converted["weightValue"] == 60_000
        assert converted["stepOrder"] == 1
    if sport == "swimming":
        assert payload["poolLength"] == 25


def test_repeats_pace_and_secondary_targets():
    prescription = Prescription(
        steps=[
            Step(
                kind="repeat",
                repeat=6,
                steps=[
                    Step(
                        kind="effort",
                        duration_kind="meters",
                        value=400,
                        target=Target(kind="pace_sec_km", low=270, high=290),
                        secondary_target=Target(
                            kind="heart_rate_bpm", low=150, high=170
                        ),
                    ),
                    Step(kind="recovery", duration_kind="seconds", value=90),
                ],
            )
        ]
    )
    payload = convert(1, "6 x 400", "running", prescription)
    group = payload["workoutSegments"][0]["workoutSteps"][0]
    assert group["numberOfIterations"] == 6
    effort = group["workoutSteps"][0]
    assert effort["targetValueOne"] == pytest.approx(1000 / 290)
    assert effort["targetValueTwo"] == pytest.approx(1000 / 270)
    assert effort["secondaryTargetValueOne"] == 150


def test_export_and_repeat_do_not_duplicate_workout_or_date(planned):
    garmin = Garmin()
    result = service.export(planned, client=garmin)
    assert result["state"] == "scheduled", result
    assert service.export(planned, client=garmin)["state"] == "scheduled"
    assert len(garmin.workouts) == len(garmin.schedules) == 1
    assert sum(method == "POST" for method, _, _ in garmin.calls) == 2


@pytest.mark.parametrize("phase", ["create", "schedule"])
def test_lost_write_response_requires_reconciliation(planned, phase):
    garmin = Garmin()
    garmin.fail = phase
    result = service.export(planned, client=garmin)
    assert result["state"] == "uncertain"
    count = len(garmin.calls)
    with pytest.raises(DocumentError, match="indéterminé"):
        service.export(planned, client=garmin)
    assert len(garmin.calls) == count
    assert service.reconcile(planned, client=garmin)["state"] == "ready"
    assert service.export(planned, client=garmin)["state"] == "scheduled"
    assert len(garmin.workouts) == len(garmin.schedules) == 1


def test_remote_conflict_never_overwrites(planned):
    garmin = Garmin()
    service.export(planned, client=garmin)
    garmin.workouts[1]["workoutName"] = "Changed in Connect"
    assert service.export(planned, client=garmin)["state"] == "conflict"
    assert garmin.workouts[1]["workoutName"] == "Changed in Connect"
    assert not any(method == "PUT" for method, _, _ in garmin.calls)


def test_changed_date_updates_same_workout_and_replaces_only_its_schedule(planned):
    garmin = Garmin()
    service.export(planned, client=garmin)
    prescription = Prescription(
        steps=[Step(kind="effort", duration_kind="seconds", value=2400)]
    )
    service.update_session(planned, 1, date(2027, 1, 13), "40 minutes", prescription)
    assert service.statuses()[0]["state"] == "dirty"
    result = service.export(planned, client=garmin)
    assert result["state"] == "scheduled", result
    assert len(garmin.workouts) == len(garmin.schedules) == 1
    assert next(iter(garmin.schedules.values()))["date"] == "2027-01-13"


def test_deleted_session_keeps_explicit_removal_task(planned):
    garmin = Garmin()
    service.export(planned, client=garmin)
    GarminRepository().delete_planned_session(planned)
    assert service.statuses()[0]["state"] == "pending_removal"
    assert garmin.workouts
    assert service.remove(planned, client=garmin)["state"] == "removed"
    assert not garmin.workouts and not garmin.schedules


def test_concurrent_export_cannot_create_second_workout(planned):
    garmin = Garmin()

    def attempt_duplicate():
        with pytest.raises(DocumentError, match="déjà en cours"):
            service.export(planned, client=garmin)

    garmin.on_create = attempt_duplicate
    assert service.export(planned, client=garmin)["state"] == "scheduled"
    assert len(garmin.workouts) == 1


def test_model_is_not_used_and_transfer_does_not_claim_delivery(planned):
    garmin = Garmin()
    result = service.export(planned, device_id=10, client=garmin)
    assert result["state"] == "transfer_requested"
    assert len(garmin.calls) <= service.MAX_EXPORT_REQUESTS


def test_invalid_or_unrepresentable_prescription_has_no_remote_write(planned):
    garmin = Garmin()
    with db_connection() as con:
        con.execute(
            "UPDATE app.planned_sessions SET sport='other' WHERE id=?", [planned]
        )
    with pytest.raises(ValueError, match="exportable"):
        service.export(planned, client=garmin)
    assert garmin.calls == []


def test_api_preserves_structured_planned_fields(planned):
    session = GarminRepository().get_planned_session(planned)
    assert session.prescription["steps"][0]["value"] == 1800
    assert session.revision == 1
    assert json.dumps(session.prescription)


def test_repeated_transfer_never_pushes_again_without_a_change(planned):
    garmin = Garmin()
    for _ in range(3):
        assert (
            service.export(planned, device_id=10, client=garmin)["state"]
            == "transfer_requested"
        )
    assert (
        sum(
            path == "/device-service/devicemessage/messages"
            for _, path, _ in garmin.calls
        )
        == 1
    )


def test_timeout_after_deletion_reconciles_without_a_second_delete(planned):
    garmin = Garmin()
    service.export(planned, client=garmin)
    GarminRepository().delete_planned_session(planned)
    garmin.fail = "delete"
    assert service.remove(planned, client=garmin)["state"] == "uncertain"
    with pytest.raises(DocumentError, match="indéterminé"):
        service.remove(planned, client=garmin)
    assert service.reconcile(planned, client=garmin)["state"] == "removed"
    assert not garmin.workouts and not garmin.schedules


def test_swim_main_and_butterfly_preserve_connect_enumerations():
    prescription = Prescription(
        pool_length_m=25,
        steps=[
            Step(kind="effort", duration_kind="meters", value=100, stroke="butterfly")
        ],
    )
    payload = convert(1, "Papillon", "swimming", prescription)
    step = payload["workoutSegments"][0]["workoutSteps"][0]
    assert step["stepType"] == {"stepTypeId": 8, "stepTypeKey": "main"}
    assert step["strokeType"] == {"strokeTypeId": 5, "strokeTypeKey": "fly"}
    prescription.steps[0].stroke = "mixed"
    with pytest.raises(ValueError, match="ordre"):
        convert(1, "Mixed", "swimming", prescription)


def test_reconciliation_fences_the_previous_worker(planned):
    old = service._claim(planned)
    with db_connection() as con:
        con.execute(
            "UPDATE app.garmin_exports SET updated_at=current_timestamp-INTERVAL '5 minutes' WHERE session_id=?",
            [planned],
        )
    new = service._claim(planned, reconcile=True)
    assert old["operation_id"] != new["operation_id"]
    with pytest.raises(DocumentError, match="récente"):
        service._update(planned, old["operation_id"], state="scheduled")
    exchange = service.Exchange(Garmin())
    exchange.reservation = (planned, old["operation_id"])
    with pytest.raises(DocumentError, match="réservation"):
        exchange.call("POST", service.WORKOUT, {})
    assert exchange.client.calls == []
