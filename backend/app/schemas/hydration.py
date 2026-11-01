import uuid
from datetime import date, datetime
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

GOAL_MIN, GOAL_MAX = 250, 10000


class EntryIn(BaseModel):
    client_id: uuid.UUID  # generated on the device; makes retries idempotent
    volume_ml: int = Field(ge=1, le=5000)
    consumed_at: AwareDatetime | None = None  # defaults to server "now"
    source: Literal["app", "reminder"] = "app"


class EntryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    client_id: uuid.UUID
    volume_ml: int
    consumed_at: datetime
    source: str
    deleted: bool = False


class DaySummary(BaseModel):
    date: date
    total_ml: int
    goal_ml: int
    progress: float  # total / goal, may exceed 1.0
    goal_met: bool


class TodayOut(DaySummary):
    timezone: str
    entries: list[EntryOut]


class HistoryOut(BaseModel):
    timezone: str
    days: list[DaySummary]


class GoalIn(BaseModel):
    daily_goal_ml: int = Field(ge=GOAL_MIN, le=GOAL_MAX)


class GoalOut(BaseModel):
    daily_goal_ml: int
    effective_from: date | None  # None = app default, never set by the user
