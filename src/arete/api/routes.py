from datetime import date
from typing import Literal

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from arete.dataio import repository as repo

router = APIRouter()

# Pagination limits
MAX_LIMIT = 100
DEFAULT_LIMIT = 20


def _calculate_bmi(height: float, weight: float) -> float | None:
    """Calculate BMI from height (cm) and weight (kg)."""
    if height and weight and height > 0:
        return round(weight / ((height / 100) ** 2), 2)
    return None


def _validate_pagination(skip: int, limit: int) -> tuple[int, int]:
    """Validate and clamp pagination parameters."""
    skip = max(0, skip)
    limit = max(1, min(limit, MAX_LIMIT))
    return skip, limit


# ---------- Schemas ----------
class SessionCreate(BaseModel):
    date: date
    objective: str
    duration: int = Field(ge=0)
    fatigue: int = Field(ge=0)
    rpe_avg7d: float | None = None


class SessionOut(BaseModel):
    id: int
    date: date
    objective: str
    duration: int
    fatigue: int
    rpe_avg7d: float | None = None


class SessionList(BaseModel):
    total: int
    items: list[SessionOut]


class UserCreate(BaseModel):
    sex: Literal["M", "F"]
    age: int = Field(gt=0)
    height: float = Field(gt=0)  # cm
    weight: float = Field(gt=0)  # kg
    desired_training_load: float | None = None


class UserOut(BaseModel):
    id: int
    sex: str
    age: int
    height: float
    weight: float
    desired_training_load: float | None = None
    bmi: float | None = None


class ObjectiveCreate(BaseModel):
    sport: str
    name: str
    priority: int = Field(ge=0, le=2)


class ObjectiveOut(BaseModel):
    id: int
    sport: str
    name: str
    priority: int


class ObjectiveList(BaseModel):
    total: int
    items: list[ObjectiveOut]


class RecordCreate(BaseModel):
    sport: str
    event: str
    performance: float = Field(gt=0)
    unit: str


class RecordOut(BaseModel):
    id: int
    sport: str
    event: str
    performance: float
    unit: str


class RecordList(BaseModel):
    total: int
    items: list[RecordOut]


# ---------- Endpoints ----------
@router.post("/plan/day", response_model=SessionOut)
def plan_day(payload: SessionCreate):
    row = repo.create_session(
        session_date=payload.date,
        objective=payload.objective,
        duration=payload.duration,
        fatigue=payload.fatigue,
        rpe_avg7d=payload.rpe_avg7d,
    )
    return SessionOut(**row)


@router.get("/sessions", response_model=SessionList)
def list_sessions(skip: int = 0, limit: int = DEFAULT_LIMIT):
    skip, limit = _validate_pagination(skip, limit)
    total, rows = repo.list_sessions(skip=skip, limit=limit)
    return SessionList(total=total, items=[SessionOut(**r) for r in rows])


@router.get("/sessions/{session_id}", response_model=SessionOut)
def get_session(session_id: int):
    row = repo.get_session(session_id)
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionOut(**row)


