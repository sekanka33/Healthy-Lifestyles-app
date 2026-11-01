import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, model_validator

Activity = Literal["walking", "running", "jogging"]
HealthProvider = Literal["health_connect", "healthkit"]

MAX_POINTS_PER_BATCH = 500


class WorkoutStart(BaseModel):
    client_id: uuid.UUID  # device-generated: retries can't create two workouts
    activity_type: Activity
    started_at: AwareDatetime


class PointIn(BaseModel):
    seq: int = Field(ge=0, le=1_000_000)
    segment: int = Field(default=0, ge=0, le=1000)  # +1 after each resume
    recorded_at: AwareDatetime
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    altitude_m: float | None = Field(default=None, ge=-500, le=9000)
    accuracy_m: float | None = Field(default=None, ge=0, le=10000)
    speed_mps: float | None = Field(default=None, ge=0, le=100)


class PointsIn(BaseModel):
    points: list[PointIn] = Field(min_length=1, max_length=MAX_POINTS_PER_BATCH)


class WorkoutFinish(BaseModel):
    ended_at: AwareDatetime
    active_duration_s: int = Field(ge=0, le=24 * 3600)  # excludes paused time
    steps: int | None = Field(default=None, ge=0, le=200_000)
    notes: str | None = Field(default=None, max_length=1000)


class ManualWorkout(BaseModel):
    client_id: uuid.UUID
    activity_type: Activity
    started_at: AwareDatetime
    active_duration_s: int = Field(ge=60, le=24 * 3600)
    distance_m: float = Field(ge=0, le=300_000)
    steps: int | None = Field(default=None, ge=0, le=200_000)
    notes: str | None = Field(default=None, max_length=1000)


class WorkoutOut(BaseModel):
    id: uuid.UUID
    client_id: uuid.UUID
    activity_type: Activity
    source: str
    status: str
    started_at: datetime
    ended_at: datetime | None
    active_duration_s: int
    distance_m: float
    pace_s_per_km: float | None
    calories_kcal_estimate: float | None  # an estimate (MET × body weight), never a measurement
    steps: int | None
    notes: str | None
    point_count: int


class RoutePoint(BaseModel):
    lat: float
    lon: float
    segment: int


class WorkoutDetail(WorkoutOut):
    route: list[RoutePoint]  # accepted fixes only


class HealthRecord(BaseModel):
    external_id: str = Field(min_length=1, max_length=200)  # the platform's record id (dedup key)
    activity_type: Activity
    started_at: AwareDatetime
    ended_at: AwareDatetime
    distance_m: float | None = Field(default=None, ge=0, le=300_000)
    steps: int | None = Field(default=None, ge=0, le=200_000)

    @model_validator(mode="after")
    def order(self):
        if self.ended_at <= self.started_at:
            raise ValueError("ended_at must be after started_at")
        return self


class HealthImportIn(BaseModel):
    provider: HealthProvider
    records: list[HealthRecord] = Field(max_length=500)


class HealthImportOut(BaseModel):
    imported: int
    updated: int
    skipped: int


class HealthConnectionIn(BaseModel):
    granted_data_types: list[Literal["exercise", "distance", "steps"]] = Field(max_length=10)


class HealthConnectionOut(BaseModel):
    provider: HealthProvider
    granted_data_types: list[str]
    connected_at: datetime
    last_synced_at: datetime | None
    active: bool


class GoalIn(BaseModel):
    metric: Literal["distance_km", "workout_count", "active_minutes"]
    period: Literal["weekly", "monthly"]
    target_value: float = Field(gt=0, le=10_000)
    activity_type: Activity | None = None


class GoalProgress(BaseModel):
    id: uuid.UUID
    metric: str
    period: str
    target_value: float
    activity_type: str | None
    current_value: float
    progress: float  # may exceed 1.0
    period_start: date
    period_end: date


class SummaryOut(BaseModel):
    period: Literal["weekly", "monthly"]
    period_start: date
    period_end: date
    timezone: str
    workouts: int
    distance_km: float
    active_minutes: float
    calories_kcal_estimate: float | None
    goals: list[GoalProgress]
