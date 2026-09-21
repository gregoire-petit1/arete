"""Strength training API endpoints.

Endpoints for:
- Managing exercise library
- Recording strength sessions with sets
- Viewing exercise history and PRs
"""

from __future__ import annotations

import logging
from datetime import date as date_type
from datetime import timedelta

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field

from arete.data.cardio_muscle_impact import CARDIO_MUSCLE_IMPACT
from arete.features import muscles as muscle_map
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

    date: date_type
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
    date: date_type
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
    date: date_type
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
    garmin_activity_id: int | None = None


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


@router.delete("/exercises/duplicates")
def remove_duplicate_exercises():
    """Remove duplicate exercises, keeping the one with lowest ID."""
    removed_count = _repo.remove_duplicate_exercises()
    return {"message": f"Removed {removed_count} duplicate exercises"}


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
    _complete_planned_strength(session.date)
    session.id = session_id

    return _session_to_summary_response(session)


@router.get("/sessions", response_model=list[StrengthSessionResponse])
def list_sessions(
    start_date: date_type | None = None,
    end_date: date_type | None = None,
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
        if s.id is None:
            continue
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


class LinkGarminRequest(BaseModel):
    """Request to link a strength session to a Garmin activity."""

    garmin_activity_id: int | None = Field(
        None, description="actual_sessions.id to link (null to unlink)"
    )


@router.post("/sessions/{session_id}/link-garmin")
def link_session_to_garmin(session_id: int, data: LinkGarminRequest):
    """Link a strength session to a Garmin activity."""
    success = _repo.link_to_actual_session(session_id, data.garmin_activity_id)
    if not success:
        raise HTTPException(status_code=404, detail="Session not found")
    return {
        "message": "Session linked" if data.garmin_activity_id else "Session unlinked"
    }


@router.get("/sessions/{session_id}/garmin-candidates")
def get_garmin_candidates(session_id: int):
    """Get Garmin activities that could be linked to this strength session.

    Returns strength activities from the same date or nearby dates.
    """
    session = _repo.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Get actual sessions from Garmin for the same date range
    from datetime import timedelta

    from arete.garmin.repository import GarminRepository

    start = session.date - timedelta(days=1)
    end = session.date + timedelta(days=1)

    actual_sessions = GarminRepository().list_actual_sessions(
        start_date=start, end_date=end, limit=200
    )

    # Filter to strength activities
    candidates = [
        {
            "id": s.id,
            "date": s.date.isoformat() if hasattr(s.date, "isoformat") else str(s.date),
            "sport": s.sport,
            "activity_type": s.session_type,
            "duration_seconds": s.duration_sec,
            "source": s.source,
        }
        for s in actual_sessions
        if s.sport == "strength"
    ]

    return {"candidates": candidates, "session_date": session.date.isoformat()}


# ─────────────────────────────────────────────────────────────────────────
# Statistics Endpoints
# ─────────────────────────────────────────────────────────────────────────


def _cardio_muscle_activity(
    start_date: date_type,
    end_date: date_type,
) -> tuple[dict[str, float], dict[str, date_type]]:
    """Pseudo-volume credited to muscles by cardio sessions, and when they ran."""
    from arete.garmin.repository import GarminRepository

    sessions = GarminRepository().list_actual_sessions(
        start_date=start_date, end_date=end_date, limit=1000
    )

    volume: dict[str, float] = {}
    last: dict[str, date_type] = {}

    for session in sessions:
        sport = session.sport.lower().replace(" ", "_") if session.sport else ""
        impact = CARDIO_MUSCLE_IMPACT.get(sport)
        if not impact:
            continue
        minutes = session.duration_sec / 60 if session.duration_sec else 0
        day = session.date
        for group in ("primary", "secondary"):
            for muscle, per_minute in impact.get(group, {}).items():
                volume[muscle] = volume.get(muscle, 0.0) + per_minute * minutes
                seen = last.get(muscle)
                if seen is None or day > seen:
                    last[muscle] = day

    return volume, last


@router.get("/stats/muscles")
def get_muscle_stats(
    days: int = Query(7, ge=1, le=365),
    include_cardio: bool = True,
):
    """Per-muscle volume, sets and freshness over the last ``days`` days.

    Every stored muscle id — precise or coarse — is spread over the twenty
    regions the silhouette paints, and the heat level is relative to the busiest
    region of the window.
    """
    end = date_type.today()
    start = end - timedelta(days=days - 1)
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)

    strength_volume, sets, strength_last = _repo.get_muscle_activity(start, end)
    prev_strength, _, _ = _repo.get_muscle_activity(prev_start, prev_end)

    volume = dict(strength_volume)
    last = dict(strength_last)
    previous = dict(prev_strength)

    if include_cardio:
        cardio_volume, cardio_last = _cardio_muscle_activity(start, end)
        for muscle, value in cardio_volume.items():
            volume[muscle] = volume.get(muscle, 0.0) + value
        for muscle, day in cardio_last.items():
            seen = last.get(muscle)
            if seen is None or day > seen:
                last[muscle] = day
        prev_cardio, _ = _cardio_muscle_activity(prev_start, prev_end)
        for muscle, value in prev_cardio.items():
            previous[muscle] = previous.get(muscle, 0.0) + value

    stats = muscle_map.build_stats(volume, sets, last, previous)
    return {
        "days": days,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "muscles": [s.as_dict() for s in stats],
    }


