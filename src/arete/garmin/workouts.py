"""Deterministic prescription conversion. Never silently weaken a workout."""

from __future__ import annotations

from typing import Any

from arete.services.prescriptions import Prescription, Step, Target


def _target(target: Target, hr_ranges: list[tuple[int, int | None]] | None) -> dict:
    kind = target.kind
    low, high = target.low, target.high
    if kind == "hr_zone":
        if not hr_ranges:
            raise ValueError(
                "Configure un seuil ou une FC maximale mesurée avant d’exporter une zone FC."
            )
        low, upper = hr_ranges[int(low) - 1]
        if upper is None or low == 0:
            raise ValueError(
                "Une zone ouverte exige des bornes FC explicites pour Garmin."
            )
        high = upper
        kind = "heart_rate_bpm"
    ids = {
        "pace_sec_km": (6, "pace.zone"),
        "heart_rate_bpm": (4, "heart.rate.zone"),
        "power_w": (2, "power.zone"),
        "cadence_rpm": (3, "cadence"),
    }
    identifier, key = ids[kind]
    if kind == "pace_sec_km":
        low, high = 1000 / high, 1000 / low
    return {
        "targetType": {"workoutTargetTypeId": identifier, "workoutTargetTypeKey": key},
        "targetValueOne": low,
        "targetValueTwo": high,
    }


def convert(
    session_id: int,
    name: str,
    sport: str,
    prescription: Prescription,
    *,
    hr_ranges: list[tuple[int, int | None]] | None = None,
) -> dict[str, Any]:
    from garminconnect import workout as w
    from garminconnect.exercises import resolve

    classes = {
        "running": w.RunningWorkout,
        "cycling": w.CyclingWorkout,
        "swimming": w.SwimmingWorkout,
        "strength": w.StrengthWorkout,
        "walking": w.WalkingWorkout,
        "hiking": w.HikingWorkout,
    }
    if sport not in classes:
        raise ValueError(f"Sport non exportable : {sport}.")
    if sport == "swimming" and not prescription.pool_length_m:
        raise ValueError("Longueur du bassin requise.")
    if sport != "swimming" and prescription.pool_length_m is not None:
        raise ValueError("La longueur du bassin ne s’applique qu’à la natation.")
    sport_type = classes[sport].model_fields["sportType"].default_factory()
    order = 0

    def steps(items: list[Step]) -> list[dict]:
        nonlocal order
        result = []
        for step in items:
            order += 1
            index = order
            if step.kind == "repeat":
                group = w.create_repeat_group(
                    step.repeat, steps(step.steps), index
                ).model_dump(exclude_none=True)
                if step.notes:
                    group["description"] = step.notes
                result.append(group)
                continue
            if (
                step.exercise
                or step.garmin_exercise
                or step.weight_kg is not None
                or step.duration_kind == "reps"
            ) and sport != "strength":
                raise ValueError(
                    "Exercices et charges ne sont exportables qu’en musculation."
                )
            if step.stroke and sport != "swimming":
                raise ValueError("Le type de nage ne s’applique qu’à la natation.")
            if (
                sport == "strength"
                and step.kind in {"rest", "recovery"}
                and (
                    step.exercise
                    or step.garmin_exercise
                    or step.weight_kg is not None
                    or step.duration_kind == "reps"
                )
            ):
                raise ValueError(
                    "Un repos de musculation ne peut pas masquer un exercice ou une charge."
                )
            if sport == "strength" and step.kind not in {"rest", "recovery"}:
                entry = resolve(step.garmin_exercise or step.exercise)
                if not entry or step.duration_kind != "reps":
                    raise ValueError(
                        f"Choisis un exercice Garmin exact et un nombre de répétitions pour « {step.exercise} »."
                    )
                item = w.create_strength_exercise_step(
                    entry["category"],
                    step_order=index,
                    reps=int(step.value or 0),
                    exercise_name=entry["exercise"],
                    weight_kg=step.weight_kg,
                ).model_dump(exclude_none=True)
                if step.kind != "effort":
                    identifier = 1 if step.kind == "warmup" else 2
                    item["stepType"] = {
                        "stepTypeId": identifier,
                        "stepTypeKey": step.kind,
                    }
            else:
                kinds = {
                    "warmup": (1, "warmup"),
                    "effort": (3, "interval"),
                    "recovery": (4, "recovery"),
                    "cooldown": (2, "cooldown"),
                    "rest": (5, "rest"),
                }
                conditions = {
                    "seconds": (2, "time"),
                    "meters": (3, "distance"),
                    "lap": (1, "lap.button"),
                    "reps": (10, "reps"),
                }
                k, label = kinds[step.kind]
                if sport == "swimming" and step.kind in {"effort", "recovery"}:
                    if step.kind == "recovery":
                        raise ValueError(
                            "En natation, précise un repos ou une étape de nage avec son objectif de récupération dans les notes."
                        )
                    k, label = 8, "main"
                c, condition = conditions[step.duration_kind]
                item = {
                    "type": "ExecutableStepDTO",
                    "stepOrder": index,
                    "stepType": {"stepTypeId": k, "stepTypeKey": label},
                    "endCondition": {
                        "conditionTypeId": c,
                        "conditionTypeKey": condition,
                    },
                    "targetType": {
                        "workoutTargetTypeId": 1,
                        "workoutTargetTypeKey": "no.target",
                    },
                }
                if step.value is not None:
                    item["endConditionValue"] = step.value
            for secondary, target in (
                (False, step.target),
                (True, step.secondary_target),
            ):
                if target:
                    if sport in {"strength", "swimming"} or (
                        target.kind == "power_w" and sport != "cycling"
                    ):
                        raise ValueError(
                            f"Cible {target.kind} non prise en charge pour {sport}."
                        )
                    converted = _target(target, hr_ranges)
                    item.update(
                        {
                            (
                                "secondary" + key[0].upper() + key[1:]
                                if secondary
                                else key
                            ): value
                            for key, value in converted.items()
                        }
                    )
            if sport == "swimming":
                if step.duration_kind == "meters" and (step.value or 0) % (
                    prescription.pool_length_m or 1
                ):
                    raise ValueError(
                        "La distance doit être un multiple de la longueur du bassin."
                    )
                if step.stroke:
                    strokes = {
                        "free": (6, "free"),
                        "back": (2, "backstroke"),
                        "breast": (3, "breaststroke"),
                        "butterfly": (5, "fly"),
                    }
                    if step.stroke not in strokes:
                        raise ValueError(
                            "Nage mixte non représentable sans détailler l’ordre et la distance de chaque nage."
                        )
                    identifier, key = strokes[step.stroke]
                    item["strokeType"] = {
                        "strokeTypeId": identifier,
                        "strokeTypeKey": key,
                    }
            if step.notes:
                item["description"] = step.notes
            result.append(item)
        return result

    # Display order is presentation metadata, not part of the workout contract.
    sport_type = {k: v for k, v in sport_type.items() if k != "displayOrder"}
    payload = {
        "workoutName": name,
        "description": f"ARETE_SESSION:{session_id}",
        "sportType": sport_type,
        "estimatedDurationInSecs": 0,
        "workoutSegments": [
            {
                "segmentOrder": 1,
                "sportType": sport_type,
                "workoutSteps": steps(prescription.steps),
            }
        ],
    }
    if sport == "swimming":
        payload["poolLength"] = prescription.pool_length_m
        payload["poolLengthUnit"] = {"unitKey": "meter"}
    return payload