@router.put("/sessions/{session_id}", response_model=SessionOut)
def update_session(session_id: int, payload: SessionCreate):
    row = repo.update_session(
        session_id,
        session_date=payload.date,
        objective=payload.objective,
        duration=payload.duration,
        fatigue=payload.fatigue,
        rpe_avg7d=payload.rpe_avg7d,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    return SessionOut(**row)


@router.delete("/sessions/{session_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_session(session_id: int):
    ok = repo.delete_session(session_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Session not found")


@router.post("/user", response_model=UserOut)
def create_user(payload: UserCreate):
    if repo.get_user():
        raise HTTPException(status_code=400, detail="User already exists")
    row = repo.create_user(
        sex=payload.sex,
        age=payload.age,
        height=payload.height,
        weight=payload.weight,
        desired_training_load=payload.desired_training_load,
    )
    return UserOut(**row, bmi=_calculate_bmi(row["height"], row["weight"]))


@router.get("/user", response_model=UserOut)
def get_user():
    row = repo.get_user()
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return UserOut(**row, bmi=_calculate_bmi(row["height"], row["weight"]))


@router.put("/user", response_model=UserOut)
def update_user(payload: UserCreate):
    row = repo.update_user(
        sex=payload.sex,
        age=payload.age,
        height=payload.height,
        weight=payload.weight,
        desired_training_load=payload.desired_training_load,
    )
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    return UserOut(**row, bmi=_calculate_bmi(row["height"], row["weight"]))


@router.post("/objectives", response_model=ObjectiveOut)
def create_objective(payload: ObjectiveCreate):
    row = repo.create_objective(
        sport=payload.sport, name=payload.name, priority=payload.priority
    )
    return ObjectiveOut(**row)


@router.get("/objectives", response_model=ObjectiveList)
def list_objectives(skip: int = 0, limit: int = DEFAULT_LIMIT):
    skip, limit = _validate_pagination(skip, limit)
    total, rows = repo.list_objectives(skip=skip, limit=limit)
    return ObjectiveList(total=total, items=[ObjectiveOut(**r) for r in rows])


@router.put("/objectives/{obj_id}", response_model=ObjectiveOut)
def update_objective(obj_id: int, payload: ObjectiveCreate):
    row = repo.update_objective(
        obj_id, sport=payload.sport, name=payload.name, priority=payload.priority
    )
    if not row:
        raise HTTPException(status_code=404, detail="Objective not found")
    return ObjectiveOut(**row)


@router.delete("/objectives/{obj_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_objective(obj_id: int):
    ok = repo.delete_objective(obj_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Objective not found")


@router.post("/records", response_model=RecordOut)
def create_record(payload: RecordCreate):
    row = repo.create_record(
        sport=payload.sport,
        event=payload.event,
        performance=payload.performance,
        unit=payload.unit,
    )
    return RecordOut(**row)


@router.get("/records", response_model=RecordList)
def list_records(skip: int = 0, limit: int = DEFAULT_LIMIT):
    skip, limit = _validate_pagination(skip, limit)
    total, rows = repo.list_records(skip=skip, limit=limit)
    return RecordList(total=total, items=[RecordOut(**r) for r in rows])


@router.put("/records/{rec_id}", response_model=RecordOut)
def update_record(rec_id: int, payload: RecordCreate):
    row = repo.update_record(
        rec_id,
        sport=payload.sport,
        event=payload.event,
        performance=payload.performance,
        unit=payload.unit,
    )
    if not row:
        raise HTTPException(status_code=404, detail="Record not found")
    return RecordOut(**row)


@router.delete("/records/{rec_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_record(rec_id: int):
    ok = repo.delete_record(rec_id)
    if not ok:
        raise HTTPException(status_code=404, detail="Record not found")


# ---------- User Settings ----------
class UserSettingsUpdate(BaseModel):
    display_name: str = "HUNTER"
    email: str | None = None
    timezone: str = "Europe/Paris"
    weekly_training_goal: int = Field(ge=1, le=14, default=6)
    rest_day_preference: list[str] = ["monday"]
    fatigue_threshold: int = Field(ge=50, le=100, default=85)
    fitness_goal: Literal["maintenance", "build", "peak", "recovery"] = "build"
    notifications_enabled: bool = True
    theme: Literal["dark", "darker", "abyss"] = "dark"
    exercise_abbreviations: dict[str, str] = {}


class UserSettingsOut(BaseModel):
    user_id: int
    display_name: str
    email: str | None
    timezone: str
    weekly_training_goal: int
    rest_day_preference: list[str]
    fatigue_threshold: int
    fitness_goal: str
    notifications_enabled: bool
    theme: str
    exercise_abbreviations: dict[str, str]


@router.get("/settings", response_model=UserSettingsOut)
def get_settings():
    """Get current user settings."""
    settings = repo.get_user_settings(user_id=1)
    if not settings:
        # Return defaults if no settings exist
        return UserSettingsOut(
            user_id=1,
            display_name="HUNTER",
            email=None,
            timezone="Europe/Paris",
            weekly_training_goal=6,
            rest_day_preference=["monday"],
            fatigue_threshold=85,
            fitness_goal="build",
            notifications_enabled=True,
            theme="dark",
            exercise_abbreviations={},
        )
    return UserSettingsOut(**settings)


@router.put("/settings", response_model=UserSettingsOut)
def update_settings(payload: UserSettingsUpdate):
    """Update user settings."""
    settings = repo.upsert_user_settings(
        user_id=1,
        display_name=payload.display_name,
        email=payload.email,
        timezone=payload.timezone,
        weekly_training_goal=payload.weekly_training_goal,
        rest_day_preference=payload.rest_day_preference,
        fatigue_threshold=payload.fatigue_threshold,
        fitness_goal=payload.fitness_goal,
        notifications_enabled=payload.notifications_enabled,
        theme=payload.theme,
        exercise_abbreviations=payload.exercise_abbreviations,
    )
    return UserSettingsOut(**settings)
