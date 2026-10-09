"""Provider-independent workout prescriptions and their validation."""

from __future__ import annotations

from datetime import date as Date
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from arete.garmin.models import SessionType

MAX_STEPS = 100
MAX_REPEAT_DEPTH = 2
MAX_EXPANDED_STEPS = 1000


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class Target(StrictModel):
    kind: Literal["pace_sec_km", "heart_rate_bpm", "power_w", "cadence_rpm", "hr_zone"]
    low: float = Field(gt=0, le=10000)
    high: float = Field(gt=0, le=10000)

    @model_validator(mode="after")
    def ordered(self):
        if self.low > self.high:
            raise ValueError("La borne basse doit précéder la borne haute.")
        if self.kind == "hr_zone" and (
            self.low != self.high or self.low not in range(1, 6)
        ):
            raise ValueError("La zone FC doit être un entier entre 1 et 5.")
        return self


class Step(StrictModel):
    kind: Literal["warmup", "effort", "recovery", "cooldown", "rest", "repeat"]
    duration_kind: Literal["seconds", "meters", "reps", "lap"] = "lap"
    value: float | None = Field(default=None, gt=0, le=1_000_000)
    target: Target | None = None
    secondary_target: Target | None = None
    repeat: int | None = Field(default=None, ge=2, le=100)
    steps: list[Step] = Field(default_factory=list, max_length=MAX_STEPS)
    exercise: str = Field(default="", max_length=120)
    garmin_exercise: str = Field(default="", max_length=120)
    weight_kg: float | None = Field(default=None, ge=0, le=1000)
    stroke: Literal["free", "back", "breast", "butterfly", "mixed"] | None = None
    notes: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def consistent(self):
        if self.kind == "repeat":
            if (
                not self.repeat
                or not self.steps
                or self.value
                or self.target
                or self.secondary_target
                or self.exercise
                or self.weight_kg is not None
                or self.stroke
            ):
                raise ValueError(
                    "Un bloc répété doit seulement définir ses répétitions et ses étapes."
                )
        elif self.steps or self.repeat:
            raise ValueError("Seul un bloc répété peut contenir des étapes.")
        elif (self.duration_kind == "lap") != (self.value is None):
            raise ValueError(
                "Indique une valeur pour la durée, la distance ou les répétitions."
            )
        if (
            self.duration_kind == "reps"
            and self.value is not None
            and not self.value.is_integer()
        ):
            raise ValueError("Le nombre de répétitions doit être entier.")
        return self


class Prescription(StrictModel):
    version: Literal[1] = 1
    steps: list[Step] = Field(min_length=1, max_length=MAX_STEPS)
    pool_length_m: float | None = Field(default=None, gt=0, le=100)

    @model_validator(mode="after")
    def bounded(self):
        count = 0
        expanded = 0

        def visit(steps: list[Step], depth: int, multiplier: int) -> None:
            nonlocal count, expanded
            if depth > MAX_REPEAT_DEPTH:
                raise ValueError("Maximum deux niveaux de répétition.")
            for step in steps:
                count += 1
                if count > MAX_STEPS:
                    raise ValueError("Maximum 100 étapes par séance.")
                if step.kind == "repeat":
                    visit(step.steps, depth + 1, multiplier * (step.repeat or 1))
                else:
                    expanded += multiplier
                    if expanded > MAX_EXPANDED_STEPS:
                        raise ValueError("Maximum 1 000 étapes après répétition.")

        visit(self.steps, 0, 1)
        return self


class Provenance(StrictModel):
    document_id: UUID
    locator: str = Field(min_length=1, max_length=200)
    quote: str = Field(min_length=1, max_length=4000)


class ImportedSession(StrictModel):
    date: Date | None = None
    sport: Literal[
        "running", "cycling", "swimming", "strength", "walking", "hiking", "other"
    ]
    session_type: SessionType = SessionType.OTHER
    description: str = Field(min_length=1, max_length=500)
    prescription: Prescription
    provenance: list[Provenance] = Field(min_length=1, max_length=20)
    strength_text: str = Field(default="", max_length=4000)
    uncertainties: list[str] = Field(default_factory=list, max_length=20)


def strength_prescription(text: str, day: Date | None) -> Prescription:
    from arete.strength.logging_service import parse_for_athlete

    parsed = parse_for_athlete(text, workout_date=day)
    if parsed.unparsed_lines or any(e.exercise_id is None for e in parsed.exercises):
        raise ValueError(
            "La grammaire ne reconnaît pas toute la séance de musculation. Corrige le texte source."
        )
    steps = []
    for exercise in parsed.exercises:
        for series in exercise.sets:
            steps.append(
                Step(
                    kind="warmup" if series.is_warmup else "effort",
                    duration_kind="reps",
                    value=series.reps,
                    exercise=exercise.name,
                    weight_kg=series.weight_kg,
                )
            )
            if len(steps) > MAX_STEPS:
                raise ValueError("Maximum 100 séries par séance.")
    return Prescription(steps=steps)


def strength_sets(
    prescription: Prescription,
) -> list[tuple[str, float | None, float | None]]:
    """Expand bounded groups for comparison; rests and Garmin names add no sets."""
    result: list[tuple[str, float | None, float | None]] = []

    def visit(steps: list[Step]) -> None:
        for step in steps:
            if step.kind == "repeat":
                for _ in range(step.repeat or 1):
                    visit(step.steps)
            elif step.kind not in {"rest", "recovery"}:
                if step.duration_kind != "reps":
                    raise ValueError(
                        "La musculation doit préciser les répétitions de chaque série."
                    )
                result.append((step.exercise.casefold(), step.value, step.weight_kg))
                assert len(result) <= MAX_EXPANDED_STEPS

    visit(prescription.steps)
    return result
