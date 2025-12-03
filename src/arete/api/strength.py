"""Strength training API endpoints.

Endpoints for:
- Managing exercise library
- Recording strength sessions with sets
- Viewing exercise history and PRs
"""

from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from arete.strength.models import (
    Exercise,
    ExerciseCategory,
    ExerciseSet,
    MuscleGroup,
    SessionExercise,
    StrengthSession,
)
from arete.strength.repository import StrengthRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/strength", tags=["strength"])

# Shared repository instance
_repo = StrengthRepository()


# ─────────────────────────────────────────────────────────────────────────
# Schemas
# ─────────────────────────────────────────────────────────────────────────


class ExerciseCreate(BaseModel):
    """Create a new exercise in the library."""

    name: str = Field(..., min_length=1, max_length=100)
    category: ExerciseCategory = ExerciseCategory.OTHER
    primary_muscle: MuscleGroup = MuscleGroup.FULL_BODY
    secondary_muscles: list[MuscleGroup] = Field(default_factory=list)
    equipment: str | None = Field(None, max_length=50)
    is_unilateral: bool = False
    notes: str | None = None


class ExerciseResponse(BaseModel):
    """Exercise response."""

    id: int
    name: str
    category: str
    primary_muscle: str
    secondary_muscles: list[str]
    equipment: str | None
    is_unilateral: bool
    notes: str | None


class SetCreate(BaseModel):
    """Create a set within an exercise."""

    set_number: int = Field(ge=1)
    reps: int = Field(ge=0)
    weight_kg: float | None = Field(None, ge=0)
    rpe: float | None = Field(None, ge=1, le=10)
    rir: int | None = Field(None, ge=0, le=10)
    rest_sec: int | None = Field(None, ge=0)
    tempo: str | None = Field(None, pattern=r"^\d-\d-\d-\d$")
    is_warmup: bool = False
    is_failure: bool = False
    notes: str | None = None


class SessionExerciseCreate(BaseModel):
    """Create an exercise within a session."""

    exercise_id: int
    order: int = Field(ge=1)
    target_sets: int | None = Field(None, ge=1)
    target_reps: str | None = None  # e.g., "8-12" or "5"
    target_rpe: float | None = Field(None, ge=1, le=10)
    sets: list[SetCreate] = Field(default_factory=list)
    notes: str | None = None


class StrengthSessionCreate(BaseModel):
    """Create a strength training session."""

    date: date
    name: str | None = Field(None, max_length=100)
    program: str | None = Field(None, max_length=50)
    duration_min: int | None = Field(None, ge=1)
    overall_rpe: float | None = Field(None, ge=1, le=10)
    fatigue_level: int | None = Field(None, ge=1, le=5)
    sleep_quality: int | None = Field(None, ge=1, le=5)
    notes: str | None = None
    exercises: list[SessionExerciseCreate] = Field(default_factory=list)


class StrengthSessionResponse(BaseModel):
    """Strength session response (summary)."""

    id: int
    date: date
    name: str | None
    program: str | None
    duration_min: int | None
    exercises_count: int
    total_sets: int
    total_volume: float
    overall_rpe: float | None
    muscles_worked: list[str]


class SetResponse(BaseModel):
    """Set response."""

    id: int
    set_number: int
    reps: int
    weight_kg: float | None
    rpe: float | None
    rir: int | None
    rest_sec: int | None
    tempo: str | None
    is_warmup: bool
    is_failure: bool
    volume: float
    estimated_1rm: float | None
    notes: str | None


class SessionExerciseResponse(BaseModel):
    """Session exercise response with sets."""

    id: int
    order: int
    exercise: ExerciseResponse | None
    target_sets: int | None
    target_reps: str | None
    target_rpe: float | None
    sets: list[SetResponse]
    total_volume: float
    working_sets_count: int
    avg_rpe: float | None
    notes: str | None


class StrengthSessionDetailResponse(BaseModel):
    """Full strength session with all exercises and sets."""

    id: int
    date: date
    name: str | None
    program: str | None
    duration_min: int | None
    overall_rpe: float | None
    fatigue_level: int | None
    sleep_quality: int | None
    notes: str | None
    exercises: list[SessionExerciseResponse]
    total_volume: float
    total_sets: int
    muscles_worked: list[str]


class ExerciseHistoryResponse(BaseModel):
    """Exercise history entry."""

    date: str
    session_exercise_id: int
    total_sets: int
    working_sets: int
    max_weight: float | None
    volume: float
    avg_rpe: float | None