# ─────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────


def _exercise_to_response(exercise: Exercise) -> ExerciseResponse:
    """Convert Exercise to response model."""
    return ExerciseResponse(
        id=exercise.id or 0,
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
        id=session.id or 0,
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
                id=s.id or 0,
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
                id=ex.id or 0,
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
        id=session.id or 0,
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
        garmin_activity_id=session.actual_session_id,
    )


# ─────────────────────────────────────────────────────────────────────────
# Workout Text Parsing (LLM)
# ─────────────────────────────────────────────────────────────────────────


class WorkoutParseRequest(BaseModel):
    """Request to parse workout text."""

    text: str = Field(..., min_length=5, description="Free-form workout text to parse")
    date: date_type | None = Field(
        default=None, description="Workout date (defaults to today)"
    )
    save: bool = Field(
        default=False, description="Whether to save the parsed session to DB"
    )


class ParsedSetResponse(BaseModel):
    """Parsed set response."""

    set_number: int
    reps: int | None = None  # None for "to failure" sets
    weight_kg: float | None = None
    rpe: float | None = None
    is_warmup: bool = False
    is_failure: bool = False
    rest_sec: int | None = None  # Rest time after set in seconds


class ExerciseSuggestion(BaseModel):
    """Catalog candidate for an exercise name the parser could not settle."""

    exercise_id: str
    name: str
    score: int


class ParsedExerciseResponse(BaseModel):
    """Parsed exercise response."""

    name: str
    exercise_id: str | None
    exercise_matched: bool
    sets: list[ParsedSetResponse]
    notes: str | None
    target_reps: str | None = None  # Rep range like "8-10" or "5"
    match_score: int = 0
    suggestions: list[ExerciseSuggestion] = []


class WorkoutParseResponse(BaseModel):
    """Response from workout parsing."""

    success: bool
    date: date_type
    name: str | None
    exercises: list[ParsedExerciseResponse]
    duration_min: int | None
    overall_rpe: float | None
    notes: str | None
    session_id: int | None = None  # Set if saved
    message: str | None = None
    unparsed_lines: list[str] = []  # Lines the grammar rejected (to fix by hand)


def _complete_planned_strength(day: date_type) -> None:
    """A logged strength session fulfils the planned strength session of that day."""
    from arete.garmin.repository import GarminRepository
    from arete.garmin.sync import complete_planned

    try:
        complete_planned(GarminRepository(), day, "strength")
    except Exception as e:  # noqa: BLE001 - never block the save
        logger.warning("Could not update planned session for %s: %s", day, e)


# ─────────────────────────────────────────────────────────────────────────
# Voice dictation
# ─────────────────────────────────────────────────────────────────────────

CHUNK_SIZE = 8192


class VoiceTranscriptionResponse(BaseModel):
    """What the browser needs to fill the session box and let the athlete check."""

    transcript: str = Field(description="French text, exactly as dictated")
    notation: str = Field(description="Compact notation rebuilt from the structure")
    unparsed: list[str] = Field(
        default_factory=list, description="Sentences left verbatim, nothing invented"
    )
    exercises: int = Field(description="How many exercises were read")
    cost_usd: float | None = Field(default=None, description="What the call cost")


async def _read_upload(file: UploadFile, max_bytes: int) -> bytes:
    """Read an upload in chunks, refusing anything oversized."""
    content = b""
    while chunk := await file.read(CHUNK_SIZE):
        content += chunk
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=413,
                detail=f"Enregistrement trop volumineux (max {max_bytes // 1024 // 1024} Mo)",
            )
    return content


_TRANSCRIPTION_STATUS: dict[str, int] = {
    "unconfigured": 503,
    "rejected_key": 503,
    "no_credit": 402,
    "rate_limited": 429,
    "unsupported_format": 400,
    "timeout": 504,
    "upstream": 502,
    "empty": 422,
}


@router.post("/sessions/transcribe", response_model=VoiceTranscriptionResponse)
async def transcribe_workout_audio(
    file: UploadFile = File(..., description="Audio recorded in the browser"),
):
    """Dictated session -> French transcript and the notation read from it.

    Nothing is saved: the athlete proof-reads the notation in the session box
    and sends it through ``/sessions/parse`` as usual. What the grammar cannot
    read comes back verbatim rather than guessed.
    """
    from arete.config import config
    from arete.llm.notation import to_notation
    from arete.llm.speech_grammar import parse_dictation, unparsed_dictation
    from arete.llm.transcription import TranscriptionError, transcribe

    audio = await _read_upload(file, config.stt_max_audio_mb * 1024 * 1024)
    if not audio:
        raise HTTPException(status_code=400, detail="Enregistrement vide")

    try:
        result = transcribe(audio, filename=file.filename or "dictation.webm")
    except TranscriptionError as exc:
        raise HTTPException(
            status_code=_TRANSCRIPTION_STATUS.get(exc.reason, 502), detail=str(exc)
        ) from exc

    exercises = parse_dictation(result.text) or []
    missed = unparsed_dictation(result.text)
    if missed:
        _record_dictation_misses(missed)
    return VoiceTranscriptionResponse(
        transcript=result.text,
        notation=to_notation(exercises),
        unparsed=missed,
        exercises=len(exercises),
        cost_usd=result.cost_usd,
    )