def canonical(value: Any) -> Any:
    """Compare semantic fields; Garmin adds IDs, defaults and display metadata."""
    ignored = {
        "workoutId",
        "ownerId",
        "author",
        "createdDate",
        "updatedDate",
        "estimatedDurationInSecs",
        "displayOrder",
        "displayable",
        "stepId",
        "childStepId",
        "workoutSegmentId",
        "segmentId",
        "isWheelchair",
        "shared",
        "consumer",
        "atpPlanId",
        "workoutProvider",
        "workoutSourceId",
        "accessControlRule",
        "avgTrainingSpeed",
        "estimateType",
        "estimatedDistanceInMeters",
        "estimatedDistanceUnit",
        "updatedDateTime",
        "createdDateTime",
        "isSessionTransitionEnabled",
        "trainingPlanId",
    }
    if isinstance(value, dict):
        return {
            k: canonical(v)
            for k, v in value.items()
            if k not in ignored and v is not None
        }
    if isinstance(value, list):
        return [canonical(v) for v in value]
    return value


def matches(expected: Any, actual: Any) -> bool:
    """Verify every requested field; Garmin may return extra computed fields."""
    if isinstance(expected, dict):
        return isinstance(actual, dict) and all(
            k in actual and matches(v, actual[k])
            for k, v in expected.items()
            if k != "estimatedDurationInSecs"
        )
    if isinstance(expected, list):
        return (
            isinstance(actual, list)
            and len(expected) == len(actual)
            and all(matches(a, b) for a, b in zip(expected, actual, strict=True))
        )
    if isinstance(expected, float | int) and isinstance(actual, float | int):
        return abs(expected - actual) < 0.00001
    return bool(expected == actual)