class PersonalRecordsResponse(BaseModel):
    """Personal records for an exercise."""

    max_weight: float | None
    max_weight_reps: int | None
    max_weight_date: str | None
    estimated_1rm: float | None
    max_session_volume: float | None
    max_volume_date: str | None


# ─────────────────────────────────────────────────────────────────────────
# Exercise Library Endpoints
# ─────────────────────────────────────────────────────────────────────────


@router.post("/exercises", response_model=ExerciseResponse)
def create_exercise(data: ExerciseCreate):
    """Create a new exercise in the library."""
    # Check if exercise already exists
    existing = _repo.get_exercise_by_name(data.name)
    if existing:
        raise HTTPException(
            status_code=400, detail=f"Exercise '{data.name}' already exists"
        )

    exercise = Exercise(
        name=data.name,
        category=data.category,
        primary_muscle=data.primary_muscle,
        secondary_muscles=data.secondary_muscles,
        equipment=data.equipment,
        is_unilateral=data.is_unilateral,
        notes=data.notes,
    )

    exercise_id = _repo.create_exercise(exercise)
    exercise.id = exercise_id

    return _exercise_to_response(exercise)


@router.get("/exercises", response_model=list[ExerciseResponse])
def list_exercises(
    category: ExerciseCategory | None = None,
    muscle: MuscleGroup | None = None,
    search: str | None = Query(None, min_length=2),
):
    """List exercises with optional filters."""
    exercises = _repo.list_exercises(category=category, muscle=muscle, search=search)
    return [_exercise_to_response(e) for e in exercises]


@router.get("/exercises/{exercise_id}", response_model=ExerciseResponse)
def get_exercise(exercise_id: int):
    """Get an exercise by ID."""
    exercise = _repo.get_exercise(exercise_id)
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")
    return _exercise_to_response(exercise)


@router.get(
    "/exercises/{exercise_id}/history", response_model=list[ExerciseHistoryResponse]
)
def get_exercise_history(exercise_id: int, limit: int = Query(20, ge=1, le=100)):
    """Get performance history for an exercise."""
    exercise = _repo.get_exercise(exercise_id)
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    return _repo.get_exercise_history(exercise_id, limit=limit)


@router.get("/exercises/{exercise_id}/prs", response_model=PersonalRecordsResponse)
def get_exercise_prs(exercise_id: int):
    """Get personal records for an exercise."""
    exercise = _repo.get_exercise(exercise_id)
    if not exercise:
        raise HTTPException(status_code=404, detail="Exercise not found")

    return _repo.get_personal_records(exercise_id)


# ─────────────────────────────────────────────────────────────────────────
# Strength Session Endpoints
# ─────────────────────────────────────────────────────────────────────────


@router.post("/sessions", response_model=StrengthSessionResponse)
def create_session(data: StrengthSessionCreate):
    """Create a new strength training session."""
    # Build session with exercises and sets
    session = StrengthSession(
        date=data.date,
        name=data.name,
        program=data.program,
        duration_min=data.duration_min,
        overall_rpe=data.overall_rpe,
        fatigue_level=data.fatigue_level,
        sleep_quality=data.sleep_quality,
        notes=data.notes,
    )

    for ex_data in data.exercises:
        # Verify exercise exists
        exercise = _repo.get_exercise(ex_data.exercise_id)
        if not exercise:
            raise HTTPException(
                status_code=400, detail=f"Exercise ID {ex_data.exercise_id} not found"
            )

        session_exercise = SessionExercise(
            exercise_id=ex_data.exercise_id,
            exercise=exercise,
            order=ex_data.order,
            target_sets=ex_data.target_sets,
            target_reps=ex_data.target_reps,
            target_rpe=ex_data.target_rpe,
            notes=ex_data.notes,
        )

        for set_data in ex_data.sets:
            exercise_set = ExerciseSet(
                set_number=set_data.set_number,
                reps=set_data.reps,
                weight_kg=set_data.weight_kg,
                rpe=set_data.rpe,
                rir=set_data.rir,
                rest_sec=set_data.rest_sec,
                tempo=set_data.tempo,
                is_warmup=set_data.is_warmup,
                is_failure=set_data.is_failure,
                notes=set_data.notes,
            )
            session_exercise.sets.append(exercise_set)

        session.exercises.append(session_exercise)

    session_id = _repo.create_session(session)
    session.id = session_id

    return _session_to_summary_response(session)