def _record_dictation_misses(missed: list[str]) -> None:
    """Log what the grammar could not read, so it can learn the turn of phrase."""
    import json
    from datetime import datetime

    from arete.dataio.db import get_db_path

    path = get_db_path().parent / "dictation_misses.jsonl"
    try:
        with path.open("a", encoding="utf-8") as handle:
            for sentence in missed:
                handle.write(
                    json.dumps(
                        {"at": datetime.now().isoformat(), "sentence": sentence},
                        ensure_ascii=False,
                    )
                    + "\n"
                )
    except OSError as exc:  # never fail a dictation over a log line
        logger.warning("Could not record dictation misses: %s", exc)


@router.post("/sessions/parse", response_model=WorkoutParseResponse)
def parse_workout_text_endpoint(request: WorkoutParseRequest):
    """Parse free-form workout text into structured session data.

    Supports formats like:
    - "2x8 @80 bench press" (sets before name)
    - "3@100, 1@105 squat" (descending sets)
    - "(pull ups, dips)" (supersets)

    Deterministic grammar + semantic catalog matching (no LLM). Lines the
    grammar cannot read come back in ``unparsed_lines``; exercise names that are
    not confidently matched come back with ``suggestions``.
    User abbreviations are loaded from settings automatically.
    """
    from arete.dataio.settings import get_user_settings
    from arete.llm.workout_parser import parse_workout_text

    # Load user abbreviations from settings
    user_settings = get_user_settings(user_id=1)
    abbreviations = (
        user_settings.get("exercise_abbreviations", {}) if user_settings else {}
    )

    try:
        parsed = parse_workout_text(
            text=request.text,
            workout_date=request.date,
            abbreviations=abbreviations,
        )

        # Convert to response
        exercises_response = []
        for ex in parsed.exercises:
            sets_response = [
                ParsedSetResponse(
                    set_number=s.set_number,
                    reps=s.reps,
                    weight_kg=s.weight_kg,
                    rpe=s.rpe,
                    is_warmup=s.is_warmup,
                    is_failure=getattr(s, "is_failure", False),
                    rest_sec=getattr(s, "rest_sec", None),
                )
                for s in ex.sets
            ]
            exercises_response.append(
                ParsedExerciseResponse(
                    name=ex.name,
                    exercise_id=ex.exercise_id,
                    exercise_matched=ex.exercise_id is not None,
                    sets=sets_response,
                    notes=ex.notes,
                    target_reps=ex.target_reps,
                    match_score=ex.match_score,
                    suggestions=[
                        ExerciseSuggestion(
                            exercise_id=sg.exercise_id, name=sg.name, score=sg.score
                        )
                        for sg in ex.suggestions
                    ],
                )
            )

        session_id = None
        message = None

        # Optionally save to database
        if request.save and parsed.exercises:
            try:
                # Build session create data
                session = StrengthSession(
                    date=parsed.date,
                    name=parsed.name,
                    duration_min=parsed.duration_min,
                    overall_rpe=parsed.overall_rpe,
                    notes=parsed.notes,
                )

                for i, ex in enumerate(parsed.exercises):
                    if ex.exercise_id:
                        # Get or create exercise from catalog
                        exercise = _repo.get_or_create_exercise_from_catalog(
                            ex.exercise_id
                        )
                        if exercise:
                            session_exercise = SessionExercise(
                                exercise_id=exercise.id,
                                exercise=exercise,
                                order=i + 1,
                            )
                            for s in ex.sets:
                                session_exercise.sets.append(
                                    ExerciseSet(
                                        set_number=s.set_number,
                                        reps=s.reps if s.reps is not None else 0,
                                        weight_kg=s.weight_kg,
                                        rpe=s.rpe,
                                        is_warmup=s.is_warmup,
                                    )
                                )
                            session.exercises.append(session_exercise)

                if session.exercises:
                    session_id = _repo.create_session(session)
                    _complete_planned_strength(session.date)
                    message = f"Session saved with {len(session.exercises)} exercises"
                else:
                    message = "No exercises matched - session not saved"

            except Exception as e:
                logger.error(f"Failed to save parsed session: {e}")
                message = f"Parsing succeeded but save failed: {str(e)}"

        return WorkoutParseResponse(
            success=True,
            date=parsed.date,
            name=parsed.name,
            exercises=exercises_response,
            duration_min=parsed.duration_min,
            overall_rpe=parsed.overall_rpe,
            notes=parsed.notes,
            session_id=session_id,
            message=message,
            unparsed_lines=parsed.unparsed_lines,
        )

    except ValueError as e:
        # Nothing recognised in the text: a client problem, say so plainly
        raise HTTPException(status_code=422, detail=str(e)) from e
