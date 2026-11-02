import uuid
from datetime import datetime, time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.common import validate_timezone


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    first_name: str
    last_name: str | None
    email_verified: bool
    timezone: str
    locale: str
    units: Literal["metric", "imperial"]
    plan: Literal["free", "premium"]
    created_at: datetime


class UserUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    timezone: str | None = None
    locale: str | None = Field(default=None, pattern=r"^[a-z]{2}(-[A-Z]{2})?$")
    units: Literal["metric", "imperial"] | None = None

    @field_validator("timezone")
    @classmethod
    def tz(cls, v: str | None) -> str | None:
        return validate_timezone(v) if v is not None else v


class NotificationPrefsOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    hydration_reminders_enabled: bool
    hydration_reminder_interval_minutes: int
    quiet_hours_start: time | None
    quiet_hours_end: time | None
    medication_reminders_enabled: bool
    workout_reminders_enabled: bool


class NotificationPrefsUpdate(BaseModel):
    hydration_reminders_enabled: bool | None = None
    hydration_reminder_interval_minutes: int | None = Field(default=None, ge=30, le=480)
    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None
    medication_reminders_enabled: bool | None = None
    workout_reminders_enabled: bool | None = None

    @model_validator(mode="after")
    def quiet_hours_pair(self):
        fields = self.model_fields_set
        if ("quiet_hours_start" in fields) != ("quiet_hours_end" in fields):
            raise ValueError("quiet_hours_start and quiet_hours_end must be set together")
        if self.quiet_hours_start is not None and self.quiet_hours_start == self.quiet_hours_end:
            raise ValueError("quiet_hours_start and quiet_hours_end must be different")
        return self


class FitnessProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    body_weight_kg: float | None  # optional; only used for calorie *estimates*


class FitnessProfileUpdate(BaseModel):
    body_weight_kg: float | None = Field(ge=20, le=400)