@router.get("/sessions", response_model=list[StrengthSessionResponse])
def list_sessions(
    start_date: date | None = None,
    end_date: date | None = None,
    program: str | None = None,
    limit: int = Query(50, ge=1, le=200),
):
    """List strength sessions."""
    sessions = _repo.list_sessions(
        start_date=start_date, end_date=end_date, program=program, limit=limit
    )

    # We need to fetch full details for summary stats
    result = []
    for s in sessions:
        full_session = _repo.get_session(s.id)
        if full_session:
            result.append(_session_to_summary_response(full_session))
    return result


@router.get("/sessions/{session_id}", response_model=StrengthSessionDetailResponse)
def get_session(session_id: int):
    """Get a strength session with full details."""
    session = _repo.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return _session_to_detail_response(session)


@router.delete("/sessions/{session_id}")
def delete_session(session_id: int):
    """Delete a strength session."""
    success = _repo.delete_session(session_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"message": "Session deleted"}


# ─────────────────────────────────────────────────────────────────────────
# Statistics Endpoints
# ─────────────────────────────────────────────────────────────────────────


@router.get("/stats/volume-by-muscle")
def get_volume_by_muscle(
    start_date: date | None = None,
    end_date: date | None = None,
):
    """Get total volume grouped by muscle group."""
    return _repo.get_volume_by_muscle(start_date=start_date, end_date=end_date)


# ─────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────


def _exercise_to_response(exercise: Exercise) -> ExerciseResponse:
    """Convert Exercise to response model."""
    return ExerciseResponse(
        id=exercise.id,
        name=exercise.name,
        category=exercise.category.value,
        primary_muscle=exercise.primary_muscle.value,
        secondary_muscles=[m.value for m in exercise.secondary_muscles],
        equipment=exercise.equipment,
        is_unilateral=exercise.is_unilateral,
        notes=exercise.notes,
    )


def _session_to_summary_response(session: StrengthSession) -> StrengthSessionResponse:
    """Convert StrengthSession to summary response."""
    return StrengthSessionResponse(
        id=session.id,
        date=session.date,
        name=session.name,
        program=session.program,
        duration_min=session.duration_min,
        exercises_count=len(session.exercises),
        total_sets=session.total_sets,
        total_volume=round(session.total_volume, 1),
        overall_rpe=session.overall_rpe,
        muscles_worked=[m.value for m in session.muscles_worked],
    )


def _session_to_detail_response(
    session: StrengthSession,
) -> StrengthSessionDetailResponse:
    """Convert StrengthSession to detailed response."""
    exercises_response = []

    for ex in session.exercises:
        sets_response = [
            SetResponse(
                id=s.id,
                set_number=s.set_number,
                reps=s.reps,
                weight_kg=s.weight_kg,
                rpe=s.rpe,
                rir=s.rir,
                rest_sec=s.rest_sec,
                tempo=s.tempo,
                is_warmup=s.is_warmup,
                is_failure=s.is_failure,
                volume=round(s.volume, 1),
                estimated_1rm=round(s.estimated_1rm, 1) if s.estimated_1rm else None,
                notes=s.notes,
            )
            for s in ex.sets
        ]

        exercise_response = None
        if ex.exercise:
            exercise_response = _exercise_to_response(ex.exercise)

        exercises_response.append(
            SessionExerciseResponse(
                id=ex.id,
                order=ex.order,
                exercise=exercise_response,
                target_sets=ex.target_sets,
                target_reps=ex.target_reps,
                target_rpe=ex.target_rpe,
                sets=sets_response,
                total_volume=round(ex.total_volume, 1),
                working_sets_count=ex.working_sets_count,
                avg_rpe=round(ex.avg_rpe, 1) if ex.avg_rpe else None,
                notes=ex.notes,
            )
        )

    return StrengthSessionDetailResponse(
        id=session.id,
        date=session.date,
        name=session.name,
        program=session.program,
        duration_min=session.duration_min,
        overall_rpe=session.overall_rpe,
        fatigue_level=session.fatigue_level,
        sleep_quality=session.sleep_quality,
        notes=session.notes,
        exercises=exercises_response,
        total_volume=round(session.total_volume, 1),
        total_sets=session.total_sets,
        muscles_worked=[m.value for m in session.muscles_worked],
    )
